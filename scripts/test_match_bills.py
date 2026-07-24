"""Offline test of the bill matcher against real observed history.

Exercises functions/function_app.py's pure matching logic (due_dates, match_one)
without Azure, Plaid or Dataverse: the seed CSV supplies the bills, the workbook's
raw sheets supply the transactions. Run this before deploying -- a matcher bug
surfaces as false MISSED in Amanda's digest, which is the one failure mode the
project instructions call unacceptable.

Usage:
  python test_match_bills.py bill_seed_review.csv ..\\..\\Household-Monthly-Nut-v2.xlsx
"""
import csv
import datetime as dt
import os
import sys
import types
from collections import Counter

import openpyxl

CSV_PATH = sys.argv[1] if len(sys.argv) > 1 else "bill_seed_review.csv"
WB_PATH = sys.argv[2] if len(sys.argv) > 2 else "../../Household-Monthly-Nut-v2.xlsx"
P = "hf"


def load_matcher():
    """Import the matcher's pure logic without the Azure/Plaid module preamble.

    function_app.py asserts PLAID_ENV and builds Key Vault clients at import time,
    so it cannot simply be imported here. Executing only the bill-matching section
    keeps this test honest -- it runs the real shipped code, not a copy.
    """
    src = open(os.path.join(os.path.dirname(__file__), "..", "functions",
                            "function_app.py"), encoding="utf-8").read()
    # Anchor on code, not on a comment banner: a reflowed comment would silently
    # change what this test executes.
    start = src.index("MATCH_WINDOW = {")
    end = src.index("def match_bills(")
    mod = types.ModuleType("matcher")
    mod.__dict__.update({
        "P": P, "date": dt.date, "timedelta": dt.timedelta,
        "monthrange": __import__("calendar").monthrange,
        "datetime": dt.datetime, "timezone": dt.timezone,
    })
    exec(compile(src[start:end], "function_app.py", "exec"), mod.__dict__)
    return mod


def load_bills(path):
    out = []
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            # Mirror match_bills' own filter exactly: kind, status and mode.
            # Including cancelled bills here would report drift on Home Chef and
            # Tesla FSD that production will never evaluate.
            if (r["kind"] != "bill" or r["status"] != "active"
                    or r["match_mode"] not in ("merchant", "merchant+amount")):
                continue
            out.append({
                f"{P}_billkey": r["bill_key"], f"{P}_name": r["name"],
                f"{P}_frequency": r["frequency"], f"{P}_dueday": int(r["due_day"]),
                f"{P}_anchordate": r["anchor_date"],
                f"{P}_expectedamount": float(r["expected_amount"] or r["observed_median"] or 0),
                f"{P}_variancetolerancepct": int(r["variance_tolerance_pct"]),
                f"{P}_latencydays": int(r["latency_days"]),
                f"{P}_matchmode": r["match_mode"], f"{P}_matchpattern": r["match_pattern"],
                f"{P}_paymentaccount": r["payment_account"],
            })
    return out


def load_txns(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    out = []
    for sheet, amt_col, env in (("Raw Checking", 3, "production"),
                                ("Raw Apple Card", 4, "applecard-csv")):
        for i, r in enumerate(wb[sheet].iter_rows(min_row=2, values_only=True)):
            if r[0] is None or r[amt_col] is None:
                continue
            amount = float(r[amt_col])
            # Both sheets are normalised to the 6.2 convention here: checking is
            # already negative-for-outflow, the card export is positive-for-purchase.
            out.append({
                f"{P}_plaidtxnid": f"{env}-{i}",
                f"{P}_posteddate": str(r[0])[:10],
                f"{P}_amount": amount if env == "production" else -amount,
                f"{P}_merchantraw": str(r[1] or ""),
                f"{P}_isremoved": False,
                f"{P}_istransfer": "APPLECARD GSBANK PAYMENT" in str(r[1] or "").upper(),
                f"{P}_sourceenv": env,
            })
    return out


def main():
    m = load_matcher()
    bills, txns = load_bills(CSV_PATH), load_txns(WB_PATH)
    # Sit inside the observed window so cycles have real data on both sides.
    today = dt.date(2026, 7, 1)
    print(f"{len(bills)} matchable bills, {len(txns)} transactions, as-of {today}\n")

    claimed, counts, misses = set(), Counter(), []
    for b in bills:
        cycles = m.due_dates(b, today)
        if not cycles:
            print(f"  !! {b[f'{P}_name']}: no cycles generated")
            continue
        row = []
        for due in cycles:
            r = m.match_one(b, due, txns, today, claimed)
            if r.get("txnid"):
                claimed.add(r["txnid"])
            counts[r["status"]] += 1
            if r["status"] == "missed":
                misses.append((b[f"{P}_name"], due, r["note"]))
            flag = {"arrived": "ok", "drifted": "DRIFT", "missed": "MISS",
                    "upcoming": "..", "unobservable": "n/a"}[r["status"]]
            row.append(f"{due.isoformat()[:7]}:{flag}")
        print(f"  {b[f'{P}_name'][:40]:<42} {' '.join(row)}")

    print(f"\nby status: {dict(counts)}")
    total = sum(counts.values())
    hit = counts["arrived"] + counts["drifted"]
    due_cycles = total - counts["upcoming"] - counts["unobservable"]
    print(f"match rate on due cycles: {hit}/{due_cycles} "
          f"({100 * hit / due_cycles:.0f}%)" if due_cycles else "no due cycles")
    if misses:
        print(f"\n{len(misses)} MISSED (each would reach Amanda's digest -- verify every one):")
        for name, due, why in misses:
            print(f"  {name[:40]:<42} {due} {why}")


if __name__ == "__main__":
    main()
