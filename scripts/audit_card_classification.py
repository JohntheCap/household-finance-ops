"""Read-only coverage audit: how do imported Apple Card rows classify()?

Buckets every applecard-csv non-transfer row by budget category, and lists the
UNTRACKED (None) merchants by total dollars so we can see what is a real coverage
gap (a restaurant/grocer that should map) vs. legitimately-untracked spend (medical,
subscriptions, one-offs, personal care that aren't among the 10 budget categories).

Usage:  py audit_card_classification.py https://org29b77f3e.crm.dynamics.com
"""
import os
import subprocess
import sys
from collections import defaultdict

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "functions"))
import budget as B

ENV_URL = sys.argv[1].rstrip("/")
API = f"{ENV_URL}/api/data/v9.2"
P = "hf"


def main():
    token = subprocess.run(
        ["az", "account", "get-access-token", "--resource", ENV_URL,
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, check=True, shell=True).stdout.strip()
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/json"})

    sel = f"{P}_posteddate,{P}_amount,{P}_merchantraw,{P}_categorydetailed,{P}_istransfer,{P}_isremoved,{P}_sourceenv"
    rows = []
    url = f"{API}/{P}_transactions?$select={sel}&$filter={P}_sourceenv eq 'applecard-csv'"
    while url:
        r = s.get(url); r.raise_for_status(); j = r.json()
        rows.extend(j["value"]); url = j.get("@odata.nextLink")

    by_cat = defaultdict(float)
    untracked = defaultdict(lambda: [0.0, 0])
    total_spend = 0.0
    for t in rows:
        if t.get(f"{P}_isremoved") or t.get(f"{P}_istransfer"):
            continue
        amt = float(t.get(f"{P}_amount") or 0)
        spend = -amt if amt < 0 else 0
        if spend <= 0:
            continue
        total_spend += spend
        merch = t.get(f"{P}_merchantraw") or ""
        cat = B.classify(merch, t.get(f"{P}_categorydetailed"))
        if cat is None:
            key = f"{merch[:34]:<34} [{(t.get(f'{P}_categorydetailed') or '')[:12]}]"
            untracked[key][0] += spend
            untracked[key][1] += 1
        else:
            by_cat[cat] += spend

    tracked = sum(by_cat.values())
    print(f"Imported card spend: ${total_spend:,.0f}  "
          f"tracked ${tracked:,.0f} ({tracked/total_spend*100:.0f}%)  "
          f"untracked ${total_spend-tracked:,.0f} ({(total_spend-tracked)/total_spend*100:.0f}%)\n")
    print("Tracked by category:")
    for c, v in sorted(by_cat.items(), key=lambda x: -x[1]):
        print(f"  {c:<22} ${v:,.0f}")
    print("\nUNTRACKED merchants by $ (candidates to add to RULES, or legit-untracked):")
    for k, (v, n) in sorted(untracked.items(), key=lambda x: -x[1][0]):
        print(f"  ${v:>7,.0f}  x{n:<3} {k}")


if __name__ == "__main__":
    main()
