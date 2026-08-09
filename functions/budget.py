"""Budget review (Sprint 5): month-to-date-style spend vs. per-category budgets.

Retrospective by design: shows the most recent COMPLETE past month -- the latest
month that (a) is fully in the past and (b) has an Apple Card statement imported
(sourceenv 'applecard-csv'). Without the card statement a category's spend is
incomplete, so the whole section stays hidden (John's signed-off choice, 2026-07-24;
same clean_empty vs sync_failed honesty as the rest of the system).

The categories John budgets by (Groceries, Dining, Amazon, ...) are a per-merchant
human mapping -- Plaid's stored categories are too coarse to reproduce them (Fred
Meyer & Walmart groceries look like GENERAL_MERCHANDISE, same as Amazon; groceries
and restaurants share FOOD_AND_DRINK). So classification is merchant-name based,
seeded from Household-Monthly-Nut-v2. Anything unmatched is simply not budget-tracked
(it falls outside these 10 categories); new grocers etc. must be added to RULES.
"""
import calendar
import datetime as dt

P = "hf"

# (display name, monthly budget target) -- human-verified, John 2026-07-24.
BUDGETS = [
    ("Groceries", 1800),
    ("Dining out", 800),
    ("Amazon", 500),
    ("Fuel", 200),
    ("Cash / ATM / Venmo", 300),
    ("Entertainment", 200),
    ("Shopping", 200),
    ("Counseling", 260),
    ("Water delivery", 120),
    ("Kids sports", 150),
]

# Ordered merchant-substring rules; FIRST match wins. Order matters where tokens
# could collide (Fuel's "FRED M FUEL" before Groceries' "FRED MEYER"; Cash's
# "APPLE CASH" is distinct). Substrings are matched uppercased against the raw
# merchant string. Seeded from the workbook's Raw Checking + Raw Apple Card sheets.
RULES = [
    ("Amazon", ("AMAZON", "AMZN")),
    ("Fuel", ("FRED M FUEL", "COSTCO GAS", "WAWA", "CHEVRON", "SHELL", "ARCO",
              "76 -", "APRO LLC", "PHILLIPS 66", "EXXON", "TEXACO", "MARATHON",
              "SPACE AGE", "PACIFIC PRIDE", "CIRCLE K", "FUEL", " GAS ", "ASTRO")),
    ("Groceries", ("ALBERTSONS", "FRED MEYER", "FRED-MEYER", "SAFEWAY", "WALMART",
                   "WINCO", "MARKET OF CHOICE", "WHOLEFDS", "WHOLE FOODS",
                   "PLAID PANTRY", "GROCERY OUTLET", "TRADER JOE", "COSTCO",
                   "THE MEATING PLACE", "HOODLAND", "NEW SEASONS", "QFC", "TARGET",
                   "GROCERY", "SUPERMARKET", "HOLLYWOOD", "GROCERY OUTLET",
                   "NATURAL CATCH", "CITY CENTER FOOD", "LUCKY MART", "FOOD MART")),
    ("Counseling", ("COUNSELING", "HILLSBORO WELLNESS", "MATERIA MEDI",
                    "THERAPY", "LEGACY", "WELLNESS")),
    ("Water delivery", ("PRIMO", "WATERSERV")),
    ("Kids sports", ("HILLSBORO RUSH", "REEDVILLE BASEBALL", "HILLSBORO PARKS",
                     "CAPELLI SPORT", "CAPTYN", "BIG WAVE", "LITTLE LEAGUE",
                     "PARKS OR", " SWIM", "SOCCER")),
    ("Cash / ATM / Venmo", ("VENMO", "ZELLE", "APPLE CASH", " ATM", "ATMP",
                            "PAI ATM", "VISA DIRECT", "CASH APP", "CASHAPP",
                            "WITHDRAWAL")),
    ("Dining out", ("POKE", "BEER CART", "EINSTEIN", "HOP N CORK", "MUNCH",
                    "PACIFIC BLENDS", "TACO BELL", "HALES", "GRUBHUB", "DOORDASH",
                    "UBER EATS", "ASIAN KITCHEN", "JERSEY MIKE", "STARBUCKS",
                    "JAMBA", "KFC", "MCDONALD", "CHIPOTLE", "PANDA EXPRESS",
                    "DUTCH BROS", "TST*", "GOSQ.COM", "SQ *", "OLD CHICAGO",
                    "RESTAURANT", "PIZZA", "SUSHI", "BAGEL", "COFFEE", "BREWING",
                    "TAQUERIA", "CAFE", "GRILL", "BAR ", "KITCHEN", "DELI",
                    "BURGER", "CENTURY BEER", "SUBS", "DINER")),
    ("Entertainment", ("PUMPKIN PATCH", "BRIDGEPORT", "EVERGREEN 13", "STEAM",
                       "PARK LANES", "LANGER", "REGAL", "CINEMA", "PINBALL",
                       "FUNDAY", "BOWLING", "ARCADE", "THEATER", "THEATRE",
                       "MUSEUM", " ZOO", "AMC ", "REG EVERGREEN", "GOLF")),
    ("Shopping", ("ROCKET 5457", "DOLLARTREE", "DOLLAR TREE", "FAMOUSFOOTWEAR",
                  "FAMOUS FOOTWEAR", "PETCO", "PETSMART", "BURLINGTON", "ROSS",
                  "OLD NAVY", "KOHL", "MARSHALL", "TJ MAXX", "NORDSTROM",
                  "DICK'S", "DICKS SPORTING", "HOMEGOODS")),
]


# Food-category merchants that are NOT dining (meal kits, milk delivery). Without
# this the coarse food-category fallback would sweep them into Dining out.
EXCLUDE = ("HOME CHEF", "ALPENROSE", "SMITH BROS", "HELLOFRESH", "BLUE APRON")


def classify(merchant, detailed=None):
    """Return the budget category for a merchant, or None if not budget-tracked.

    Merchant name wins (RULES, first match). For anything unmatched, fall back to
    the Plaid/Apple category (`detailed`): restaurants are endlessly named, so a
    food-category txn that wasn't already claimed as groceries by name is dining.
    """
    m = (merchant or "").upper()
    if any(x in m for x in EXCLUDE):
        return None
    for name, subs in RULES:
        if any(s in m for s in subs):
            return name
    d = (detailed or "").upper()
    if ("RESTAURANT" in d or "FAST_FOOD" in d or "COFFEE" in d or "BEER_WINE" in d
            or "ALCOHOL" in d or ("FOOD_AND_DRINK" in d and "GROCER" not in d)):
        # Apple tags wineries/liquor "Alcohol"; the household budgets dining & alcohol
        # together, so they land in Dining out (nut's "Dining & alcohol" grouping).
        return "Dining out"
    if d == "GAS":                       # Apple "Gas" for stations not caught by name
        return "Fuel"
    return None


def _covered_months(txns):
    """Set of 'YYYY-MM' that have at least one imported Apple Card statement row."""
    return {(t.get(f"{P}_posteddate") or "")[:7]
            for t in txns if t.get(f"{P}_sourceenv") == "applecard-csv"
            and t.get(f"{P}_posteddate")}


def pick_month(txns, today):
    """Latest fully-past month that has an Apple Card statement imported, else None."""
    cur = f"{today:%Y-%m}"
    past_covered = sorted(m for m in _covered_months(txns) if m and m < cur)
    return past_covered[-1] if past_covered else None


def _month_label(ym):
    y, m = ym.split("-")
    return f"{dt.date(int(y), int(m), 1):%B %Y}"


def compute(txns, today):
    """Aggregate spend per budget category for the retrospective month.

    Returns {shown, month, month_label, rows:[{name,budget,spent,pct,over}],
    any_over, empty_reason}. shown=False (with empty_reason) until a card statement
    for a complete past month is imported.
    """
    month = pick_month(txns, today)
    if not month:
        return {"shown": False, "month": None,
                "empty_reason": "awaiting_applecard_statement"}

    spent = {name: 0.0 for name, _ in BUDGETS}
    for t in txns:
        if t.get(f"{P}_isremoved") or t.get(f"{P}_istransfer"):
            continue
        if (t.get(f"{P}_posteddate") or "")[:7] != month:
            continue
        amt = float(t.get(f"{P}_amount") or 0)
        cat = classify(t.get(f"{P}_merchantraw"), t.get(f"{P}_categorydetailed"))
        if cat not in spent:
            continue
        if amt >= 0:                      # income/refunds net down spend
            spent[cat] -= amt
        else:
            spent[cat] += -amt

    rows = []
    for name, budget in BUDGETS:
        s = max(0.0, round(spent[name], 2))
        pct = (s / budget) if budget else 0
        rows.append({"name": name, "budget": budget, "spent": s,
                     "pct": pct, "over": s > budget})
    return {"shown": True, "month": month, "month_label": _month_label(month),
            "rows": rows, "any_over": any(r["over"] for r in rows),
            "empty_reason": None}


# ---- In-month (MTD) budget: the "how much is left THIS month" view -----------
# The retrospective compute() above is the reconciled truth for a closed month.
# This is the live, in-progress companion John asked for: how much of each budget
# has been spent so far this calendar month, so "how much is left" is answerable
# before the month closes.
#
# Data honesty (the whole point): checking purchases are REAL in-month (Plaid). Card
# purchases are not itemized until the monthly statement, so the card slice of each
# category is:
#   - REAL where a statement covering this month has been imported (applecard-csv), and
#   - ESTIMATED for the rest, from that category's OWN recent card history prorated to
#     how far into the month we are. Per-category (not a split of the volatile card
#     total) so a travel/one-off month doesn't inflate groceries or dining.
# The estimated portion is surfaced explicitly -- an understated dining figure must
# never read as confirmed fact (R13 applied to the budget).

def compute_inmonth(txns, today):
    """Month-to-date spend per budget category, checking-real + card-estimated.

    Returns {shown, month_label, day, days_total, pace, rows:[{name, budget, spent,
    checking, card, card_est, pct, over, pace_target}], est_total, real_total,
    est_share, any_over, empty_reason}.
    """
    month = f"{today:%Y-%m}"
    cats = [name for name, _ in BUDGETS]
    checking = {c: 0.0 for c in cats}
    card_real = {c: 0.0 for c in cats}
    hist_card = {c: 0.0 for c in cats}
    hist_months, any_prod_this_month = set(), False

    for t in txns:
        if t.get(f"{P}_isremoved") or t.get(f"{P}_istransfer"):
            continue
        m = (t.get(f"{P}_posteddate") or "")[:7]
        if not m:
            continue
        env = t.get(f"{P}_sourceenv")
        amt = float(t.get(f"{P}_amount") or 0)
        spend = -amt                      # outflow(<0) -> positive spend; refund nets down
        cat = classify(t.get(f"{P}_merchantraw"), t.get(f"{P}_categorydetailed"))

        if env == "applecard-csv" and m < month:
            hist_months.add(m)            # a month with card detail imported
            if cat in hist_card and amt < 0:
                hist_card[cat] += -amt
            continue
        if cat not in checking:
            continue
        if env == "production" and m == month:
            checking[cat] += spend
            any_prod_this_month = True
        elif env == "applecard-csv" and m == month:
            card_real[cat] += spend

    n_hist = len(hist_months) or 1
    days_total = calendar.monthrange(today.year, today.month)[1]
    pace = today.day / days_total

    rows, est_total, real_total = [], 0.0, 0.0
    for name, bud in BUDGETS:
        chk = max(0.0, round(checking[name], 2))
        cr = max(0.0, round(card_real[name], 2))
        # Estimate the card spend not yet itemized: this category's typical monthly
        # card spend, prorated to the month elapsed, less any card rows already in.
        avg_card = hist_card[name] / n_hist
        est = max(0.0, round(avg_card * pace - cr, 2))
        card = round(cr + est, 2)
        spent = round(chk + card, 2)
        est_total += est
        real_total += chk + cr
        rows.append({"name": name, "budget": bud, "spent": spent,
                     "checking": chk, "card": card, "card_est": est,
                     "pct": (spent / bud) if bud else 0, "over": spent > bud,
                     "pace_target": round(bud * pace, 2)})

    if not any_prod_this_month and est_total == 0:
        return {"shown": False, "month_label": _month_label(month),
                "empty_reason": "no_month_data_yet"}

    denom = real_total + est_total
    return {"shown": True, "month_label": _month_label(month),
            "day": today.day, "days_total": days_total, "pace": pace,
            "rows": rows, "est_total": round(est_total, 2),
            "real_total": round(real_total, 2),
            "est_share": (est_total / denom) if denom else 0,
            "any_over": any(r["over"] for r in rows),
            "card_estimated": est_total > 0, "empty_reason": None}


# ---- Rendering (Outlook-safe: table/bgcolor bars, no chained selectors) ----

def _money(v):
    return f"${v:,.0f}"


def render_section(b):
    """Full <div class='sec'> for the digest, or '' if not shown."""
    if not b.get("shown"):
        return ""
    cats = ""
    for r in b["rows"]:
        pct = r["pct"]
        fill = min(100, round(pct * 100))
        if r["over"]:
            amt_html = (f'<span class="cat-amt over">{_money(r["spent"])} '
                        f'<span class="cat-of over">of {_money(r["budget"])} &middot; '
                        f'over {_money(r["spent"] - r["budget"])}</span></span>')
            bar = f'<table class="bar"><tr><td bgcolor="#c0392b" width="100%"></td></tr></table>'
        else:
            amt_html = (f'<span class="cat-amt">{_money(r["spent"])} '
                        f'<span class="cat-of">of {_money(r["budget"])}</span></span>')
            rest = 100 - fill
            bar = (f'<table class="bar"><tr>'
                   f'<td bgcolor="#1e7d45" width="{fill}%"></td>'
                   + (f'<td bgcolor="#e4e8ee" width="{rest}%"></td>' if rest > 0 else "")
                   + f'</tr></table>')
        cats += (f'<div class="cat"><div class="cat-top">'
                 f'<span class="cat-name">{r["name"]}</span>{amt_html}</div>{bar}</div>')

    return (f'<div class="sec"><h3>Budget review &mdash; {b["month_label"]}</h3>'
            f'<div class="budget-note">Last complete month (Apple Card statement in). '
            f'Green = under budget, red = over.</div>{cats}</div>')


def render_inmonth_section(b):
    """In-month MTD budget: a spend/budget bar per category with a pace marker, and
    an explicit note wherever card spend is estimated (never let an estimate read as
    fact). '' if not shown."""
    if not b.get("shown"):
        return ""
    cats = ""
    for r in b["rows"]:
        fill = min(100, round(r["pct"] * 100))
        if r["over"]:
            amt_html = (f'<span class="cat-amt over">{_money(r["spent"])} '
                        f'<span class="cat-of over">of {_money(r["budget"])} &middot; '
                        f'over {_money(r["spent"] - r["budget"])}</span></span>')
            bar = '<table class="bar"><tr><td bgcolor="#c0392b" width="100%"></td></tr></table>'
        else:
            amt_html = (f'<span class="cat-amt">{_money(r["spent"])} '
                        f'<span class="cat-of">of {_money(r["budget"])} &middot; '
                        f'{_money(r["budget"] - r["spent"])} left</span></span>')
            rest = 100 - fill
            bar = (f'<table class="bar"><tr>'
                   f'<td bgcolor="#1e7d45" width="{fill}%"></td>'
                   + (f'<td bgcolor="#e4e8ee" width="{rest}%"></td>' if rest > 0 else "")
                   + '</tr></table>')
        est_line = ""
        if r["card_est"] >= 5:
            est_line = (f'<div class="cat-of" style="margin-top:2px">'
                        f'includes ~{_money(r["card_est"])} estimated card spend</div>')
        cats += (f'<div class="cat"><div class="cat-top">'
                 f'<span class="cat-name">{r["name"]}</span>{amt_html}</div>{bar}'
                 f'{est_line}</div>')

    pct_month = round(b["pace"] * 100)
    if b.get("card_estimated"):
        note = (f'{b["month_label"]}, day {b["day"]} of {b["days_total"]} ({pct_month}% in). '
                f'Checking is live; card spend is partly estimated from recent months until '
                f'the statement imports (~{round(b["est_share"]*100)}% of the total shown). '
                f'&ldquo;left&rdquo; = budget minus spent so far.')
    else:
        note = (f'{b["month_label"]}, day {b["day"]} of {b["days_total"]} ({pct_month}% in). '
                f'&ldquo;left&rdquo; = budget minus spent so far.')

    return (f'<div class="sec"><h3>This month so far &mdash; {b["month_label"]}</h3>'
            f'<div class="budget-note">{note}</div>{cats}</div>')
