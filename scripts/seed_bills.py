"""Seed hf_bill from the reviewed CSV (Sprint 3R item a).

Reads the file derive_bill_seed.py produced AFTER John has reviewed it -- the
derivation proposes, a human confirms, this loads. Re-running is safe: every row
is an alternate-key upsert on hf_billkey, so edits to the CSV flow through and
nothing duplicates.

Auth: borrows your Azure CLI login (az login), same as create_tables.py.
Prerequisite: the hf_bill alternate key must show Active in the solution
(~15 min after create_tables.py). Upserts fail with 404 until then.

Usage:
  python seed_bills.py https://org29b77f3e.crm.dynamics.com bill_seed_review.csv
  python seed_bills.py https://org29b77f3e.crm.dynamics.com bill_seed_review.csv --dry-run
"""
import csv
import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone

import requests

ENV_URL = sys.argv[1].rstrip("/")
CSV_PATH = sys.argv[2]
DRY_RUN = "--dry-run" in sys.argv
API = f"{ENV_URL}/api/data/v9.2"
P = "hf"

VALID_KIND = {"bill", "category", "excluded"}
VALID_MODE = {"merchant", "merchant+amount", "review", "none"}
VALID_STATUS = {"active", "paused", "cancelled"}
VALID_ACCOUNT = {"checking", "applecard", "mixed", "unknown"}

# End dates known from the Register notes but not derivable from transactions.
END_DATES = {
    "tesla-model-y-lease-jpmorgan": "2028-03-31",
    "apple-card-installment-plan": "2026-11-30",
}


def now():
    return datetime.now(timezone.utc).isoformat()


def money(v):
    # Tolerate Excel's round-trip: the review step opens this file in a spreadsheet,
    # which happily writes back "$2,897.45" where we wrote 2897.45.
    if v in (None, "", "None"):
        return None
    return round(float(str(v).replace("$", "").replace(",", "").strip()), 2)


def isodate(v):
    """Normalise a review-edited date back to ISO.

    Excel reformats 2026-04-16 to 4/16/2026 on save, and Dataverse rejects that --
    silently turning the human-verification step into a data corruption step.
    """
    if v in (None, "", "None"):
        return None
    v = str(v).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(v[:10], fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"unparseable date {v!r}")


def integer(v, default=None):
    if v in (None, "", "None"):
        return default
    return int(float(v))


def validate(rows):
    """Refuse to seed a CSV that would poison matching. Fail loud, fail early."""
    errors, keys = [], set()
    for i, r in enumerate(rows, start=2):  # header is line 1
        key = r["bill_key"]
        where = f"line {i} ({r.get('name', '?')[:40]})"
        if not key:
            errors.append(f"{where}: empty bill_key")
        if key in keys:
            errors.append(f"{where}: duplicate bill_key '{key}'")
        keys.add(key)
        if r["kind"] not in VALID_KIND:
            errors.append(f"{where}: kind '{r['kind']}' not in {sorted(VALID_KIND)}")
        if r["match_mode"] not in VALID_MODE:
            errors.append(f"{where}: match_mode '{r['match_mode']}' not in {sorted(VALID_MODE)}")
        if r["status"] not in VALID_STATUS:
            errors.append(f"{where}: status '{r['status']}' not in {sorted(VALID_STATUS)}")
        if r["payment_account"] not in VALID_ACCOUNT:
            errors.append(f"{where}: payment_account '{r['payment_account']}'")
        # The invariant that keeps false MISSED out of Amanda's digest: anything
        # the matcher will act on needs a pattern and a due day to act on.
        if r["kind"] == "bill" and r["match_mode"] in ("merchant", "merchant+amount"):
            if not r["match_pattern"]:
                errors.append(f"{where}: match_mode={r['match_mode']} but no match_pattern")
            if not integer(r["due_day"]):
                errors.append(f"{where}: match_mode={r['match_mode']} but no due_day")
            if not r.get("anchor_date"):
                errors.append(f"{where}: match_mode={r['match_mode']} but no anchor_date")
        if r["kind"] != "bill" and r["match_mode"] != "none":
            errors.append(f"{where}: kind={r['kind']} must have match_mode=none")
    return errors


def to_record(r, ts):
    kind = r["kind"]
    return {
        f"{P}_billkey": r["bill_key"],
        f"{P}_name": r["name"][:120],
        f"{P}_kind": kind,
        f"{P}_tier": r["tier"][:10],
        f"{P}_status": r["status"],
        f"{P}_amounttype": r["amount_type"][:20],
        f"{P}_expectedamount": money(r["expected_amount"]),
        f"{P}_monthlyequivalent": money(r.get("monthly_equivalent")),
        f"{P}_frequency": r["frequency"][:20],
        f"{P}_dueday": integer(r["due_day"]),
        f"{P}_anchordate": isodate(r.get("anchor_date")),
        f"{P}_paymentaccount": r["payment_account"],
        f"{P}_latencydays": integer(r["latency_days"], 35),
        f"{P}_matchmode": r["match_mode"],
        f"{P}_matchpattern": r["match_pattern"][:200],
        f"{P}_variancetolerancepct": integer(r["variance_tolerance_pct"], 15),
        f"{P}_enddate": END_DATES.get(r["bill_key"]) or isodate(r["end_date"]),
        f"{P}_notes": (r["notes"] or "")[:4000],
        f"{P}_freshnessts": ts,
        f"{P}_sourceenv": "monthly-nut-v2",
    }


def main():
    with open(CSV_PATH, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    errors = validate(rows)
    if errors:
        print(f"REFUSING TO SEED -- {len(errors)} validation error(s):")
        for e in errors:
            print("  " + e)
        sys.exit(1)

    counts = {k: sum(1 for r in rows if r["kind"] == k) for k in sorted(VALID_KIND)}
    matchable = sum(1 for r in rows if r["match_mode"] in ("merchant", "merchant+amount"))
    print(f"{len(rows)} rows validated: {counts}; {matchable} will be matched")

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

    ts, run_id = now(), str(uuid.uuid4())[:8]
    written = 0
    for r in rows:
        rec = to_record(r, ts)
        url = f"{API}/{P}_bills({P}_billkey='{r['bill_key']}')"
        resp = s.patch(url, data=json.dumps(rec))
        if resp.status_code >= 400:
            sys.exit(f"FAILED on {r['bill_key']}: HTTP {resp.status_code}\n{resp.text[:800]}")
        written += 1

    # Non-negotiable 2: the seed is a state change, so it is audited like any other.
    audit = s.post(f"{API}/{P}_auditlogs", data=json.dumps({
        f"{P}_timestamp": ts,
        f"{P}_actor": "seed_bills",
        f"{P}_action": "bill.seed",
        f"{P}_entitytype": "Bill",
        f"{P}_entityid": run_id,
        f"{P}_context": json.dumps({
            "run_id": run_id, "source": CSV_PATH, "rows": written,
            "kinds": counts, "matchable": matchable,
            "source_env": "monthly-nut-v2",
        })[:4000],
    }))
    if audit.status_code >= 400:
        sys.exit(f"rows written but AUDIT FAILED: HTTP {audit.status_code}\n{audit.text[:500]}")

    print(f"seeded {written} bills, audit run_id={run_id}")


if __name__ == "__main__":
    main()
