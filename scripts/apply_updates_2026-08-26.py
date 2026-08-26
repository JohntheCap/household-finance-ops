"""Registry update 2026-08-26 (John): add Amanda's American Express card debt.

Balance $5,981.16 at 16.4% APR; minimum payment $175/mo due the 25th. At the
minimum alone: ~46-47 payments, payoff ~June/July 2030, ~$2,130 total interest.

Tier 1 fixed (like the other debt payments), so the envelope drops $175/mo.
Match mode starts as "none": we do not yet know which account the payment
leaves from (monitored USAA checking vs Amanda's own account) or the
descriptor. TODO once the next payment posts: confirm the paying account,
set matchmode/matchpattern (Amex ACH usually reads like "AMERICAN EXPRESS ACH
PMT"), so the digest can track arrived/missed.

Idempotent (alternate-key upsert). Audited. Usage:
  py apply_updates_2026-08-26.py https://org29b77f3e.crm.dynamics.com [--dry-run]
"""
import datetime as dt, json, subprocess, sys, requests

ENV_URL = sys.argv[1].rstrip("/"); DRY = "--dry-run" in sys.argv
API = f"{ENV_URL}/api/data/v9.2"; P = "hf"; TODAY = dt.date(2026, 8, 26)
KEY = "amex-amanda-payment"
NOTE = ("Amanda's American Express: balance $5,981.16 as of 2026-08-26, 16.4% APR, "
        "minimum $175/mo due the 25th. At minimum-only: ~46-47 payments, payoff "
        "~June/July 2030, ~$2,130 interest. TODO: confirm which account the payment "
        "posts from and set matchmode/matchpattern after the next payment lands. "
        "Reported by Amanda 2026-08-26.")

REC = {f"{P}_billkey": KEY, f"{P}_name": "Amex payment (Amanda)",
       f"{P}_kind": "bill", f"{P}_tier": "1", f"{P}_status": "active",
       f"{P}_amounttype": "fixed", f"{P}_expectedamount": 175.0,
       f"{P}_monthlyequivalent": 175.0, f"{P}_frequency": "monthly",
       f"{P}_dueday": 25, f"{P}_anchordate": "2026-08-25",
       f"{P}_paymentaccount": "checking", f"{P}_latencydays": 5,
       f"{P}_matchmode": "none", f"{P}_variancetolerancepct": 15,
       f"{P}_notes": NOTE, f"{P}_sourceenv": "registry-update"}


def _do(v): return dt.date.fromisoformat(v[:10]) if v else None


def envelope(bills, today):
    inc = 0.0
    for b in bills:
        if b.get(f"{P}_kind") != "income" or b.get(f"{P}_status") != "active":
            continue
        st, en = _do(b.get(f"{P}_startdate")), _do(b.get(f"{P}_enddate"))
        if (st and today < st) or (en and today > en):
            continue
        inc += float(b.get(f"{P}_monthlyequivalent") or 0)
    t1 = 0.0
    for b in bills:
        if (b.get(f"{P}_kind") != "bill" or str(b.get(f"{P}_tier")) != "1"
                or b.get(f"{P}_status") != "active"):
            continue
        st, en = _do(b.get(f"{P}_startdate")), _do(b.get(f"{P}_enddate"))
        if (st and today < st) or (en and today > en):
            continue
        t1 += float(b.get(f"{P}_monthlyequivalent") or 0)
    return round(inc, 2), round(t1, 2), round(inc - t1, 2)


def main():
    tok = subprocess.run(["az","account","get-access-token","--resource",ENV_URL,
        "--query","accessToken","-o","tsv"], capture_output=True, text=True, check=True,
        shell=True).stdout.strip()
    s = requests.Session(); s.headers.update({"Authorization": f"Bearer {tok}",
        "OData-MaxVersion":"4.0","OData-Version":"4.0","Accept":"application/json","Content-Type":"application/json"})

    def all_bills():
        sel = (f"{P}_billkey,{P}_name,{P}_kind,{P}_tier,{P}_status,"
               f"{P}_monthlyequivalent,{P}_startdate,{P}_enddate")
        out, url = [], f"{API}/{P}_bills?$select={sel}"
        while url:
            j = s.get(url).json(); out += j.get("value", []); url = j.get("@odata.nextLink")
        return out

    bills0 = all_bills()
    i0, t0, e0 = envelope(bills0, TODAY)
    print(f"{'DRY RUN  ' if DRY else ''}Envelope BEFORE: {i0:,.2f} - {t0:,.2f} = {e0:,.2f}")
    existing = next((b for b in bills0 if b.get(f"{P}_billkey") == KEY), None)
    if existing and float(existing.get(f"{P}_monthlyequivalent") or 0) == 175.0:
        print(f"  == {KEY}: already present at $175/mo, skip"); return
    print(f"  -> {KEY}: Tier 1 fixed $175/mo, due 25th (balance $5,981.16 @ 16.4% APR)")
    if DRY:
        return
    ts = dt.datetime.now(dt.timezone.utc).isoformat()
    rec = dict(REC); rec[f"{P}_freshnessts"] = ts
    r = s.patch(f"{API}/{P}_bills({P}_billkey='{KEY}')", data=json.dumps(rec))
    if r.status_code >= 400: sys.exit(f"PATCH FAILED: {r.status_code}\n{r.text[:600]}")
    a = s.post(f"{API}/{P}_auditlogs", data=json.dumps({f"{P}_timestamp":ts,
        f"{P}_actor":"apply_updates_2026-08-26", f"{P}_action":"bill.add_debt",
        f"{P}_entitytype":"Bill", f"{P}_entityid":KEY,
        f"{P}_context":json.dumps({"billkey":KEY,"monthly":175.0,"balance":5981.16,
            "apr_pct":16.4,"due_day":25,"payoff_at_minimum":"~2030-07",
            "requested_by":"John (reported by Amanda)"})[:4000]}))
    if a.status_code >= 400: sys.exit(f"AUDIT FAILED: {a.status_code}")
    i1, t1, e1 = envelope(all_bills(), TODAY)
    print(f"Envelope AFTER: {i1:,.2f} - {t1:,.2f} = {e1:,.2f}  (change {e1-e0:+,.2f})")


if __name__ == "__main__":
    main()
