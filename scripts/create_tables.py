"""Create the Dataverse schema: 6 tables, all columns, 4 alternate keys.

Sprint 2 (live since 2026-07-07): hf_account, hf_transaction, hf_plaiditem, hf_auditlog.
Sprint 3R adds: hf_bill + hf_billinstance (PRD 6.2 Tables 6 and 7), and
hf_categorydetailed on hf_transaction.

Auth: borrows your Azure CLI login (az login) — no credentials in this script.
Idempotent: skips tables/columns/keys that already exist; safe to re-run. Re-running
after Sprint 2 creates only the new objects and no-ops on everything else.

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
            "MinValue": -1000000000.0, "MaxValue": 1000000000.0,  # negative = outflow (6.2)
            "RequiredLevel": {"Value": "None"}, "DisplayName": label(display)}


def col_int(schema, display, lo=0, hi=1000):
    return {"@odata.type": "Microsoft.Dynamics.CRM.IntegerAttributeMetadata",
            "SchemaName": schema, "MinValue": lo, "MaxValue": hi,
            "RequiredLevel": {"Value": "None"}, "DisplayName": label(display)}


def col_decimal(schema, display, lo=-100000.0, hi=100000.0):
    # Explicit Min/Max on every numeric column: the 2026-07-07 hf_amount range bug
    # was a default-bounds surprise. Never rely on the default again.
    return {"@odata.type": "Microsoft.Dynamics.CRM.DecimalAttributeMetadata",
            "SchemaName": schema, "Precision": 2, "MinValue": lo, "MaxValue": hi,
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
         # Sprint 3R item c: primary alone collapses groceries and restaurants
         # into FOOD_AND_DRINK. detailed is what makes categories trustworthy.
         col_text("hf_categorydetailed", "Category (Detailed)", 100),
         # Sprint 3R item d: card payments are transfers between our own accounts,
         # not spending. Set on APPLECARD GSBANK PAYMENT rows so the payment and
         # the purchases behind it are never both counted as outflow.
         col_bool("hf_istransfer", "Is Transfer"),
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

    # ---- Sprint 3R: the bill registry (PRD 6.2 Table 6) ----
    # hf_kind separates real obligations from spend rollups. Both live here so the
    # monthly nut stays queryable in one place, but only kind='bill' is ever
    # matched -- a category has no due date, so it could only produce false MISSED.
    {"schema": "hf_bill", "display": "Bill", "plural": "Bills",
     "primary": col_text("hf_name", "Bill Name", 120, primary=True),
     "columns": [
         col_text("hf_billkey", "Bill Key", 100),
         col_text("hf_kind", "Kind", 20),                    # bill | category | excluded
         col_text("hf_tier", "Tier", 10),                    # 1 | 2 | 3 | One-off
         col_text("hf_status", "Status", 20),                # active | paused | cancelled
         col_text("hf_amounttype", "Amount Type", 20),       # fixed | variable
         # Two distinct amounts. expectedamount is the per-cycle charge and drives
         # matching; monthlyequivalent is the amortised figure the monthly nut uses.
         # Garbage is 94.72 per cycle but 47.36 a month, and using the latter to
         # match reads every garbage cycle as +100% drift.
         col_money("hf_expectedamount", "Expected Amount"),
         col_money("hf_monthlyequivalent", "Monthly Equivalent"),
         col_text("hf_frequency", "Frequency", 20),          # monthly | bimonthly | quarterly | annual
         col_int("hf_dueday", "Due Day of Month", 1, 31),
         col_dateonly("hf_anchordate", "Cadence Anchor Date"),
         col_text("hf_paymentaccount", "Payment Account", 20),  # checking | applecard | mixed
         # Missed-detection grace. Apple Card spend only arrives with the monthly
         # statement CSV, so a card bill is not late at due+3 the way a checking
         # bill is -- it is simply not observable yet. Without this the first
         # nightly run would fire ~14 false MISSED into Amanda's digest.
         col_int("hf_latencydays", "Match Latency Days", 0, 400),
         col_text("hf_matchmode", "Match Mode", 20),  # merchant | merchant+amount | review | none
         col_text("hf_matchpattern", "Match Pattern", 200),
         col_int("hf_variancetolerancepct", "Variance Tolerance Pct", 0, 100),
         col_dateonly("hf_startdate", "Start Date"),
         col_dateonly("hf_enddate", "End Date"),
         col_memo("hf_notes", "Notes"),
         col_text("hf_freshnessts", "Freshness Timestamp", 40),
         col_text("hf_sourceenv", "Source Environment", 20),
     ],
     "key": ("hf_bill_billkey_key", "Bill Key", ["hf_billkey"])},

    # Per-cycle state (PRD 6.2 Table 7). Status lives here, not on hf_bill, so a
    # MISSED month stays on the record after the next cycle opens and can be
    # acknowledged rather than overwritten.
    {"schema": "hf_billinstance", "display": "Bill Instance", "plural": "Bill Instances",
     "primary": col_text("hf_name", "Instance Name", 200, primary=True),
     "columns": [
         col_text("hf_instancekey", "Instance Key", 100),  # <billkey>|YYYY-MM
         col_text("hf_billkey", "Bill Key", 100),          # parent, by alternate key
         col_dateonly("hf_duedate", "Due Date"),
         col_money("hf_expectedamount", "Expected Amount"),
         col_money("hf_actualamount", "Actual Amount"),
         # upcoming | arrived | missed | drifted | skipped | unobservable
         col_text("hf_status", "Status", 20),
         col_text("hf_matchedtxnid", "Matched Transaction ID", 100),
         col_dateonly("hf_paiddate", "Paid Date"),
         col_decimal("hf_variancepct", "Variance Pct", -10000.0, 10000.0),
         # Tool contract (A4): confidence and source_env travel with the value.
         col_decimal("hf_matchconfidence", "Match Confidence", 0.0, 1.0),
         col_text("hf_emptyreason", "Empty Reason", 40),
         col_memo("hf_notes", "Match Notes"),
         col_text("hf_freshnessts", "Freshness Timestamp", 40),
         col_text("hf_sourceenv", "Source Environment", 20),
     ],
     "key": ("hf_billinstance_instancekey_key", "Instance Key", ["hf_instancekey"])},

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
print("6 tables; keys on Account, Transaction, Bill, BillInstance reach Active in ~15 min.")
print("Alternate keys must be Active BEFORE seed_bills.py runs -- upserts need them.")
