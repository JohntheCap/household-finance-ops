"""Correction 2026-09-01c: the second August PGE payment is ARREARS, not a bug.

apply_updates_2026-09-01.py filed the 2026-08-24 PGE payment of 200.00 as a
"SEPARATE OPEN ISSUE" implying a matcher defect. John corrected this the same
day: they made two PGE payments in August as BACK PAYMENT on a past-due balance.

The wider history supports him -- this is catch-up behaviour, not a matching gap:
    2026-04  no payment
    2026-05  300.00
    2026-06  300.23 + 325.00   (the 06-29 payment bound to the July cycle)
    2026-07  no payment
    2026-08  180.00 + 200.00

So the matcher is behaving correctly: it binds ONE transaction per cycle, and an
arrears payment is not a cycle. Nothing to fix in the matching layer. What is
genuinely missing is the arrears BALANCE -- an obligation the envelope does not
model, because hf_bill represents recurring cycles, not payoff balances. Sizing
that is John's to supply (see the kickoff checklist).

Appends a clarifying note; does not change any matching behaviour.
Idempotent. Audited. Usage:
  py apply_updates_2026-09-01c.py https://org29b77f3e.crm.dynamics.com [--dry-run]
"""
import datetime as dt, json, subprocess, sys, requests

ENV_URL = sys.argv[1].rstrip("/"); DRY = "--dry-run" in sys.argv
API = f"{ENV_URL}/api/data/v9.2"; P = "hf"
KEY = "electric-pge"
MARKER = "[2026-09-01c arrears]"
NOTE = (f"{MARKER} CORRECTION to the 2026-09-01 note above: the 2026-08-24 "
        "payment of 200.00 is NOT an unmatched cycle or a matcher defect. John "
        "confirms they made two PGE payments in August as back payment on a "
        "past-due balance. History: 2026-04 none, 05 300.00, 06 300.23+325.00, "
        "07 none, 08 180.00+200.00 -- catch-up, not drift. The matcher correctly "
        "binds one transaction per cycle; an arrears payment is not a cycle, so "
        "do NOT widen the match window. OPEN: the arrears BALANCE is not modelled "
        "anywhere -- hf_bill holds recurring cycles, not payoff balances.")


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
        print(f"  == {KEY}: correction already recorded, skip"); return
    print(f"  -> {KEY}: appending arrears correction to notes (no behaviour change)")
    if DRY:
        print("  --dry-run: nothing written"); return
    ts = dt.datetime.now(dt.timezone.utc).isoformat()
    resp = s.patch(f"{API}/{P}_bills({P}_billkey='{KEY}')", data=json.dumps({
        f"{P}_freshnessts": ts,
        f"{P}_notes": f"{NOTE} {(row.get(f'{P}_notes') or '')}".strip()[:4000]}))
    if resp.status_code >= 400:
        sys.exit(f"PATCH FAILED: {resp.status_code}\n{resp.text[:600]}")
    a = s.post(f"{API}/{P}_auditlogs", data=json.dumps({
        f"{P}_timestamp": ts, f"{P}_actor": "apply_updates_2026-09-01c",
        f"{P}_action": "bill.correct_note", f"{P}_entitytype": "Bill",
        f"{P}_entityid": KEY,
        f"{P}_context": json.dumps({"billkey": KEY,
            "correction": "2026-08-24 PGE 200.00 is arrears back-payment, not an unmatched cycle",
            "evidence": "2026-04 none, 05 300.00, 06 300.23+325.00, 07 none, 08 180.00+200.00",
            "source": "John, 2026-09-01"})[:4000]}))
    if a.status_code >= 400:
        sys.exit(f"AUDIT FAILED: {a.status_code}\n{a.text[:400]}")
    print("  corrected + audited")


if __name__ == "__main__":
    main()
