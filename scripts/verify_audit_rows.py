"""Read-only: confirm the audit rows from today's registry changes landed.

Queries hf_auditlog for the two actors that made the 2026-08-09 changes and prints
each row (timestamp, action, entity, before/after from context). No writes.

Expected: 5 rows --
  apply_plan_updates_2026-08-09: bill.deactivate x3 (primo, lmnt, apple installment)
                                 + bill.update_amount x1 (comcast)
  fix_apple_installment_enddate: bill.correct_enddate x1 (apple installment)

Usage:
  py verify_audit_rows.py https://org29b77f3e.crm.dynamics.com
"""
import json
import os
import subprocess
import sys

import requests

ENV_URL = sys.argv[1].rstrip("/")
API = f"{ENV_URL}/api/data/v9.2"
P = "hf"
_AZ_SHELL = os.name == "nt"
ACTORS = ("apply_plan_updates_2026-08-09", "fix_apple_installment_enddate")


def main():
    token = subprocess.run(
        ["az", "account", "get-access-token", "--resource", ENV_URL,
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, check=True, shell=_AZ_SHELL).stdout.strip()
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}",
                      "OData-MaxVersion": "4.0", "OData-Version": "4.0",
                      "Accept": "application/json", "Content-Type": "application/json"})

    flt = " or ".join(f"{P}_actor eq '{a}'" for a in ACTORS)
    sel = f"{P}_timestamp,{P}_actor,{P}_action,{P}_entitytype,{P}_entityid,{P}_context"
    url = f"{API}/{P}_auditlogs?$select={sel}&$filter={flt}&$orderby={P}_timestamp asc"

    rows = []
    while url:
        r = s.get(url)
        r.raise_for_status()
        j = r.json()
        rows.extend(j.get("value", []))
        url = j.get("@odata.nextLink")

    print(f"Found {len(rows)} audit row(s) from actors {ACTORS}:\n")
    for i, r in enumerate(rows, 1):
        ts = r.get(f"{P}_timestamp")
        actor = r.get(f"{P}_actor")
        action = r.get(f"{P}_action")
        eid = r.get(f"{P}_entityid")
        try:
            ctx = json.loads(r.get(f"{P}_context") or "{}")
            delta = {k: ctx[k] for k in ("before", "after") if k in ctx}
        except (ValueError, TypeError):
            delta = r.get(f"{P}_context")
        print(f"{i}. {ts}  {actor}")
        print(f"     {action} -> {eid}")
        print(f"     {json.dumps(delta)}")
    print(f"\nExpected 5 (4 from apply_plan_updates + 1 correction). "
          f"{'OK' if len(rows) == 5 else 'MISMATCH -- investigate' if len(rows) else 'NONE FOUND'}")


if __name__ == "__main__":
    main()
