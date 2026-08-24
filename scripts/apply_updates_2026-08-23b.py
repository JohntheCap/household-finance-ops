"""Registry updates 2026-08-23 (round 2, John):
  - Harris & Harris: record ~$1,500 balance remaining (no amount change; ~11 mo left).
  - Apple services (card side): Apple One cancelled -> iCloud+Apple Music $29.97 (was
    $39.99), so -$10.02/mo. AppleCare (Amanda) $13.99 and YouTube Premium $18.99 stay.
  - Xbox/Microsoft (card side): Game Pass ($14.99) cancelled, -$14.99/mo.
Tier 3 items don't move the envelope; this keeps the registry truthful. All audited.
Usage: py apply_updates_2026-08-23b.py https://org29b77f3e.crm.dynamics.com [--dry-run]
"""
import datetime as dt, json, os, subprocess, sys, requests
ENV_URL = sys.argv[1].rstrip("/"); DRY = "--dry-run" in sys.argv
API = f"{ENV_URL}/api/data/v9.2"; P = "hf"

UPDATES = [
    {"key": "harris-harris", "action": "bill.note",
     "set": {}, "marker": "Balance ~$1,500",
     "note": "Balance ~$1,500 remaining as of 2026-08-23 (John): about 11 months left at $137.50/mo."},
    {"key": "apple-services-card-side", "action": "bill.update_amount",
     "set": {f"{P}_expectedamount": 72.22, f"{P}_monthlyequivalent": 72.22},
     "marker": "Apple One cancelled",
     "note": "Apple One cancelled 2026-08-23; now iCloud + Apple Music $29.97/mo (was $39.99). "
             "AppleCare (Amanda's phone) $13.99/mo and YouTube Premium $18.99/mo retained."},
    {"key": "xbox-microsoft-card-side", "action": "bill.update_amount",
     "set": {f"{P}_expectedamount": 7.17, f"{P}_monthlyequivalent": 7.17},
     "marker": "Game Pass ($14.99) cancelled",
     "note": "Xbox Game Pass ($14.99/mo) cancelled 2026-08-23; remainder is store purchases."},
]


def main():
    tok = subprocess.run(["az","account","get-access-token","--resource",ENV_URL,
        "--query","accessToken","-o","tsv"], capture_output=True, text=True, check=True,
        shell=True).stdout.strip()
    s = requests.Session(); s.headers.update({"Authorization": f"Bearer {tok}",
        "OData-MaxVersion":"4.0","OData-Version":"4.0","Accept":"application/json","Content-Type":"application/json"})
    ts = dt.datetime.now(dt.timezone.utc).isoformat()
    for u in UPDATES:
        r = s.get(f"{API}/{P}_bills({P}_billkey='{u['key']}')")
        if r.status_code == 404: print(f"  !! {u['key']} NOT FOUND"); continue
        row = r.json()
        if u["marker"] in (row.get(f"{P}_notes") or ""):
            print(f"  == {u['key']}: already applied, skip"); continue
        desc = ", ".join(f"{k.split('_',1)[1]}={v}" for k,v in u["set"].items()) or "note only"
        print(f"  -> {u['key']}: {desc}")
        if DRY: continue
        before = {k: row.get(k) for k in u["set"]}
        patch = dict(u["set"]); patch[f"{P}_freshnessts"] = ts
        patch[f"{P}_notes"] = f"{u['note']} {(row.get(f'{P}_notes') or '')}".strip()[:4000]
        resp = s.patch(f"{API}/{P}_bills({P}_billkey='{u['key']}')", data=json.dumps(patch))
        if resp.status_code >= 400: sys.exit(f"PATCH FAILED {u['key']}: {resp.status_code}\n{resp.text[:600]}")
        a = s.post(f"{API}/{P}_auditlogs", data=json.dumps({f"{P}_timestamp":ts,
            f"{P}_actor":"apply_updates_2026-08-23b", f"{P}_action":u["action"],
            f"{P}_entitytype":"Bill", f"{P}_entityid":u["key"],
            f"{P}_context":json.dumps({"billkey":u["key"],"before":before,"after":u["set"],
                "note":u["note"][:120],"requested_by":"John"})[:4000]}))
        if a.status_code >= 400: sys.exit(f"AUDIT FAILED {u['key']}: {a.status_code}")
    if not DRY: print("done")


if __name__ == "__main__":
    main()
