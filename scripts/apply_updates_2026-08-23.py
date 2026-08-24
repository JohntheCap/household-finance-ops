"""Registry updates 2026-08-23 (John):
  1. Fabletics -> cancelled (end today).
  2. Milk delivery (Alpenrose/Smith Bros) -> cancelled (end today).
  3. Cell (Google Fi) -> new normal $40/mo (mobile data now; was a work e-SIM);
     budget $40, not to exceed $60, so variance tolerance widened to 50%.
Only Google Fi is Tier 1, so only it moves the envelope (+15.10 to Tier 1).
Every change audited. Idempotent. Usage:
  py apply_updates_2026-08-23.py https://org29b77f3e.crm.dynamics.com [--dry-run]
"""
import datetime as dt, json, os, subprocess, sys, uuid, requests

ENV_URL = sys.argv[1].rstrip("/"); DRY_RUN = "--dry-run" in sys.argv
API = f"{ENV_URL}/api/data/v9.2"; P = "hf"; TODAY = dt.date(2026, 8, 23)
CANCEL = "CANCELLED by John 2026-08-23. No further billing."
GFI = ("New normal ~$40/mo: John now uses Google Fi for mobile data (was on a work "
       "e-SIM). Budget $40, not to exceed $60; variance tolerance widened to 50%. Paid "
       "via debit ...8696 out of monitored checking. Set 2026-08-23.")

CHANGES = [
    {"billkey": "fabletics", "action": "bill.deactivate",
     "set": {f"{P}_status": "cancelled", f"{P}_enddate": "2026-08-23"},
     "name_tag": "(CANCELLED)", "note_prefix": CANCEL,
     "skip_if": lambda r: r.get(f"{P}_status") == "cancelled"},
    {"billkey": "milk-delivery-alpenrose-smith-bros", "action": "bill.deactivate",
     "set": {f"{P}_status": "cancelled", f"{P}_enddate": "2026-08-23"},
     "name_tag": "(CANCELLED)", "note_prefix": CANCEL,
     "skip_if": lambda r: r.get(f"{P}_status") == "cancelled"},
    {"billkey": "cell-google-fi", "action": "bill.update_amount",
     "set": {f"{P}_expectedamount": 40.0, f"{P}_monthlyequivalent": 40.0,
             f"{P}_variancetolerancepct": 50},
     "note_prefix": GFI,
     "skip_if": lambda r: (float(r.get(f"{P}_expectedamount") or 0) == 40.0
                           and float(r.get(f"{P}_monthlyequivalent") or 0) == 40.0
                           and int(r.get(f"{P}_variancetolerancepct") or 0) == 50)},
]


def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
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
    t1 = sum(float(b.get(f"{P}_monthlyequivalent") or 0) for b in bills
             if b.get(f"{P}_kind") == "bill" and str(b.get(f"{P}_tier")) == "1"
             and b.get(f"{P}_status") == "active")
    return round(inc, 2), round(t1, 2), round(inc - t1, 2)


def main():
    tok = subprocess.run(["az","account","get-access-token","--resource",ENV_URL,
        "--query","accessToken","-o","tsv"], capture_output=True, text=True, check=True,
        shell=True).stdout.strip()
    s = requests.Session(); s.headers.update({"Authorization": f"Bearer {tok}",
        "OData-MaxVersion":"4.0","OData-Version":"4.0","Accept":"application/json","Content-Type":"application/json"})

    def all_bills():
        sel = f"{P}_billkey,{P}_name,{P}_kind,{P}_tier,{P}_status,{P}_monthlyequivalent,{P}_startdate,{P}_enddate"
        out, url = [], f"{API}/{P}_bills?$select={sel}"
        while url:
            j = s.get(url).json(); out += j.get("value", []); url = j.get("@odata.nextLink")
        return out

    bills0 = all_bills()
    i0, t0, e0 = envelope(bills0, TODAY)
    print(f"{'DRY RUN  ' if DRY_RUN else ''}Envelope BEFORE: {i0:,.2f} - {t0:,.2f} = {e0:,.2f}")
    # projected
    proj = {b.get(f"{P}_billkey"): dict(b) for b in bills0}
    for ch in CHANGES:
        if ch["billkey"] in proj:
            proj[ch["billkey"]].update(ch["set"])
    ip, tp, ep = envelope(list(proj.values()), TODAY)
    print(f"Envelope PROJECTED: {ip:,.2f} - {tp:,.2f} = {ep:,.2f}  (change {ep-e0:+,.2f}, ~${ep:,.0f})\n")

    ts = now()
    for ch in CHANGES:
        key = ch["billkey"]
        r = s.get(f"{API}/{P}_bills({P}_billkey='{key}')")
        if r.status_code == 404: print(f"  !! {key} NOT FOUND"); continue
        row = r.json()
        if ch["skip_if"](row): print(f"  == {key}: already applied, skip"); continue
        fields = ", ".join(f"{k.split('_',1)[1]}={v}" for k,v in ch["set"].items())
        print(f"  -> {key}: {fields}")
        if DRY_RUN: continue
        before = {k: row.get(k) for k in ch["set"]}
        patch = dict(ch["set"]); patch[f"{P}_freshnessts"] = ts
        if ch.get("name_tag"):
            nm = row.get(f"{P}_name") or ""
            if ch["name_tag"] not in nm: patch[f"{P}_name"] = f"{nm} {ch['name_tag']}".strip()[:120]
        if ch.get("note_prefix"):
            old = row.get(f"{P}_notes") or ""
            if ch["note_prefix"][:20] not in old: patch[f"{P}_notes"] = f"{ch['note_prefix']} {old}".strip()[:4000]
        resp = s.patch(f"{API}/{P}_bills({P}_billkey='{key}')", data=json.dumps(patch))
        if resp.status_code >= 400: sys.exit(f"PATCH FAILED {key}: {resp.status_code}\n{resp.text[:600]}")
        a = s.post(f"{API}/{P}_auditlogs", data=json.dumps({f"{P}_timestamp":ts,
            f"{P}_actor":"apply_updates_2026-08-23", f"{P}_action":ch["action"],
            f"{P}_entitytype":"Bill", f"{P}_entityid":key,
            f"{P}_context":json.dumps({"billkey":key,"before":before,"after":ch["set"],
                "requested_by":"John"})[:4000]}))
        if a.status_code >= 400: sys.exit(f"AUDIT FAILED {key}: {a.status_code}")

    if not DRY_RUN:
        i1, t1, e1 = envelope(all_bills(), TODAY)
        print(f"\nEnvelope AFTER: {i1:,.2f} - {t1:,.2f} = {e1:,.2f}  (change {e1-e0:+,.2f}, ~${e1:,.0f})")


if __name__ == "__main__":
    main()
