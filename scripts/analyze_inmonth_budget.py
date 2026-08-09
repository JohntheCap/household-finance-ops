"""PROOF-OF-CONCEPT: in-month (MTD) per-category budget with card estimate.

Read-only. Computes, for the current calendar month:
  checking_mtd[cat]  = real, from production checking PURCHASES (excl. transfers)
  card_total_mtd     = real $ total from the Apple Card payments proxy (checking
                       APPLECARD GSBANK PAYMENT rows this month; John zeroes the
                       card ~daily so payments ~= card spend so far)
  card_est[cat]      = card_total_mtd * historical card category mix (from imported
                       applecard-csv statement rows) -- the ESTIMATED split
  spent_mtd[cat]     = checking_mtd + card_est   (+ real current-month card rows if
                       a fresh statement covering this month was imported)

Prints an August-so-far table vs. budget and vs. calendar pace. No writes; this is
a design proof before wiring anything into budget.py / the digest.

Usage:  py analyze_inmonth_budget.py https://org29b77f3e.crm.dynamics.com
"""
import calendar
import datetime as dt
import os
import subprocess
import sys

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "functions"))
import budget as B  # reuse the exact classify() rules + BUDGETS

ENV_URL = sys.argv[1].rstrip("/")
API = f"{ENV_URL}/api/data/v9.2"
P = "hf"
TODAY = dt.date(2026, 8, 9)
MONTH = f"{TODAY:%Y-%m}"


def get(s, path):
    out, url = [], f"{API}/{path}"
    while url:
        r = s.get(url)
        r.raise_for_status()
        j = r.json()
        out.extend(j.get("value", []))
        url = j.get("@odata.nextLink")
    return out


def money(v):
    return f"${v:,.0f}"


def main():
    token = subprocess.run(
        ["az", "account", "get-access-token", "--resource", ENV_URL,
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, check=True, shell=True).stdout.strip()
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}",
                      "OData-MaxVersion": "4.0", "OData-Version": "4.0",
                      "Accept": "application/json"})

    sel = (f"{P}_posteddate,{P}_amount,{P}_merchantraw,{P}_categorydetailed,"
           f"{P}_istransfer,{P}_isremoved,{P}_sourceenv")
    txns = get(s, f"{P}_transactions?$select={sel}")

    cats = [name for name, _ in B.BUDGETS]
    checking_mtd = {c: 0.0 for c in cats}
    card_real_mtd = {c: 0.0 for c in cats}
    card_total_mtd = 0.0          # real card $ this month (payments proxy)
    hist_card = {c: 0.0 for c in cats}
    hist_card_total = 0.0         # all imported card spend (for the mix denominator)

    for t in txns:
        if t.get(f"{P}_isremoved"):
            continue
        pd = (t.get(f"{P}_posteddate") or "")[:10]
        month = pd[:7]
        amt = float(t.get(f"{P}_amount") or 0)
        merch = t.get(f"{P}_merchantraw") or ""
        env = t.get(f"{P}_sourceenv")
        is_tr = t.get(f"{P}_istransfer")
        cat = B.classify(merch, t.get(f"{P}_categorydetailed"))

        if env == "production" and month == MONTH:
            if is_tr and "APPLECARD" in merch.upper():
                card_total_mtd += -amt if amt < 0 else 0    # payment outflow = card $
            elif not is_tr and amt < 0 and cat in checking_mtd:
                checking_mtd[cat] += -amt
        elif env == "applecard-csv" and not is_tr:
            spend = -amt if amt < 0 else 0
            if month == MONTH and cat in card_real_mtd:      # fresh card rows this month
                card_real_mtd[cat] += spend
            elif month < MONTH:                              # history -> category mix
                hist_card_total += spend
                if cat in hist_card:
                    hist_card[cat] += spend

    # Estimated card split of the real card total, using the historical card mix.
    share = {c: (hist_card[c] / hist_card_total if hist_card_total else 0) for c in cats}
    tracked_share = sum(share.values())
    card_est = {c: card_total_mtd * share[c] for c in cats}

    days_total = calendar.monthrange(TODAY.year, TODAY.month)[1]
    pace = TODAY.day / days_total

    print(f"In-month budget -- {TODAY:%B} 1-{TODAY.day} ({TODAY.day}/{days_total} days, "
          f"{pace*100:.0f}% of month)\n")
    print(f"Real card $ so far this month (payments proxy): {money(card_total_mtd)}")
    print(f"  distributed by historical card mix ({tracked_share*100:.0f}% of card spend "
          f"falls in tracked categories; rest is untracked)\n")
    hdr = f"{'Category':<20}{'checking':>10}{'card est':>10}{'= spent':>9}{'budget':>9}{'left':>8}  pace"
    print(hdr)
    print("-" * len(hdr))
    for name, bud in B.BUDGETS:
        chk = checking_mtd[name]
        cd = card_est[name] + card_real_mtd[name]
        spent = chk + cd
        left = bud - spent
        on_pace = bud * pace
        flag = "OVER PACE" if spent > on_pace else "ok"
        print(f"{name:<20}{money(chk):>10}{money(cd):>10}{money(spent):>9}"
              f"{money(bud):>9}{money(left):>8}  {flag}")


if __name__ == "__main__":
    main()
