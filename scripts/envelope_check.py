"""Compute the live monthly envelope (active income - active Tier 1) for given dates."""
import datetime as dt, os, subprocess, sys, requests
ENV_URL = sys.argv[1].rstrip("/"); API = f"{ENV_URL}/api/data/v9.2"; P = "hf"
DATES = sys.argv[2:] or [dt.date.today().isoformat()]
tok = subprocess.run(["az","account","get-access-token","--resource",ENV_URL,
    "--query","accessToken","-o","tsv"], capture_output=True, text=True, check=True,
    shell=True).stdout.strip()
s = requests.Session(); s.headers.update({"Authorization": f"Bearer {tok}", "Accept":"application/json"})
sel = f"{P}_name,{P}_kind,{P}_tier,{P}_status,{P}_monthlyequivalent,{P}_startdate,{P}_enddate"
bills, url = [], f"{API}/{P}_bills?$select={sel}"
while url:
    j = s.get(url).json(); bills += j.get("value", []); url = j.get("@odata.nextLink")
def d(v): return dt.date.fromisoformat(v[:10]) if v else None
for ds in DATES:
    today = dt.date.fromisoformat(ds); inc=0.0; t1=0.0; lines=[]
    for b in bills:
        if b.get(f"{P}_status")!="active": continue
        kind=b.get(f"{P}_kind"); is_inc=kind=="income"; is_t1=kind=="bill" and str(b.get(f"{P}_tier"))=="1"
        if not (is_inc or is_t1): continue
        st,en = d(b.get(f"{P}_startdate")), d(b.get(f"{P}_enddate"))
        if (st and today<st) or (en and today>en): continue   # honor start/end like compute_envelope
        me=float(b.get(f"{P}_monthlyequivalent") or 0)
        if is_inc: inc+=me; lines.append(f"{b.get(f'{P}_name')} ${me:,.0f}")
        else: t1+=me
    print(f"{ds}: income {inc:,.2f} - Tier1 {t1:,.2f} = ENVELOPE {inc-t1:,.2f}")
    print(f"        in-window income: {', '.join(lines)}")
