"""Revert my incorrect Google Fi change and diagnose feed currency.

8696 is John's DEBIT card drawing from the monitored checking account, so Google Fi
IS observable in the Plaid feed (posts ~13th-15th monthly). Restore the correct row:
match_mode=merchant, payment_account=checking, due_day=13, anchor 2026-04-13. Bump
latency to 30 so a normal mid-month post is never prematurely MISSED. Then report the
newest production transaction date (is the feed current?) and any August Google Fi row.
"""
import datetime as dt, json, os, subprocess, sys, requests
ENV_URL = sys.argv[1].rstrip("/"); API = f"{ENV_URL}/api/data/v9.2"; P = "hf"
DRY = "--dry-run" in sys.argv
tok = subprocess.run(["az","account","get-access-token","--resource",ENV_URL,
    "--query","accessToken","-o","tsv"], capture_output=True, text=True, check=True,
    shell=True).stdout.strip()
s = requests.Session(); s.headers.update({"Authorization": f"Bearer {tok}",
    "OData-MaxVersion":"4.0","OData-Version":"4.0","Accept":"application/json","Content-Type":"application/json"})

NOTE = ("Paid via debit card ...8696 out of the monitored USAA checking account, so it "
        "IS observable in the Plaid feed (posts ~13th-15th monthly: Apr 13, May 13, Jun 15, "
        "Jul 14). Statement date (2nd) differs from the debit date. Amount crept up: Jun "
        "$24.52, Jul $24.93, Aug statement $40.14 (watch if this sticks). Corrected 2026-08-23.")
correct = {f"{P}_matchmode":"merchant", f"{P}_paymentaccount":"checking", f"{P}_dueday":13,
           f"{P}_anchordate":"2026-04-13", f"{P}_latencydays":30, f"{P}_notes":NOTE}

b = s.get(f"{API}/{P}_bills({P}_billkey='cell-google-fi')").json()
print("current:", {k: b.get(f"{P}_{k}") for k in ("matchmode","paymentaccount","dueday","latencydays")})
if not DRY:
    ts = dt.datetime.now(dt.timezone.utc).isoformat()
    correct[f"{P}_freshnessts"] = ts
    r = s.patch(f"{API}/{P}_bills({P}_billkey='cell-google-fi')", data=json.dumps(correct))
    r.raise_for_status()
    s.post(f"{API}/{P}_auditlogs", data=json.dumps({f"{P}_timestamp":ts,
        f"{P}_actor":"revert_googlefi", f"{P}_action":"bill.correct",
        f"{P}_entitytype":"Bill", f"{P}_entityid":"cell-google-fi",
        f"{P}_context":json.dumps({"reason":"revert wrong match_mode=none; 8696 is a checking debit card",
            "restored":{"matchmode":"merchant","paymentaccount":"checking","dueday":13,"latencydays":30}})[:4000]}))
    print("reverted + audited")

# Feed currency: newest production transaction overall
r = s.get(f"{API}/{P}_transactions", params={"$select":"hf_posteddate",
    "$filter":"hf_sourceenv eq 'production'","$orderby":"hf_posteddate desc","$top":"1"})
newest = (r.json()["value"] or [{}])[0].get(f"{P}_posteddate")
print(f"\nnewest production txn in feed: {newest}")
# Any August google fi?
r = s.get(f"{API}/{P}_transactions", params={"$select":"hf_posteddate,hf_amount,hf_merchantraw",
    "$filter":"hf_sourceenv eq 'production' and hf_posteddate ge 2026-08-01 and "
              "(contains(hf_merchantraw,'oogle') or contains(hf_merchantraw,'wQ28'))"})
aug = r.json()["value"]
print(f"August Google Fi rows: {len(aug)}  {[ (t.get(f'{P}_posteddate'),t.get(f'{P}_amount')) for t in aug]}")
