"""Registry corrections 2026-09-01 (month-end close, September).

Five changes, each evidence-backed from the drifted-instance audit run this
session (9 drifted instances across 6 bills). FOUR are applied; B is HELD
pending John's read of the collections agreement -- see its inline comment.

A. amex-amanda-payment -- Amanda starts paying the Amex from primary checking
   (...0666) at the Sept 25 due date. That account is already synced, so the
   payment joins the perimeter with NO Plaid Item #2 (PAYG question closed).
   paymentaccount external -> checking, and anchordate 2026-08-25 -> 2026-09-25
   so due_dates() cannot invent Jul/Aug cycles she paid externally.
   matchmode STAYS "none" on purpose: the descriptor has never appeared in
   1,155 synced transactions, so any pattern would be a guess, and a guessed
   pattern is fake match config -- it produces a false MISSED in Amanda's
   digest. October follow-up: read the real descriptor off the first posting,
   then set matchmode=merchant + matchpattern from evidence.
   NOTE: startdate is deliberately NOT set. startdate gates the envelope window
   (digest.py), so dating it 9/25 would drop $175 out of September's Tier 1 --
   but she owes it in September regardless of which account pays it.

B. harris-harris -- HELD, NOT APPLIED. All four observed actuals are exactly
   100.00 (2026-05-21, 06-21, 07-21, 08-21; zero spread) against a registered
   137.50. That is either a bad seed (fix to 100.00, which improves Tier 1 by
   37.50 and pushes payoff from ~Jul 2027 to ~Nov 2027) or four short payments
   on a collections account (escalate instead). John is checking which.

C. patreon -- expected 8.02 is stale. 10.00 in May, then 5.00 for three
   consecutive months. 8.02 -> 5.00. Tier 3, so no headline envelope effect.

D. gas-nw-natural -- not drift, seasonality. Actuals 67.53 / 37.63 / 29.38 /
   27.76 across May-Aug: a 143% spread on a gas bill going into summer.
   amounttype fixed -> variable, tolerance 15 -> 60 (worst observed -51.5%).

E. electric-pge -- same class. Actuals 300.00 / 300.23 / 325.00 / 180.00.
   amounttype fixed -> variable, tolerance 15 -> 50 (worst observed -41.6%,
   matching the Google Fi tolerance precedent).

Deliberately NOT touched:
  internet-comcast -- 94/94/43.61/70.00 was a real price change that has
    already settled at the registered 70.00. Nothing to fix.
  synchrony-payment -- 100/100/100/72.00. A single low month, not a trend.
    Watch it in October rather than moving expected off 100.00 on one data
    point.

Idempotent (per-bill notes marker). Audited (one hf_auditlog row per change).
Usage:
  py apply_updates_2026-09-01.py https://org29b77f3e.crm.dynamics.com [--dry-run]
"""
import datetime as dt, json, subprocess, sys, requests

ENV_URL = sys.argv[1].rstrip("/"); DRY = "--dry-run" in sys.argv
API = f"{ENV_URL}/api/data/v9.2"; P = "hf"
ACTOR = "apply_updates_2026-09-01"

# marker: substring searched in hf_notes to make each change idempotent.
UPDATES = [
    {"key": "amex-amanda-payment",
     "action": "bill.move_into_perimeter",
     "marker": "[2026-09-01 perimeter]",
     "patch": {f"{P}_paymentaccount": "checking",
               f"{P}_anchordate": "2026-09-25"},
     "note": ("[2026-09-01 perimeter] Amanda begins paying this from primary "
              "checking (...0666) at the 2026-09-25 due date, so it enters the "
              "Plaid perimeter with no Item #2. matchmode stays 'none' until "
              "the first payment posts and we can read the real descriptor -- "
              "0 amex/aexp descriptors in 1,155 synced txns, so any pattern now "
              "would be a guess. Follow-up in the October close: set "
              "matchmode=merchant + matchpattern from the observed posting."),
     "evidence": "0/1155 amex descriptors; 23 outflows $150-200 all identified as other merchants"},

    {"key": "harris-harris",
     "action": "bill.correct_stale_expectedamount",
     "marker": "[2026-09-01 expected]",
     # HELD 2026-09-01. The data is unambiguous -- four actuals of exactly
     # 100.00 -- but it has two readings and only John can pick: either the
     # 137.50 seed is wrong (registry error, fix it), or 137.50 is the agreed
     # payment and these are four short payments on a COLLECTIONS account,
     # which is a shortfall to escalate, not a number to quietly restate.
     # Lift by deleting this one line once he has read the agreement.
     "hold": "awaiting John's check of the Harris & Harris agreement",
     "patch": {f"{P}_expectedamount": 100.00,
               f"{P}_monthlyequivalent": 100.00},
     "note": ("[2026-09-01 expected] expectedamount 137.50 -> 100.00. All four "
              "observed actuals are exactly 100.00 (05-21, 06-21, 07-21, "
              "08-21), zero spread -- the 137.50 was a bad seed, not drift. "
              "Payoff date must be recomputed against 100.00/mo."),
     "evidence": "4/4 observed actuals = 100.00 exactly, 2026-05-21 through 2026-08-21"},

    {"key": "patreon",
     "action": "bill.correct_stale_expectedamount",
     "marker": "[2026-09-01 expected]",
     "patch": {f"{P}_expectedamount": 5.00,
               f"{P}_monthlyequivalent": 5.00},
     "note": ("[2026-09-01 expected] expectedamount 8.02 -> 5.00. 10.00 in May "
              "then 5.00 for three consecutive months; the membership tier "
              "changed and the seed averaged across the change."),
     "evidence": "actuals 2026-05:10.00, 06:5.00, 07:5.00, 08:5.00"},

    {"key": "gas-nw-natural",
     "action": "bill.reclassify_variable",
     "marker": "[2026-09-01 variable]",
     "patch": {f"{P}_amounttype": "variable",
               f"{P}_variancetolerancepct": 60},
     "note": ("[2026-09-01 variable] Registered fixed/15% but this is a "
              "seasonal gas bill: 67.53 / 37.63 / 29.38 / 27.76 May-Aug, a 143% "
              "spread. amounttype -> variable, tolerance -> 60% (worst observed "
              "-51.5%). expectedamount stays 57.27 as the annual average -- "
              "winter will run back above it."),
     "evidence": "actuals 67.53/37.63/29.38/27.76; drifted 2026-07 (-48.7%) and 2026-08 (-51.5%)"},

    {"key": "electric-pge",
     "action": "bill.reclassify_variable",
     "marker": "[2026-09-01 variable]",
     "patch": {f"{P}_amounttype": "variable",
               f"{P}_variancetolerancepct": 50},
     "note": ("[2026-09-01 variable] Registered fixed/15% but usage-billed: "
              "300.00 / 300.23 / 325.00 / 180.00 May-Aug. amounttype -> "
              "variable, tolerance -> 50% (worst observed -41.6%), matching the "
              "Google Fi precedent. SEPARATE OPEN ISSUE: a second PGE billpay "
              "of 200.00 posted 2026-08-24, 19d from the 08-05 due date and so "
              "outside the 10d match window -- August PGE was 380.00 across two "
              "payments, only one of which bound. Do not fix by widening the "
              "window; that would let one cycle claim the next cycle's txn."),
     "evidence": "actuals 300.00/300.23/325.00/180.00; drifted 2026-08 (-41.6%); unmatched 2026-08-24 -200.00"},
]


def main():
    tok = subprocess.run(["az", "account", "get-access-token", "--resource", ENV_URL,
        "--query", "accessToken", "-o", "tsv"], capture_output=True, text=True,
        check=True, shell=True).stdout.strip()
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}", "OData-MaxVersion": "4.0",
        "OData-Version": "4.0", "Accept": "application/json",
        "Content-Type": "application/json"})

    applied = skipped = held = 0
    for u in UPDATES:
        key = u["key"]
        if u.get("hold"):
            print(f"  ~~ {key}: HELD -- {u['hold']}")
            held += 1
            continue
        r = s.get(f"{API}/{P}_bills({P}_billkey='{key}')")
        if r.status_code == 404:
            sys.exit(f"{key} NOT FOUND -- aborting, registry is not in the expected state")
        if r.status_code >= 400:
            sys.exit(f"GET {key} failed: {r.status_code}\n{r.text[:400]}")
        row = r.json()
        if u["marker"] in (row.get(f"{P}_notes") or ""):
            print(f"  == {key}: already applied, skip")
            skipped += 1
            continue

        before = {f: row.get(f) for f in u["patch"]}
        print(f"  -> {key}")
        for f, after in u["patch"].items():
            print(f"       {f.replace(P + '_', ''):22} {before[f]} -> {after}")
        if DRY:
            continue

        ts = dt.datetime.now(dt.timezone.utc).isoformat()
        patch = dict(u["patch"])
        patch[f"{P}_freshnessts"] = ts
        patch[f"{P}_notes"] = f"{u['note']} {(row.get(f'{P}_notes') or '')}".strip()[:4000]
        resp = s.patch(f"{API}/{P}_bills({P}_billkey='{key}')", data=json.dumps(patch))
        if resp.status_code >= 400:
            sys.exit(f"PATCH {key} FAILED: {resp.status_code}\n{resp.text[:600]}")

        a = s.post(f"{API}/{P}_auditlogs", data=json.dumps({
            f"{P}_timestamp": ts, f"{P}_actor": ACTOR, f"{P}_action": u["action"],
            f"{P}_entitytype": "Bill", f"{P}_entityid": key,
            f"{P}_context": json.dumps({"billkey": key, "before": before,
                "after": u["patch"], "evidence": u["evidence"],
                "requested_by": "John"})[:4000]}))
        if a.status_code >= 400:
            sys.exit(f"AUDIT {key} FAILED: {a.status_code}\n{a.text[:400]}")
        applied += 1

    verb = "would apply" if DRY else "applied"
    print(f"\n  {verb} {len(UPDATES) - skipped - held if DRY else applied}, skipped {skipped}, held {held}")
    if not DRY and applied:
        print("  NEXT: run /api/match, or 'Coming up / Needs attention' stays stale.")


if __name__ == "__main__":
    main()
