"""Add the pay-yourself-first savings sweep as a future-dated Tier 1 line.

John will bank most of the $1,500/week Substrate draw. Modeling a monthly savings
sweep as a Tier 1 "bill" makes the envelope show real lean spending room instead of
the full draw. Managed HERE (not bill_seed_review.csv) because the CSV/seed_bills
carries no start date, and this line MUST start 2026-09-01 (the envelope's Tier 1
now honors startdate) so it does not bite the August envelope.

TARGET is tunable -- change SWEEP and re-run. Idempotent.

Double-count caveat: when the real weekly transfers to savings start posting, they
must be EXCLUDED from variable spend (or they'd be counted once here and again as
spend). That exclusion needs the actual transfer descriptor/destination, captured
once the first sweep posts. Until then this line only sets the plan (base envelope).

Usage: py add_savings_sweep.py https://org29b77f3e.crm.dynamics.com [--dry-run]
"""
import datetime as dt, json, os, subprocess, sys, requests
ENV_URL = sys.argv[1].rstrip("/"); DRY = "--dry-run" in sys.argv
API = f"{ENV_URL}/api/data/v9.2"; P = "hf"
KEY = "savings-sweep-substrate"; SWEEP = 3000.0; START = "2026-09-01"
NOTE = ("PAY YOURSELF FIRST: reserves ~$3,000/mo of the Substrate owner draw to savings "
        "(starts 2026-09-01), so the envelope reflects lean spending room, not the full "
        "$6,500 draw. Target is tunable. Internal transfer, not a biller (match_mode=none). "
        "TODO: once real sweeps post, exclude those transfers from variable spend to avoid "
        "double-counting. Set by John 2026-08-23.")

REC = {f"{P}_billkey": KEY, f"{P}_name": "Savings sweep (Substrate draw)",
       f"{P}_kind": "bill", f"{P}_tier": "1", f"{P}_status": "active",
       f"{P}_amounttype": "fixed", f"{P}_expectedamount": SWEEP, f"{P}_monthlyequivalent": SWEEP,
       f"{P}_frequency": "monthly", f"{P}_startdate": START, f"{P}_paymentaccount": "checking",
       f"{P}_matchmode": "none", f"{P}_notes": NOTE, f"{P}_sourceenv": "savings-config"}


def main():
    tok = subprocess.run(["az","account","get-access-token","--resource",ENV_URL,
        "--query","accessToken","-o","tsv"], capture_output=True, text=True, check=True,
        shell=True).stdout.strip()
    s = requests.Session(); s.headers.update({"Authorization": f"Bearer {tok}",
        "OData-MaxVersion":"4.0","OData-Version":"4.0","Accept":"application/json","Content-Type":"application/json"})
    print(f"savings sweep: ${SWEEP:,.0f}/mo, Tier 1, starts {START}")
    if DRY:
        print("  --dry-run: nothing written"); return
    ts = dt.datetime.now(dt.timezone.utc).isoformat()
    rec = dict(REC); rec[f"{P}_freshnessts"] = ts
    r = s.patch(f"{API}/{P}_bills({P}_billkey='{KEY}')", data=json.dumps(rec))
    if r.status_code >= 400: sys.exit(f"PATCH FAILED: {r.status_code}\n{r.text[:600]}")
    a = s.post(f"{API}/{P}_auditlogs", data=json.dumps({f"{P}_timestamp":ts,
        f"{P}_actor":"add_savings_sweep", f"{P}_action":"bill.add_savings_sweep",
        f"{P}_entitytype":"Bill", f"{P}_entityid":KEY,
        f"{P}_context":json.dumps({"billkey":KEY,"monthly":SWEEP,"start":START,
            "reason":"pay-yourself-first: bank most of the Substrate draw","requested_by":"John"})[:4000]}))
    if a.status_code >= 400: sys.exit(f"AUDIT FAILED: {a.status_code}")
    print("  added + audited")


if __name__ == "__main__":
    main()
