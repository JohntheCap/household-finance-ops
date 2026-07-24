"""Reset a Plaid Item's sync cursor so the next sync re-emits full history.

Sprint 3R item c: hf_categorydetailed and hf_istransfer only populate on rows the
sync writes, so the ~476 already-synced transactions would keep their coarse
FOOD_AND_DRINK category forever. Blanking the cursor makes /transactions/sync
replay every transaction as 'added'; the hf_plaidtxnid alternate key turns those
into updates, so nothing duplicates and no history is lost.

The pre-reset cursor is written to the audit log before the reset, so the change
is reversible from the audit trail alone.

Auth: borrows your Azure CLI login (az login).

Usage:
  python reset_cursor.py https://org29b77f3e.crm.dynamics.com --list
  python reset_cursor.py https://org29b77f3e.crm.dynamics.com --label USAA
  # then trigger the sync once (timer at 13:00 UTC, or the manual_sync endpoint)
"""
import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone

import requests

ENV_URL = sys.argv[1].rstrip("/")
API = f"{ENV_URL}/api/data/v9.2"
P = "hf"
LIST_ONLY = "--list" in sys.argv
LABEL = sys.argv[sys.argv.index("--label") + 1] if "--label" in sys.argv else None

if not LIST_ONLY and not LABEL:
    sys.exit("specify --label <item label>, or --list to see them")

token = subprocess.run(
    ["az", "account", "get-access-token", "--resource", ENV_URL,
     "--query", "accessToken", "-o", "tsv"],
    capture_output=True, text=True, check=True, shell=True).stdout.strip()

s = requests.Session()
s.headers.update({"Authorization": f"Bearer {token}",
                  "OData-MaxVersion": "4.0", "OData-Version": "4.0",
                  "Accept": "application/json", "Content-Type": "application/json"})

items = s.get(f"{API}/{P}_plaiditems").json()["value"]

if LIST_ONLY:
    for i in items:
        cur = i.get(f"{P}_cursor") or ""
        print(f"  {i[f'{P}_label']:<20} active={i.get(f'{P}_active')} "
              f"last={i.get(f'{P}_lastsyncstatus')} cursor={cur[:24]}...({len(cur)} chars)")
    sys.exit(0)

target = [i for i in items if i[f"{P}_label"] == LABEL]
if len(target) != 1:
    sys.exit(f"expected exactly 1 item labelled '{LABEL}', found {len(target)}")
item = target[0]
old_cursor = item.get(f"{P}_cursor") or ""
guid = item[f"{P}_plaiditemid"]
ts, run_id = datetime.now(timezone.utc).isoformat(), str(uuid.uuid4())[:8]

# Audit BEFORE mutating: if the reset succeeds and the audit does not, the trail
# would be missing the one value needed to undo it.
r = s.post(f"{API}/{P}_auditlogs", data=json.dumps({
    f"{P}_timestamp": ts,
    f"{P}_actor": "reset_cursor",
    f"{P}_action": "plaid.cursor.reset",
    f"{P}_entitytype": "PlaidItem",
    f"{P}_entityid": guid,
    f"{P}_context": json.dumps({
        "run_id": run_id, "label": LABEL, "reason": "sprint3r-c backfill",
        "previous_cursor": old_cursor, "source_env": "production",
    })[:4000],
}))
if r.status_code >= 400:
    sys.exit(f"audit write failed, cursor NOT reset: HTTP {r.status_code}\n{r.text[:500]}")

r = s.patch(f"{API}/{P}_plaiditems({guid})", data=json.dumps({f"{P}_cursor": ""}))
if r.status_code >= 400:
    sys.exit(f"cursor reset FAILED: HTTP {r.status_code}\n{r.text[:500]}")

print(f"cursor cleared for '{LABEL}' (was {len(old_cursor)} chars), audit run_id={run_id}")
print("next sync replays full history as 'added'; upserts make that safe.")
