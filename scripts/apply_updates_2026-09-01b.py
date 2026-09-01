"""BUG FIX 2026-09-01b: Google Fi's match pattern hardcodes one month's token.

Not a new feature -- a correctness fix, so it is exempt from the month's
one-improvement cap (OPERATING-CADENCE.md).

Evidence (all 5 observed Google Fi charges):
    2026-04-13  -24.79  "Google FI 74B59B"
    2026-05-13  -25.33  "Google FI PMSHTN"
    2026-06-15  -24.52  "Google FI RBHvMS"
    2026-07-14  -24.93  "FI 44wQ28 g.co/helppay#CA"
    2026-08-14  -40.14  "FI BDSJMH g.co/helppay#CA"

Two things rotate: a random per-month token, AND in July the descriptor format
itself changed from "Google FI <TOKEN>" to "FI <TOKEN> g.co/helppay#CA". The
registered pattern "Google FI|FI 44wQ28" pins July's specific token, so it
matched July by coincidence and matched NOTHING in August -- Google Fi would
have been reported MISSED every month from here on, which is exactly the false
flag the Google Fi tolerance/latency work was meant to stop.

Fix: widen the second alternative from "FI 44wQ28" to the bare prefix "FI ".
Collision check run against the full transaction history: exactly two merchant
strings start with "FI ", and both are Google Fi. matchmode stays "merchant"
(prefix + date window), so a future format change still surfaces rather than
silently binding the wrong row.

NOT changed: expectedamount stays 40.00. Actuals run 24.79-40.14; with the
already-tuned 50% tolerance and 30-day latency, 40.00 covers the whole observed
range. The monthlyequivalent overstates the recent average by roughly $12/mo,
which is conservative in a deficit month -- revisit once there are more months
at the new 40.14 level.

Idempotent. Audited. Usage:
  py apply_updates_2026-09-01b.py https://org29b77f3e.crm.dynamics.com [--dry-run]
"""
import datetime as dt, json, subprocess, sys, requests

ENV_URL = sys.argv[1].rstrip("/"); DRY = "--dry-run" in sys.argv
API = f"{ENV_URL}/api/data/v9.2"; P = "hf"
KEY = "cell-google-fi"
NEW_PATTERN = "Google FI|FI "
MARKER = "[2026-09-01b pattern]"
NOTE = (f"{MARKER} matchpattern 'Google FI|FI 44wQ28' -> 'Google FI|FI '. The "
        "descriptor carries a random per-month token and changed format in July "
        "('Google FI <TOK>' -> 'FI <TOK> g.co/helppay#CA'), so the pinned token "
        "matched July by luck and missed August's -40.14 entirely. Verified only "
        "two merchant strings in the full history start with 'FI ', both Google Fi.")


def main():
    tok = subprocess.run(["az", "account", "get-access-token", "--resource", ENV_URL,
        "--query", "accessToken", "-o", "tsv"], capture_output=True, text=True,
        check=True, shell=True).stdout.strip()
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}", "OData-MaxVersion": "4.0",
        "OData-Version": "4.0", "Accept": "application/json",
        "Content-Type": "application/json"})

    r = s.get(f"{API}/{P}_bills({P}_billkey='{KEY}')")
    if r.status_code >= 400:
        sys.exit(f"GET {KEY} failed: {r.status_code}\n{r.text[:400]}")
    row = r.json()
    if MARKER in (row.get(f"{P}_notes") or ""):
        print(f"  == {KEY}: already applied, skip"); return

    before = row.get(f"{P}_matchpattern")
    print(f"  -> {KEY}: matchpattern {before!r} -> {NEW_PATTERN!r}")
    if DRY:
        print("  --dry-run: nothing written"); return

    ts = dt.datetime.now(dt.timezone.utc).isoformat()
    patch = {f"{P}_matchpattern": NEW_PATTERN, f"{P}_freshnessts": ts,
             f"{P}_notes": f"{NOTE} {(row.get(f'{P}_notes') or '')}".strip()[:4000]}
    resp = s.patch(f"{API}/{P}_bills({P}_billkey='{KEY}')", data=json.dumps(patch))
    if resp.status_code >= 400:
        sys.exit(f"PATCH FAILED: {resp.status_code}\n{resp.text[:600]}")

    a = s.post(f"{API}/{P}_auditlogs", data=json.dumps({
        f"{P}_timestamp": ts, f"{P}_actor": "apply_updates_2026-09-01b",
        f"{P}_action": "bill.fix_matchpattern", f"{P}_entitytype": "Bill",
        f"{P}_entityid": KEY,
        f"{P}_context": json.dumps({"billkey": KEY,
            "before": {f"{P}_matchpattern": before},
            "after": {f"{P}_matchpattern": NEW_PATTERN},
            "evidence": "5 observed charges; token rotates monthly; format changed 2026-07; "
                        "only 2 merchants in history start with 'FI ', both Google Fi",
            "requested_by": "John"})[:4000]}))
    if a.status_code >= 400:
        sys.exit(f"AUDIT FAILED: {a.status_code}\n{a.text[:400]}")
    print("  fixed + audited")
    print("  NEXT: run /api/match so the August cycle rebinds.")


if __name__ == "__main__":
    main()
