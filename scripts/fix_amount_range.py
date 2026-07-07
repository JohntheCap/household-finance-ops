"""Fix hf_transaction.hf_amount to allow negative amounts (outflows, per data model 6.2).

Retrieves the Money attribute metadata, sets MinValue=-1e9 / MaxValue=1e9, PUTs it back.
Auth borrows your az login, same as create_tables.py.

Usage: python fix_amount_range.py https://org29b77f3e.crm.dynamics.com
"""
import json
import subprocess
import sys

import requests

ENV_URL = sys.argv[1].rstrip("/")
API = f"{ENV_URL}/api/data/v9.2"
ATTR = ("EntityDefinitions(LogicalName='hf_transaction')"
        "/Attributes(LogicalName='hf_amount')"
        "/Microsoft.Dynamics.CRM.MoneyAttributeMetadata")

token = subprocess.run(
    ["az", "account", "get-access-token", "--resource", ENV_URL,
     "--query", "accessToken", "-o", "tsv"],
    capture_output=True, text=True, check=True, shell=True).stdout.strip()

headers = {"Authorization": f"Bearer {token}",
           "OData-MaxVersion": "4.0", "OData-Version": "4.0",
           "Accept": "application/json", "Content-Type": "application/json",
           "MSCRM.MergeLabels": "true"}

r = requests.get(f"{API}/{ATTR}", headers=headers)
r.raise_for_status()
attr = r.json()
attr.pop("@odata.context", None)
print(f"current range: {attr.get('MinValue')} .. {attr.get('MaxValue')}")

attr["@odata.type"] = "Microsoft.Dynamics.CRM.MoneyAttributeMetadata"
attr["MinValue"] = -1000000000.0
attr["MaxValue"] = 1000000000.0

r = requests.put(f"{API}/{ATTR}", headers=headers, data=json.dumps(attr))
if r.status_code not in (200, 204):
    sys.exit(f"FAILED: HTTP {r.status_code}\n{r.text[:1000]}")

r = requests.get(f"{API}/{ATTR}", headers=headers)
r.raise_for_status()
a = r.json()
print(f"new range:     {a.get('MinValue')} .. {a.get('MaxValue')}")
print("Done.")
