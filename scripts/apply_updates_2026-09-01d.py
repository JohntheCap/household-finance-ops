"""Register the August strays 2026-09-01d -- and deliberately NOT register three.

John identified all five unregistered August outflows this session. Two have a
real cadence and are registered; three do not, and registering them anyway would
manufacture false MISSED flags (OPERATING-CADENCE.md "What NOT to do").

REGISTERED
  roadside-aaa      AAA OR/ID member dues, 191.00 ANNUAL, observed 2026-08-17.
                    John: required, not optional -- Amanda's van is in fair (not
                    good) condition, so roadside cover is a safety dependency.
                    Tier 1 accordingly. monthlyequivalent 15.92 (191.00/12).
                    anchordate 2026-08-17 matters: due_dates() refuses cycles
                    before the anchor month, so a 2-cycle lookback on an ANNUAL
                    bill cannot invent MISSED cycles for 2024/2025 (the GoDaddy
                    lesson, function_app.py).
  supplement-seed   SEED.COM multivitamin, 39.99 MONTHLY. Observed 2026-06-08,
                    07-06, 08-17 (plus a one-off 134.97 on 06-18, an initial or
                    bulk order, not the subscription). The charge date wanders
                    across 9 days, so dueday 10 + latency 30 keeps all three
                    inside the 10-day match window. Tier 3: it is a supplement,
                    and in a deficit month it is a visible, honest cut candidate.

NOT REGISTERED, on purpose
  Redmond ("Redmond Redmon", 34.50, 2026-08-06, Apple Card) -- John's hair-loss
    supplement prescription. Exactly ONE occurrence in 1,157 transactions. One
    data point is not a cadence; registering it would assert a monthly cycle we
    have never observed. Revisit once a second charge appears.
  COLUMBIA RIVER NATU (74.29 on 2026-07-06, 48.00 on 2026-08-10) -- Amanda's
    naturopath. John does not think it is monthly, and the amounts differ by
    55%, consistent with per-visit billing. A visit is not a recurring
    obligation; a bill row would flag MISSED in any month she does not go.
    Tracked as irregular medical spend instead.
  ZOOM MANAGEMENT OR (30.00, 2026-08-10) -- UNKNOWN. John does not recognise it,
    and it appears exactly once. Do not register what nobody can identify.
    See the kickoff checklist: John to identify it from the USAA statement.

Idempotent (alternate-key upsert, skipped if the row already exists). Audited.
Usage:
  py apply_updates_2026-09-01d.py https://org29b77f3e.crm.dynamics.com [--dry-run]
"""
import datetime as dt, json, subprocess, sys, requests

ENV_URL = sys.argv[1].rstrip("/"); DRY = "--dry-run" in sys.argv
API = f"{ENV_URL}/api/data/v9.2"; P = "hf"
ACTOR = "apply_updates_2026-09-01d"

NEW_BILLS = [
    {f"{P}_billkey": "roadside-aaa",
     f"{P}_name": "Roadside assistance (AAA)",
     f"{P}_kind": "bill", f"{P}_tier": "1", f"{P}_status": "active",
     f"{P}_amounttype": "fixed",
     f"{P}_expectedamount": 191.00, f"{P}_monthlyequivalent": 15.92,
     f"{P}_frequency": "annual", f"{P}_dueday": 17,
     f"{P}_anchordate": "2026-08-17",
     f"{P}_paymentaccount": "checking",
     f"{P}_latencydays": 30, f"{P}_matchmode": "merchant",
     f"{P}_matchpattern": "AAA OR/ID", f"{P}_variancetolerancepct": 20,
     f"{P}_notes": ("[2026-09-01d] Registered from the August reconcile. Annual "
                    "dues, observed 2026-08-17 -191.00. John: REQUIRED, not "
                    "discretionary -- Amanda's van is in fair (not good) "
                    "condition, so roadside cover is a safety dependency; hence "
                    "Tier 1. Only one occurrence is on record because the "
                    "transaction history starts 2025-12-31 and this is annual. "
                    "Tolerance 20% for annual dues increases.")},

    {f"{P}_billkey": "supplement-seed",
     f"{P}_name": "Multivitamin (Seed)",
     f"{P}_kind": "bill", f"{P}_tier": "3", f"{P}_status": "active",
     f"{P}_amounttype": "fixed",
     f"{P}_expectedamount": 39.99, f"{P}_monthlyequivalent": 39.99,
     f"{P}_frequency": "monthly", f"{P}_dueday": 10,
     f"{P}_anchordate": "2026-06-08",
     f"{P}_paymentaccount": "checking",
     f"{P}_latencydays": 30, f"{P}_matchmode": "merchant",
     f"{P}_matchpattern": "SEED.COM", f"{P}_variancetolerancepct": 15,
     f"{P}_notes": ("[2026-09-01d] Registered from the August reconcile. John's "
                    "monthly multivitamin. Observed 39.99 on 2026-06-08, 07-06 "
                    "and 08-17; the 134.97 on 06-18 was a one-off initial/bulk "
                    "order, NOT the subscription -- do not raise expectedamount "
                    "for it. Charge date wanders ~9 days, so dueday 10 + latency "
                    "30 keeps every observed charge inside the match window. "
                    "Tier 3: a genuine cut candidate while the envelope is negative.")},
]


def main():
    tok = subprocess.run(["az", "account", "get-access-token", "--resource", ENV_URL,
        "--query", "accessToken", "-o", "tsv"], capture_output=True, text=True,
        check=True, shell=True).stdout.strip()
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}", "OData-MaxVersion": "4.0",
        "OData-Version": "4.0", "Accept": "application/json",
        "Content-Type": "application/json"})

    created = skipped = 0
    for rec in NEW_BILLS:
        key = rec[f"{P}_billkey"]
        r = s.get(f"{API}/{P}_bills({P}_billkey='{key}')")
        if r.status_code == 200:
            print(f"  == {key}: already registered, skip")
            skipped += 1
            continue
        if r.status_code != 404:
            sys.exit(f"GET {key} unexpected: {r.status_code}\n{r.text[:400]}")
        print(f"  -> CREATE {key}: {rec[f'{P}_name']} "
              f"{rec[f'{P}_expectedamount']:.2f}/{rec[f'{P}_frequency']} "
              f"tier {rec[f'{P}_tier']} (monthly-equiv {rec[f'{P}_monthlyequivalent']:.2f})")
        if DRY:
            continue
        ts = dt.datetime.now(dt.timezone.utc).isoformat()
        body = dict(rec)
        body[f"{P}_freshnessts"] = ts
        body[f"{P}_sourceenv"] = "august-reconcile"
        resp = s.patch(f"{API}/{P}_bills({P}_billkey='{key}')", data=json.dumps(body))
        if resp.status_code >= 400:
            sys.exit(f"UPSERT {key} FAILED: {resp.status_code}\n{resp.text[:600]}")
        a = s.post(f"{API}/{P}_auditlogs", data=json.dumps({
            f"{P}_timestamp": ts, f"{P}_actor": ACTOR, f"{P}_action": "bill.register",
            f"{P}_entitytype": "Bill", f"{P}_entityid": key,
            f"{P}_context": json.dumps({"billkey": key, "after": rec,
                "source": "August 2026 reconcile; identified by John 2026-09-01",
                "not_registered": ["Redmond (1 occurrence, no cadence)",
                                   "Columbia River Naturopath (per-visit, variable)",
                                   "Zoom Management (unidentified)"],
                "requested_by": "John"})[:4000]}))
        if a.status_code >= 400:
            sys.exit(f"AUDIT {key} FAILED: {a.status_code}\n{a.text[:400]}")
        created += 1

    verb = "would create" if DRY else "created"
    print(f"\n  {verb} {len(NEW_BILLS) - skipped if DRY else created}, skipped {skipped}")
    print("  Tier 1 effect: +15.92/mo (AAA). Tier 3 effect: +39.99/mo (Seed).")
    if not DRY and created:
        print("  NEXT: run /api/match.")


if __name__ == "__main__":
    main()
