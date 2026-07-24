"""Extend the HF Sync Writer role to the Sprint 3R tables.

Sprint 2's RUNBOOK 1.3 deliberately scoped the function's application-user role to
the four original hf_ tables (least privilege, no delete). hf_bill and
hf_billinstance were created later, so the app user has no access to them and the
matcher's first write returns DATAVERSE_403. This grants the SAME access the
original four tables have -- org-level Create/Read/Write, no delete -- to the two
new tables, keeping the least-privilege posture intact.

Idempotent: AddPrivilegesRole is additive and re-granting an already-held
privilege is a no-op, so this is safe to re-run.

Auth: borrows your Azure CLI login (az login) -- your admin identity, not the
function's. The function cannot widen its own role.

Usage:
  python grant_bill_privileges.py https://org29b77f3e.crm.dynamics.com
"""
import json
import subprocess
import sys

import requests

ENV_URL = sys.argv[1].rstrip("/")
API = f"{ENV_URL}/api/data/v9.2"
ROLE_NAME = "HF Sync Writer"
DEPTH = "Global"  # org-level, matching the original four tables

# Create/Read/Write only -- no Delete, no Append/AppendTo. The new tables use text
# keys (hf_billkey, hf_matchedtxnid), not lookups, so no relationship privileges
# are needed, and append-only discipline means nothing is ever deleted.
TABLES = ["hf_bill", "hf_billinstance"]
ACCESS = ["Create", "Read", "Write"]

token = subprocess.run(
    ["az", "account", "get-access-token", "--resource", ENV_URL,
     "--query", "accessToken", "-o", "tsv"],
    capture_output=True, text=True, check=True, shell=True).stdout.strip()

s = requests.Session()
s.headers.update({"Authorization": f"Bearer {token}",
                  "OData-MaxVersion": "4.0", "OData-Version": "4.0",
                  "Accept": "application/json", "Content-Type": "application/json"})


def one(path):
    r = s.get(f"{API}/{path}")
    r.raise_for_status()
    v = r.json()["value"]
    return v[0] if v else None


role = one(f"roles?$select=roleid,name&$filter=name eq '{ROLE_NAME}'")
if not role:
    sys.exit(f"role '{ROLE_NAME}' not found -- check RUNBOOK 1.3 ran")
role_id = role["roleid"]

privileges = []
for tbl in TABLES:
    for acc in ACCESS:
        p = one(f"privileges?$select=privilegeid,name&$filter=name eq 'prv{acc}{tbl}'")
        if not p:
            sys.exit(f"privilege prv{acc}{tbl} not found -- was the table created?")
        privileges.append({"PrivilegeId": p["privilegeid"], "Depth": DEPTH})
        print(f"  will grant {p['name']} ({DEPTH})")

r = s.post(f"{API}/roles({role_id})/Microsoft.Dynamics.CRM.AddPrivilegesRole",
           data=json.dumps({"Privileges": privileges}))
if r.status_code >= 400:
    sys.exit(f"AddPrivilegesRole failed: HTTP {r.status_code}\n{r.text[:800]}")

print(f"\ngranted {len(privileges)} privileges to '{ROLE_NAME}'.")
print("Privilege changes propagate within ~1-2 min; re-run the matcher after that.")
