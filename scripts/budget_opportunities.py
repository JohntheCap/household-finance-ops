"""Dump active bills by tier (monthly-equivalent) to find tightening opportunities."""
import os, subprocess, sys, requests
from collections import defaultdict
ENV_URL = sys.argv[1].rstrip("/"); API = f"{ENV_URL}/api/data/v9.2"; P = "hf"
tok = subprocess.run(["az","account","get-access-token","--resource",ENV_URL,
    "--query","accessToken","-o","tsv"], capture_output=True, text=True, check=True,
    shell=True).stdout.strip()
s = requests.Session(); s.headers.update({"Authorization": f"Bearer {tok}", "Accept":"application/json"})
sel = f"{P}_name,{P}_kind,{P}_tier,{P}_status,{P}_monthlyequivalent,{P}_paymentaccount,{P}_amounttype"
rows, url = [], f"{API}/{P}_bills?$select={sel}&$filter={P}_status eq 'active'"
while url:
    j = s.get(url).json(); rows += j.get("value", []); url = j.get("@odata.nextLink")

tiers = defaultdict(list); income = 0.0
for b in rows:
    me = float(b.get(f"{P}_monthlyequivalent") or 0)
    if b.get(f"{P}_kind") == "income": income += me; continue
    if b.get(f"{P}_kind") != "bill": continue
    tiers[str(b.get(f"{P}_tier"))].append((me, b.get(f"{P}_name"), b.get(f"{P}_amounttype"),
                                           b.get(f"{P}_paymentaccount")))
print(f"Active income: {income:,.2f}/mo\n")
grand = 0.0
for t in ("1","2","3"):
    items = sorted(tiers.get(t, []), reverse=True)
    sub = sum(x[0] for x in items); grand += sub
    label = {"1":"TIER 1 fixed/debt","2":"TIER 2 essential","3":"TIER 3 discretionary"}[t]
    print(f"== {label}: {sub:,.2f}/mo, {len(items)} bills ==")
    for me, name, at, acct in items:
        print(f"   {me:>8.2f}  {name}  [{at}/{acct}]")
    print()
print(f"TOTAL registered bills: {grand:,.2f}/mo")
