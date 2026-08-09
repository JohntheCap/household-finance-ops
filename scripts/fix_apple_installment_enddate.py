"""Correct the Apple Card installment end date to its real completion date.

apply_plan_updates_2026-08-09.py stamped enddate=2026-08-09 (the run date) when it
deactivated apple-card-installment-plan. John clarified the installment actually
finished 2026-06-30. Fix the end date + note; audit the correction. Envelope is
unaffected (Tier 1 keys off status, not enddate). Idempotent: skips if already set.

Auth: borrows az login (John@johnthecap.com / tenant 7e8aa92f...), same as the others.

Usage:
  py fix_apple_installment_enddate.py https://org29b77f3e.crm.dynamics.com
  py fix_apple_installment_enddate.py https://org29b77f3e.crm.dynamics.com --dry-run
"""
import datetime as dt
import json
import os
import subprocess
import sys

import requests

ENV_URL = sys.argv[1].rstrip("/")
DRY_RUN = "--dry-run" in sys.argv
API = f"{ENV_URL}/api/data/v9.2"
P = "hf"
_AZ_SHELL = os.name == "nt"

BILLKEY = "apple-card-installment-plan"
NEW_END = "2026-06-30"
NEW_NOTE = ("Installment PAID IN FULL / all payments completed 2026-06-30 (confirmed "
            "by John). Deactivated in registry 2026-08-09. No further billing.")


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def main():
    token = subprocess.run(
        ["az", "account", "get-access-token", "--resource", ENV_URL,
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, check=True, shell=_AZ_SHELL).stdout.strip()
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}",
                      "OData-MaxVersion": "4.0", "OData-Version": "4.0",
                      "Accept": "application/json", "Content-Type": "application/json"})

    r = s.get(f"{API}/{P}_bills({P}_billkey='{BILLKEY}')")
    if r.status_code == 404:
        sys.exit(f"{BILLKEY} NOT FOUND")
    r.raise_for_status()
    row = r.json()
    old_end = row.get(f"{P}_enddate")
    print(f"{BILLKEY}: status={row.get(f'{P}_status')}, enddate {old_end} -> {NEW_END}")

    if (old_end or "")[:10] == NEW_END:
        print("  already correct -- nothing to do (idempotent)")
        return
    if DRY_RUN:
        print("  --dry-run: nothing written")
        return

    ts = now()
    patch = {f"{P}_enddate": NEW_END, f"{P}_notes": NEW_NOTE, f"{P}_freshnessts": ts}
    resp = s.patch(f"{API}/{P}_bills({P}_billkey='{BILLKEY}')", data=json.dumps(patch))
    if resp.status_code >= 400:
        sys.exit(f"PATCH FAILED: HTTP {resp.status_code}\n{resp.text[:800]}")

    audit = s.post(f"{API}/{P}_auditlogs", data=json.dumps({
        f"{P}_timestamp": ts,
        f"{P}_actor": "fix_apple_installment_enddate",
        f"{P}_action": "bill.correct_enddate",
        f"{P}_entitytype": "Bill",
        f"{P}_entityid": BILLKEY,
        f"{P}_context": json.dumps({
            "billkey": BILLKEY, "before": {"enddate": old_end},
            "after": {"enddate": NEW_END}, "reason": "actual completion 2026-06-30, not run date",
        })[:4000],
    }))
    if audit.status_code >= 400:
        sys.exit(f"row corrected but AUDIT FAILED: HTTP {audit.status_code}\n{audit.text[:500]}")
    print(f"  corrected + audited (enddate={NEW_END})")


if __name__ == "__main__":
    main()
