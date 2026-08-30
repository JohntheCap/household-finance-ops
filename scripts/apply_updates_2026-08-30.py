"""Registry correction 2026-08-30: neither the Substrate draw nor Oregon UI is real yet.

John reported at the weekly check-in:
  - Substrate owner draw CANNOT start 2026-09-01: the company EIN is still pending
    with the IRS (John follows up Tuesday 2026-09-01). No draw until the EIN lands.
  - Oregon UI is still unpaid; he contacts the agency 2026-08-31 for an update.

Evidence (read-only query of hf_transaction, 2026-06-01 .. 2026-08-30, 59 inflow
rows): ZERO Oregon UI deposits have EVER posted. The $3,908.67/mo UI line has been
inflating the envelope by that amount every month since it was seeded -- August's
headline envelope of $3,831 is overstated by ~$3,909. The back-pay, when it comes,
is a ONE-TIME LUMP and was never meant to be modeled as monthly income (see the
line's own seed note). So the monthly equivalent goes to 0; the row stays for
history and for when the lump lands.

Three coupled changes -- the sweep exists only to bank the draw, so it moves with it:
  1. income-oregon-ui-john       monthlyequivalent 3908.67 -> 0
  2. income-substrate-owner-draw startdate 2026-09-01 -> DRAW_START
  3. savings-sweep-substrate     startdate 2026-09-01 -> DRAW_START

DRAW_START is a PLACEHOLDER, not a forecast. Re-run this script with a new value
(or reset it) the day the EIN arrives and the first draw actually posts.

Idempotent (re-running with the same values is a no-op). Audited (non-negotiable #2).
Usage:
  py apply_updates_2026-08-30.py https://org29b77f3e.crm.dynamics.com [--dry-run]
"""
import datetime as dt, json, subprocess, sys, requests

ENV_URL = sys.argv[1].rstrip("/"); DRY = "--dry-run" in sys.argv
API = f"{ENV_URL}/api/data/v9.2"; P = "hf"

# Placeholder start for the draw AND its dependent savings sweep. John's call.
DRAW_START = "2026-10-01"

STAMP = "EIN-PENDING 2026-08-30"

CHANGES = [
    {"key": "income-oregon-ui-john",
     "patch": {f"{P}_monthlyequivalent": 0.0, f"{P}_expectedamount": 0.0},
     "note": ("NEVER PAID -- verified 2026-08-30: zero Oregon UI deposits in any synced "
              "transaction 2026-06-01..2026-08-30 (59 inflow rows checked). Claim still "
              "unresolved; John contacts the agency 2026-08-31. Monthly equivalent zeroed "
              "because this line was inflating the envelope by $3,908.67/mo for money that "
              "has never arrived. When the agency pays, it is a ONE-TIME BACK-PAY LUMP -- "
              "record it as a transaction, do NOT restore a monthly figure."),
     "why": "no UI deposit has ever posted; monthly line was fiction"},

    {"key": "income-substrate-owner-draw",
     "patch": {f"{P}_startdate": DRAW_START, f"{P}_anchordate": DRAW_START},
     "note": (f"START PUSHED {STAMP}: cannot begin 2026-09-01 -- the Substrate EIN is still "
              f"pending with the IRS (John follows up Tuesday). {DRAW_START} is a PLACEHOLDER, "
              "not a forecast; reset it to the real date once the EIN lands and the first "
              "draw posts to checking."),
     "why": "EIN pending with IRS; draw cannot start 2026-09-01"},

    {"key": "savings-sweep-substrate",
     "patch": {f"{P}_startdate": DRAW_START},
     "note": (f"START PUSHED {STAMP}: this sweep banks the Substrate draw, so it cannot begin "
              f"before the draw does. Moved with income-substrate-owner-draw to {DRAW_START}. "
              "Keep the two dates in lockstep."),
     "why": "sweep banks the draw; must not start before it"},
]


def main():
    print(f"Registry correction 2026-08-30  (DRAW_START={DRAW_START})"
          + ("  [DRY RUN]" if DRY else ""))
    tok = subprocess.run(["az","account","get-access-token","--resource",ENV_URL,
        "--query","accessToken","-o","tsv"], capture_output=True, text=True, check=True,
        shell=True).stdout.strip()
    s = requests.Session(); s.headers.update({"Authorization": f"Bearer {tok}",
        "OData-MaxVersion":"4.0","OData-Version":"4.0","Accept":"application/json",
        "Content-Type":"application/json"})

    ts = dt.datetime.now(dt.timezone.utc).isoformat()
    applied = []
    for c in CHANGES:
        key = c["key"]
        r = s.get(f"{API}/{P}_bills({P}_billkey='{key}')")
        if r.status_code == 404:
            sys.exit(f"{key} NOT FOUND -- registry out of sync, stopping")
        row = r.json()

        before = {k: row.get(k) for k in c["patch"]}
        def norm(v):
            return round(float(v), 2) if isinstance(v, (int, float)) else (str(v)[:10] if v else None)
        if all(norm(before[k]) == norm(v) for k, v in c["patch"].items()):
            print(f"  == {key}: already correct, skip"); continue

        for k, v in c["patch"].items():
            print(f"  -> {key}: {k.replace(P+'_','')} {norm(before[k])} -> {norm(v)}")
        if DRY:
            applied.append(key); continue

        patch = dict(c["patch"])
        patch[f"{P}_freshnessts"] = ts
        existing = (row.get(f"{P}_notes") or "")
        patch[f"{P}_notes"] = f"{c['note']} {existing}".strip()[:4000]
        resp = s.patch(f"{API}/{P}_bills({P}_billkey='{key}')", data=json.dumps(patch))
        if resp.status_code >= 400:
            sys.exit(f"PATCH FAILED on {key}: {resp.status_code}\n{resp.text[:600]}")

        a = s.post(f"{API}/{P}_auditlogs", data=json.dumps({
            f"{P}_timestamp": ts, f"{P}_actor": "apply_updates_2026-08-30",
            f"{P}_action": "bill.correct_income_plan", f"{P}_entitytype": "Bill",
            f"{P}_entityid": key,
            f"{P}_context": json.dumps({"billkey": key, "before": before,
                "after": c["patch"], "reason": c["why"], "requested_by": "John",
                "source": "weekly check-in 2026-08-30"})[:4000]}))
        if a.status_code >= 400:
            sys.exit(f"{key} patched but AUDIT FAILED: {a.status_code}\n{a.text[:500]}")
        applied.append(key)

    if DRY:
        print(f"  --dry-run: nothing written ({len(applied)} row(s) would change)")
    else:
        print(f"  {len(applied)} row(s) corrected + audited")


if __name__ == "__main__":
    main()
