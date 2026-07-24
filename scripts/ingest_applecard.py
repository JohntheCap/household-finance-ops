"""Ingest an Apple Card statement CSV into hf_transaction (Sprint 3R item d).

Wallet -> Apple Card -> statement -> Export Transactions -> CSV. Monthly latency
is accepted: the checking-side APPLECARD GSBANK PAYMENT rows already carry the
timely cash-flow signal, this adds the line-item detail behind them.

Idempotency key
---------------
The Sprint 3 plan specified applecard-<sha256(date|merchant|amount)>. Measured
against six real statements that key collides on 5 tuples covering 7 rows -- most
severely 4x DELTA $676.52 on 2026-05-26, which would collapse to one row and lose
$2,029.56 silently. The tuple is genuinely not unique: same merchant, same amount,
same day happens. So an occurrence ordinal within each (date, merchant, amount)
group joins the hash. Re-importing the same statement reproduces the same
ordinals, so upserts stay idempotent.

Known edge: if one calendar day's charges were ever split across two statement
files, the ordinals would differ between them and could duplicate. Statements cut
on billing cycles rather than mid-day, so this has not been observed; the run
summary prints the collision count so it stays visible.

Amount convention
-----------------
Apple's CSV is positive-for-purchase; ours is negative-for-outflow (6.2), so
amounts are negated. Payment rows arrive negative and become positive, and are
flagged hf_istransfer -- they are the card-side mirror of the checking payment,
not new spending.

Category taxonomy
-----------------
Apple's categories are not Plaid's. Rather than invent a mapping, Apple's value
is stored verbatim in hf_categorydetailed and hf_category is left empty. Read
category together with hf_sourceenv; the taxonomies are not comparable.

Auth: borrows your Azure CLI login (az login).

Usage:
  python ingest_applecard.py https://org29b77f3e.crm.dynamics.com statement.csv --dry-run
  python ingest_applecard.py https://org29b77f3e.crm.dynamics.com statement.csv
"""
import csv
import datetime as dt
import hashlib
import json
import subprocess
import sys
import uuid
from collections import Counter, defaultdict

import requests

ENV_URL = sys.argv[1].rstrip("/")
CSV_PATH = sys.argv[2]
DRY_RUN = "--dry-run" in sys.argv
API = f"{ENV_URL}/api/data/v9.2"
P = "hf"
SOURCE_ENV = "applecard-csv"

# The Apple Card has no Plaid Item, but it still needs an hf_account row so
# transactions join to something and the digest can name the account.
CARD_ACCOUNT_ID = "applecard-manual"
CARD_ACCOUNT_NAME = "Apple Card (statement CSV)"

# Export header names vary by locale/version; first match wins.
COLUMNS = {
    "date": ("Transaction Date", "Date"),
    "merchant": ("Merchant", "Description"),
    "category": ("Category", "Apple category"),
    "type": ("Type",),
    "amount": ("Amount (USD)", "Amount"),
}


def pick(header, names, required=True):
    for n in names:
        if n in header:
            return n
    lowered = {h.lower().strip(): h for h in header}
    for n in names:
        if n.lower() in lowered:
            return lowered[n.lower()]
    if required:
        sys.exit(f"CSV missing a column for {names}; got {header}")
    return None


def as_date(v):
    v = str(v).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return dt.datetime.strptime(v[:10], fmt).date()
        except ValueError:
            continue
    return None


def synthetic_id(date, merchant, amount, occurrence):
    raw = f"{date.isoformat()}|{merchant}|{amount:.2f}|{occurrence}"
    return f"applecard-{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"[:100]


def load(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        sys.exit(f"{path} has no data rows")
    header = list(rows[0].keys())
    col = {k: pick(header, names, required=(k != "type")) for k, names in COLUMNS.items()}

    parsed, skipped, seen = [], [], defaultdict(int)
    for i, r in enumerate(rows, start=2):
        date = as_date(r[col["date"]])
        raw_amount = (r[col["amount"]] or "").replace("$", "").replace(",", "").strip()
        merchant = (r[col["merchant"]] or "").strip()
        if date is None or not raw_amount or not merchant:
            skipped.append(f"line {i}: unparseable (date={r[col['date']]!r} amount={raw_amount!r})")
            continue
        amount = float(raw_amount)
        key = (date, merchant, amount)
        seen[key] += 1
        txn_type = (r[col["type"]] or "").strip() if col["type"] else ""
        parsed.append({
            "id": synthetic_id(date, merchant, amount, seen[key]),
            "date": date,
            "merchant": merchant[:200],
            "amount": -amount,  # 6.2: negative = outflow
            "category": (r[col["category"]] or "").strip()[:100] if col["category"] else "",
            "type": txn_type,
            "is_transfer": txn_type.lower() == "payment",
            "occurrence": seen[key],
        })
    collisions = sum(v - 1 for v in seen.values() if v > 1)
    return parsed, skipped, collisions


def main():
    txns, skipped, collisions = load(CSV_PATH)
    ids = {t["id"] for t in txns}
    if len(ids) != len(txns):
        sys.exit(f"INTERNAL: {len(txns) - len(ids)} duplicate synthetic ids -- refusing to write")

    dates = [t["date"] for t in txns]
    covers = f"{min(dates)}..{max(dates)}"
    transfers = sum(t["is_transfer"] for t in txns)
    outflow = sum(t["amount"] for t in txns if not t["is_transfer"])
    print(f"{len(txns)} rows, covering {covers}")
    print(f"  {transfers} payment rows flagged as transfers (excluded from spend)")
    print(f"  net non-transfer outflow {outflow:,.2f}")
    print(f"  {collisions} same-day/merchant/amount repeats disambiguated by ordinal")
    print(f"  top categories: {dict(Counter(t['category'] for t in txns).most_common(5))}")
    for s in skipped:
        print("  SKIPPED " + s)

    if DRY_RUN:
        print("--dry-run: nothing written")
        return

    token = subprocess.run(
        ["az", "account", "get-access-token", "--resource", ENV_URL,
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, check=True, shell=True).stdout.strip()
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}",
                      "OData-MaxVersion": "4.0", "OData-Version": "4.0",
                      "Accept": "application/json", "Content-Type": "application/json"})

    ts = dt.datetime.now(dt.timezone.utc).isoformat()
    run_id = str(uuid.uuid4())[:8]

    r = s.patch(f"{API}/{P}_accounts({P}_plaidaccountid='{CARD_ACCOUNT_ID}')",
                data=json.dumps({f"{P}_name": CARD_ACCOUNT_NAME, f"{P}_mask": "",
                                 f"{P}_type": "credit/credit card",
                                 f"{P}_freshnessts": ts, f"{P}_sourceenv": SOURCE_ENV}))
    if r.status_code >= 400:
        sys.exit(f"account upsert failed: HTTP {r.status_code}\n{r.text[:500]}")

    written = 0
    for t in txns:
        r = s.patch(f"{API}/{P}_transactions({P}_plaidtxnid='{t['id']}')", data=json.dumps({
            f"{P}_posteddate": t["date"].isoformat(),
            f"{P}_amount": round(t["amount"], 2),
            f"{P}_merchantraw": t["merchant"],
            f"{P}_category": "",            # Apple taxonomy != Plaid taxonomy
            f"{P}_categorydetailed": t["category"],
            f"{P}_istransfer": t["is_transfer"],
            f"{P}_ispending": False,        # statements are settled by definition
            f"{P}_isremoved": False,
            f"{P}_plaidaccountid_text": CARD_ACCOUNT_ID,
            f"{P}_freshnessts": ts,
            f"{P}_sourceenv": SOURCE_ENV,
        }))
        if r.status_code >= 400:
            sys.exit(f"FAILED on {t['merchant']} {t['date']}: HTTP {r.status_code}\n{r.text[:600]}\n"
                     f"{written} rows already written; re-running is safe (upserts).")
        written += 1

    r = s.post(f"{API}/{P}_auditlogs", data=json.dumps({
        f"{P}_timestamp": ts,
        f"{P}_actor": "ingest_applecard",
        f"{P}_action": "applecard.import",
        f"{P}_entitytype": "Transaction",
        f"{P}_entityid": run_id,
        f"{P}_context": json.dumps({
            "run_id": run_id, "file": CSV_PATH, "rows": written,
            # Statement coverage: which months have card detail, so a rollup can
            # tell "no card spend" from "no statement imported yet".
            "covers": covers, "transfers": transfers, "collisions": collisions,
            "skipped": len(skipped),
            "empty_reason": "clean_empty" if not written else None,
            "source_env": SOURCE_ENV,
        })[:4000],
    }))
    if r.status_code >= 400:
        sys.exit(f"rows written but AUDIT FAILED: HTTP {r.status_code}\n{r.text[:500]}")

    print(f"imported {written} rows, audit run_id={run_id}")


if __name__ == "__main__":
    main()
