"""Registry correction 2026-08-26 (round 2): Amanda's Amex is paid EXTERNALLY.

Evidence: scanned all 1,128 hf_transaction rows (checking ...0666/...0658, Visa
payment feed, Apple Card CSVs) for amex/american exp/aexp descriptors — zero
hits, across the July 25 and Aug 25 due dates. The $175 minimum never touches
monitored accounts; Amanda pays from her own account. So paymentaccount
"checking" (assumed in round 1) is wrong: set it to "external". matchmode stays
"none" — arrived/missed tracking is impossible until her paying account (or the
Amex itself) joins the Plaid sync.

Idempotent. Audited. Usage:
  py apply_updates_2026-08-26b.py https://org29b77f3e.crm.dynamics.com [--dry-run]
"""
import datetime as dt, json, subprocess, sys, requests

ENV_URL = sys.argv[1].rstrip("/"); DRY = "--dry-run" in sys.argv
API = f"{ENV_URL}/api/data/v9.2"; P = "hf"
KEY = "amex-amanda-payment"
MARKER = "paid externally"
NOTE = ("PAID EXTERNALLY (Amanda's own account): verified 2026-08-26 — zero Amex "
        "descriptors in all 1,128 synced transactions across two due dates, so the "
        "payment never posts to monitored accounts. Tracking requires adding her "
        "paying account or the Amex itself as Plaid Item #2.")


def main():
    tok = subprocess.run(["az","account","get-access-token","--resource",ENV_URL,
        "--query","accessToken","-o","tsv"], capture_output=True, text=True, check=True,
        shell=True).stdout.strip()
    s = requests.Session(); s.headers.update({"Authorization": f"Bearer {tok}",
        "OData-MaxVersion":"4.0","OData-Version":"4.0","Accept":"application/json","Content-Type":"application/json"})
    r = s.get(f"{API}/{P}_bills({P}_billkey='{KEY}')")
    if r.status_code == 404: sys.exit(f"{KEY} NOT FOUND — run apply_updates_2026-08-26.py first")
    row = r.json()
    if MARKER in (row.get(f"{P}_notes") or "").lower():
        print(f"  == {KEY}: already corrected, skip"); return
    print(f"  -> {KEY}: paymentaccount {row.get(f'{P}_paymentaccount')} -> external")
    if DRY: return
    ts = dt.datetime.now(dt.timezone.utc).isoformat()
    before = {f"{P}_paymentaccount": row.get(f"{P}_paymentaccount")}
    patch = {f"{P}_paymentaccount": "external", f"{P}_freshnessts": ts,
             f"{P}_notes": f"{NOTE} {(row.get(f'{P}_notes') or '')}".strip()[:4000]}
    resp = s.patch(f"{API}/{P}_bills({P}_billkey='{KEY}')", data=json.dumps(patch))
    if resp.status_code >= 400: sys.exit(f"PATCH FAILED: {resp.status_code}\n{resp.text[:600]}")
    a = s.post(f"{API}/{P}_auditlogs", data=json.dumps({f"{P}_timestamp":ts,
        f"{P}_actor":"apply_updates_2026-08-26b", f"{P}_action":"bill.correct_paymentaccount",
        f"{P}_entitytype":"Bill", f"{P}_entityid":KEY,
        f"{P}_context":json.dumps({"billkey":KEY,"before":before,
            "after":{f"{P}_paymentaccount":"external"},
            "evidence":"0/1128 synced txns match amex descriptors across 2 due dates",
            "requested_by":"John"})[:4000]}))
    if a.status_code >= 400: sys.exit(f"AUDIT FAILED: {a.status_code}")
    print("  corrected + audited")


if __name__ == "__main__":
    main()
