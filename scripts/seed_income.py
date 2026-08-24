"""Seed the active-income lines into hf_bill as kind='income' (envelope headline).

The weekly digest's envelope headline reads income LIVE (income - Tier 1 bills),
so income cannot stay hardcoded in digest.py. Rather than a new table (non-
negotiable #3: no side databases), income lines live in hf_bill under kind='income'
-- a kind the nightly matcher already ignores (function_app match_bills filters
hf_kind eq 'bill'), so these rows never produce bill instances or false MISSED.
Reusing hf_bill also gives the Oregon-UI end-date cliff a home for free
(hf_enddate + hf_status), which the envelope honors: an income line only counts
while today is within [startdate, enddate], so it drops out automatically.

Re-running is safe: every row is an alternate-key upsert on hf_billkey.

Auth: borrows your Azure CLI login (az login), same as seed_bills.py.
Prerequisite: the hf_bill alternate key must be Active in the solution.

Usage:
  python seed_income.py https://org29b77f3e.crm.dynamics.com
  python seed_income.py https://org29b77f3e.crm.dynamics.com --dry-run
"""
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone

import requests

# az is a .cmd on Windows (needs the shell to resolve) but a normal executable on
# POSIX, where shell=True with a list arg would run bare `az` and drop the token
# args. Match the platform so the same script runs on John's Windows box and here.
_AZ_SHELL = os.name == "nt"

ENV_URL = sys.argv[1].rstrip("/")
DRY_RUN = "--dry-run" in sys.argv
API = f"{ENV_URL}/api/data/v9.2"
P = "hf"

# Human-verified income lines (John, moved here from digest.py INCOME_ACTIVE,
# 2026-07-27). monthly_equivalent is the amount that feeds the envelope. Oregon UI
# is a PLACEHOLDER until the award letter confirms the weekly benefit amount, and
# carries an end date -- after it, the line falls out of window and the envelope
# shrinks on its own (the digest warns for the 4 weeks before).
# cadence (Sprint 6): drives the cash-runway "next paycheck" date. Derived from
# hf_transaction deposit history 2026-07-27. freq 'monthly' = VA-style end-of-month
# posting; 'biweekly' = anchor + 14-day multiples. An income line with freq=None is
# EXCLUDED from the runway (but still counts in the monthly envelope -- option b):
# that's how not-yet-started Oregon UI stays out of the cash view until it posts.
INCOME = [
    {"bill_key": "income-va-disability",       "name": "VA disability",
     "monthly": 1256.90, "end": None, "freq": "monthly", "anchor": None,
     "notes": "VA service-connected disability. Fixed monthly; posts the last "
              "business day for the coming month (observed 4/29, 5/28, 6/29)."},
    {"bill_key": "income-amanda-viking-vet",   "name": "Amanda (Viking Vet)",
     "monthly": 3486.24, "end": None, "freq": "biweekly", "anchor": "2026-07-24",
     "notes": "Amanda's Viking Vet net pay. Biweekly, Fridays; anchor 2026-07-24 "
              "(next 2026-08-07). Amount varies ~$1,200-1,840; monthly here is the "
              "smoothed equivalent for the envelope, not a per-check figure."},
    {"bill_key": "income-oregon-ui-john",      "name": "Oregon UI (John)",
     "monthly": 3908.67, "end": "2026-08-31", "freq": None, "anchor": None,
     "notes": "CONFIRMED IN TALKS 2026-08-23: John will definitely be paid, but a "
              "processing issue delayed it; the agency will BACK-PAY the missed weeks "
              "(a lump, not modeled here as monthly). BRIDGE income only -- ENDS "
              "2026-08-31, when John's Substrate owner draw begins (cannot draw business "
              "income and collect UI). Amount still a PLACEHOLDER until the award letter "
              "confirms the weekly benefit. freq=None keeps it out of the cash-runway; "
              "counts in the monthly envelope through its end date."},
    {"bill_key": "income-substrate-owner-draw", "name": "Substrate owner draw (John)",
     "monthly": 6500.00, "start": "2026-09-01", "end": None, "freq": "weekly", "anchor": "2026-09-01",
     "notes": "John's weekly owner draw from Substrate (his business with Jim): $1,500/week "
              "starting 2026-09-01. Monthly equivalent $6,500 (1500 x 52 / 12) for the "
              "envelope; weekly cadence feeds the cash-runway. Replaces the Oregon UI bridge "
              "(UI ends 2026-08-31 as this begins). start=2026-09-01 keeps it OUT of the "
              "envelope until it actually starts. Added 2026-08-23."},
]


def now():
    return datetime.now(timezone.utc).isoformat()


def to_record(r, ts):
    """Income modeled as a non-matchable hf_bill row. matchmode='none' and
    kind='income' both keep it out of the matcher; tier is 'income' for clarity."""
    return {
        f"{P}_billkey": r["bill_key"],
        f"{P}_name": r["name"][:120],
        f"{P}_kind": "income",
        f"{P}_tier": "income",
        f"{P}_status": "active",
        f"{P}_amounttype": "fixed",
        f"{P}_expectedamount": round(r["monthly"], 2),
        f"{P}_monthlyequivalent": round(r["monthly"], 2),
        f"{P}_frequency": r.get("freq") or "",
        f"{P}_anchordate": r.get("anchor"),
        f"{P}_startdate": r.get("start"),   # None => counts immediately; set to gate a future start
        f"{P}_paymentaccount": "unknown",
        f"{P}_matchmode": "none",
        f"{P}_enddate": r["end"],
        f"{P}_notes": r["notes"][:4000],
        f"{P}_freshnessts": ts,
        f"{P}_sourceenv": "income-config",
    }


def main():
    total = round(sum(r["monthly"] for r in INCOME), 2)
    print(f"{len(INCOME)} income lines, total {total}/mo:")
    for r in INCOME:
        end = f"  end={r['end']}" if r["end"] else ""
        print(f"  {r['bill_key']:26} {r['monthly']:>10.2f}{end}")

    if DRY_RUN:
        print("--dry-run: nothing written")
        return

    token = subprocess.run(
        ["az", "account", "get-access-token", "--resource", ENV_URL,
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, check=True, shell=_AZ_SHELL).stdout.strip()

    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}",
                      "OData-MaxVersion": "4.0", "OData-Version": "4.0",
                      "Accept": "application/json", "Content-Type": "application/json"})

    ts, run_id = now(), str(uuid.uuid4())[:8]
    written = 0
    for r in INCOME:
        rec = to_record(r, ts)
        url = f"{API}/{P}_bills({P}_billkey='{r['bill_key']}')"
        resp = s.patch(url, data=json.dumps(rec))
        if resp.status_code >= 400:
            sys.exit(f"FAILED on {r['bill_key']}: HTTP {resp.status_code}\n{resp.text[:800]}")
        written += 1

    # Non-negotiable #2: the seed is a state change, so it is audited.
    audit = s.post(f"{API}/{P}_auditlogs", data=json.dumps({
        f"{P}_timestamp": ts,
        f"{P}_actor": "seed_income",
        f"{P}_action": "income.seed",
        f"{P}_entitytype": "Bill",
        f"{P}_entityid": run_id,
        f"{P}_context": json.dumps({
            "run_id": run_id, "rows": written, "total_monthly": total,
            "source_env": "income-config",
        })[:4000],
    }))
    if audit.status_code >= 400:
        sys.exit(f"rows written but AUDIT FAILED: HTTP {audit.status_code}\n{audit.text[:500]}")

    print(f"seeded {written} income lines, audit run_id={run_id}")


if __name__ == "__main__":
    main()
