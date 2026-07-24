"""Report alternate-key activation state (Sprint 3R setup gate).

Alternate keys take ~15 minutes to build after create_tables.py. Upserts against a
key that is still Pending fail with a confusing "key not found" 404, so this is the
wait-point check between creating the schema and seeding it.

Auth: borrows your Azure CLI login (az login).

Usage:
  python check_keys.py https://org29b77f3e.crm.dynamics.com
"""
import subprocess
import sys

import requests

ENV_URL = sys.argv[1].rstrip("/")
API = f"{ENV_URL}/api/data/v9.2"

TABLES = ["hf_account", "hf_transaction", "hf_bill", "hf_billinstance"]

token = subprocess.run(
    ["az", "account", "get-access-token", "--resource", ENV_URL,
     "--query", "accessToken", "-o", "tsv"],
    capture_output=True, text=True, check=True, shell=True).stdout.strip()

s = requests.Session()
s.headers.update({"Authorization": f"Bearer {token}",
                  "OData-MaxVersion": "4.0", "OData-Version": "4.0",
                  "Accept": "application/json"})

# 0 = Pending, 1 = InProgress, 2 = Active, 3 = Failed
# Documented as an integer enum, but the API actually returns the string form
# ("Active"). Normalise both and compare case-insensitively -- the first version
# of this check reported NOT READY against four keys that were all Active.
STATES = {0: "Pending", 1: "InProgress", 2: "Active", 3: "Failed"}
ready = True

for table in TABLES:
    r = s.get(f"{API}/EntityDefinitions(LogicalName='{table}')/Keys"
              f"?$select=LogicalName,EntityKeyIndexStatus")
    if r.status_code == 404:
        print(f"  {table:<18} TABLE NOT FOUND -- run create_tables.py first")
        ready = False
        continue
    if r.status_code >= 400:
        sys.exit(f"{table}: HTTP {r.status_code}\n{r.text[:400]}")
    keys = r.json().get("value", [])
    if not keys:
        print(f"  {table:<18} (no alternate key -- expected for this table)")
        continue
    for k in keys:
        raw = k.get("EntityKeyIndexStatus")
        state = str(STATES.get(raw, raw))
        print(f"  {table:<18} {k['LogicalName']:<38} {state}")
        if state.lower() != "active":
            ready = False

print()
print("READY to seed." if ready else "NOT READY -- wait and re-run (keys build in ~15 min).")
sys.exit(0 if ready else 1)
