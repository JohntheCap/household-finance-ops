"""Create the Sprint 2 Dataverse schema: 4 tables, all columns, 2 alternate keys.

Auth: borrows your Azure CLI login (az login) — no credentials in this script.
Idempotent: skips tables/columns/keys that already exist; safe to re-run.

Usage:
  pip install requests
  python create_tables.py https://org29b77f3e.crm.dynamics.com
"""
import json
import subprocess
import sys

import requests

ENV_URL = sys.argv[1].rstrip("/")
API = f"{ENV_URL}/api/data/v9.2"
SOLUTION = "householdfinance"  # objects land in this solution -> 'hf' prefix publisher
LANG = 1033


def label(text):
    return {"@odata.type": "Microsoft.Dynamics.CRM.Label",
            "LocalizedLabels": [{"@odata.type": "Microsoft.Dynamics.CRM.LocalizedLabel",
                                 "Label": text, "LanguageCode": LANG}]}


def col_text(schema, display, maxlen, primary=False):
    a = {"@odata.type": "Microsoft.Dynamics.CRM.StringAttributeMetadata",
         "SchemaName": schema, "MaxLength": maxlen,
         "RequiredLevel": {"Value": "None"}, "DisplayName": label(display)}
    if primary:
        a["IsPrimaryName"] = True
    return a


def col_memo(schema, display, maxlen=4000):
    return {"@odata.type": "Microsoft.Dynamics.CRM.MemoAttributeMetadata",
            "SchemaName": schema, "MaxLength": maxlen,
            "RequiredLevel": {"Value": "None"}, "DisplayName": label(display)}


def col_bool(schema, display):
    return {"@odata.type": "Microsoft.Dynamics.CRM.BooleanAttributeMetadata",
            "SchemaName": schema, "RequiredLevel": {"Value": "None"},
            "DisplayName": label(display),
            "OptionSet": {"@odata.type": "Microsoft.Dynamics.CRM.BooleanOptionSetMetadata",
                          "TrueOption": {"Value": 1, "Label": label("Yes")},
                          "FalseOption": {"Value": 0, "Label": label("No")}}}


def col_dateonly(schema, display):
    return {"@odata.type": "Microsoft.Dynamics.CRM.DateTimeAttributeMetadata",
            "SchemaName": schema, "Format": "DateOnly",
            "RequiredLevel": {"Value": "None"}, "DisplayName": label(display)}


def col_money(schema, display):
    return {"@odata.type": "Microsoft.Dynamics.CRM.MoneyAttributeMetadata",
            "SchemaName": schema, "Precision": 2,
            "RequiredLevel": {"Value": "None"}, "DisplayName": label(display)}


# ---- schema definition (primary-name column doubles as a real data column) ----

TABLES = [
    {"schema": "hf_account", "display": "Account", "plural": "Accounts",
     "primary": col_text("hf_name", "Account Name", 120, primary=True),
     "columns": [
         col_text("hf_plaidaccountid", "Plaid Account ID", 100),
         col_text("hf_mask", "Mask", 10),
         col_text("hf_type", "Account Type", 50),
         col_text("hf_freshnessts", "Freshness Timestamp", 40),
         col_text("hf_sourceenv", "Source Environment", 20),
     ],
     "key": ("hf_account_plaidaccountid_key", "Plaid Account ID Key", ["hf_plaidaccountid"])},

    {"schema": "hf_transaction", "display": "Transaction", "plural": "Transactions",
     "primary": col_text("hf_merchantraw", "Merchant (Raw)", 200, primary=True),
     "columns": [
         col_text("hf_plaidtxnid", "Plaid Transaction ID", 100),
         col_dateonly("hf_posteddate", "Posted Date"),
         col_money("hf_amount", "Amount"),
         col_text("hf_category", "Category", 60),
         col_bool("hf_ispending", "Is Pending"),
         col_bool("hf_isremoved", "Is Removed"),
         col_text("hf_plaidaccountid_text", "Plaid Account ID (Text)", 100),
         col_text("hf_freshnessts", "Freshness Timestamp", 40),
         col_text("hf_sourceenv", "Source Environment", 20),
     ],
     "key": ("hf_transaction_plaidtxnid_key", "Plaid Transaction ID Key", ["hf_plaidtxnid"])},

    {"schema": "hf_plaiditem", "display": "Plaid Item", "plural": "Plaid Items",
     "primary": col_text("hf_label", "Label", 80, primary=True),
     "columns": [
         col_text("hf_kvsecretname", "Key Vault Secret Name", 120),
         col_memo("hf_cursor", "Sync Cursor"),
         col_bool("hf_active", "Is Active"),
         col_text("hf_lastsyncstatus", "Last Sync Status", 100),
         col_text("hf_lastsyncts", "Last Sync Timestamp", 40),
     ],
     "key": None},

    {"schema": "hf_auditlog", "display": "Audit Log", "plural": "Audit Logs",
     "primary": col_text("hf_action", "Action", 80, primary=True),
     "columns": [
         col_text("hf_timestamp", "Timestamp", 40),
         col_text("hf_actor", "Actor", 80),
         col_text("hf_entitytype", "Entity Type", 40),
         col_text("hf_entityid", "Entity ID", 80),
         col_memo("hf_context", "Context"),
     ],
     "key": None},
]

# ---- execution ----

token = subprocess.run(
    ["az", "account", "get-access-token", "--resource", ENV_URL,
     "--query", "accessToken", "-o", "tsv"],
    capture_output=True, text=True, check=True, shell=True).stdout.strip()

s = requests.Session()
s.headers.update({"Authorization": f"Bearer {token}",
                  "OData-MaxVersion": "4.0", "OData-Version": "4.0",
                  "Accept": "application/json", "Content-Type": "application/json",
                  "MSCRM.SolutionUniqueName": SOLUTION})


def exists(path):
    return s.get(f"{API}/{path}").status_code == 200


def post(path, payload, what):
    r = s.post(f"{API}/{path}", data=json.dumps(payload))
    if r.status_code in (200, 201, 204):
        print(f"  created {what}")
    else:
        sys.exit(f"FAILED on {what}: HTTP {r.status_code}\n{r.text[:1000]}")


for t in TABLES:
    name = t["schema"]
    print(f"\n== {t['display']} ({name}) ==")
    if exists(f"EntityDefinitions(LogicalName='{name}')"):
        print("  table exists, checking columns")
    else:
        post("EntityDefinitions", {
            "SchemaName": name,
            "DisplayName": label(t["display"]),
            "DisplayCollectionName": label(t["plural"]),
            "OwnershipType": "UserOwned",
            "HasNotes": False, "HasActivities": False,
            "Attributes": [t["primary"]],
        }, f"table {name}")

    for col in t["columns"]:
        cname = col["SchemaName"]
        if exists(f"EntityDefinitions(LogicalName='{name}')/Attributes(LogicalName='{cname}')"):
            print(f"  column {cname} exists, skipping")
        else:
            post(f"EntityDefinitions(LogicalName='{name}')/Attributes", col, f"column {cname}")

    if t["key"]:
        kschema, kdisplay, kattrs = t["key"]
        if exists(f"EntityDefinitions(LogicalName='{name}')/Keys(LogicalName='{kschema}')"):
            print(f"  key {kschema} exists, skipping")
        else:
            post(f"EntityDefinitions(LogicalName='{name}')/Keys", {
                "SchemaName": kschema,
                "DisplayName": label(kdisplay),
                "KeyAttributes": kattrs,
            }, f"alternate key {kschema}")

print("\nDone. Verify in make.powerapps.com -> Solutions -> HouseholdFinance:")
print("4 tables; keys on Account + Transaction should reach status Active within ~15 min.")
