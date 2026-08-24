"""Diagnostic: find Google Fi charges in the synced checking feed + show the bill row."""
import os, subprocess, sys, requests
ENV_URL = sys.argv[1].rstrip("/"); API = f"{ENV_URL}/api/data/v9.2"; P = "hf"
tok = subprocess.run(["az","account","get-access-token","--resource",ENV_URL,
    "--query","accessToken","-o","tsv"], capture_output=True, text=True, check=True,
    shell=True).stdout.strip()
s = requests.Session(); s.headers.update({"Authorization": f"Bearer {tok}", "Accept":"application/json"})

# Bill row
b = s.get(f"{API}/{P}_bills({P}_billkey='cell-google-fi')").json()
print("BILL cell-google-fi:",
      {k: b.get(f"{P}_{k}") for k in ("matchmode","paymentaccount","dueday","anchordate",
       "matchpattern","expectedamount","monthlyequivalent","variancetolerancepct")})

# Any transaction that looks like Google Fi (case-insensitive contains)
flt = ("(contains(hf_merchantraw,'oogle') or contains(hf_merchantraw,'wQ28') "
       "or contains(hf_merchantraw,'GOOGLE FI'))")
r = s.get(f"{API}/{P}_transactions",
          params={"$select":"hf_posteddate,hf_amount,hf_merchantraw,hf_sourceenv,hf_istransfer,hf_isremoved",
                  "$filter":flt, "$orderby":"hf_posteddate desc"})
r.raise_for_status()
rows = r.json()["value"]
print(f"\n{len(rows)} matching transaction(s):")
for t in rows[:25]:
    print(f"  {t.get(f'{P}_posteddate')}  {float(t.get(f'{P}_amount') or 0):>8.2f}  "
          f"env={t.get(f'{P}_sourceenv')}  tr={t.get(f'{P}_istransfer')}  rm={t.get(f'{P}_isremoved')}  "
          f"| {t.get(f'{P}_merchantraw')}")

# Google Fi instances (what the matcher produced)
inst = s.get(f"{API}/{P}_billinstances",
    params={"$select":"hf_instancekey,hf_duedate,hf_status,hf_expectedamount,hf_actualamount,hf_notes",
            "$filter":"hf_billkey eq 'cell-google-fi'","$orderby":"hf_duedate desc"}).json()["value"]
print(f"\n{len(inst)} bill instance(s):")
for i in inst[:8]:
    print(f"  {i.get(f'{P}_duedate')}  {i.get(f'{P}_status')}  exp={i.get(f'{P}_expectedamount')}  "
          f"act={i.get(f'{P}_actualamount')}  | {(i.get(f'{P}_notes') or '')[:60]}")
