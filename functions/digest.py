"""Weekly digest: assemble + render (Sprint 4, shared by preview and production).

Reader-injected so the same logic serves both callers with different auth:
  - scripts/build_digest.py  (local preview, az-login session)
  - function_app.weekly_digest  (production, Dataverse client-secret + timer)
`get(path)` returns a list of Dataverse records; `assemble` and `render` are pure.

Signed-off scope (John, 2026-07-24): paid this week / coming up / needs attention
(MISSED only, no routine drift) / nut status (minimum nut vs income-still-active).
Amanda-first: no jargon, decision-first, never cry wolf.

Data honesty (R13 applied to the reader): the digest may NOT say "all clear" if the
sync is stale or failed; empty sections carry an explicit empty_reason.
"""
import datetime as dt
import re

P = "hf"

try:                                    # budget review (Sprint 5) is optional
    import budget as _budget
except Exception:                       # noqa: BLE001
    _budget = None

# ---- Human-verified config (NOT recomputed from the registry) -------------
# Minimum nut and income come from John's monthly-nut analysis; variable-category
# amounts in hf_bill are per-transaction medians and would badly understate the
# nut. Update when the analysis or the UI benefit firms up. Derived 2026-07-24
# from Household-Monthly-Nut-v2 (tier1+tier2 active; blanks = Apr-Jun actual avg).
MINIMUM_NUT = 7754.23           # tier 1 (fixed/debt) 4707.54 + tier 2 (essential) 3046.69
INCOME_ACTIVE = [
    ("VA disability", 1256.90),
    ("Amanda (Viking Vet)", 3486.24),
    ("Oregon UI (John)", 3908.67),   # PLACEHOLDER until the award letter confirms
]

STALE_HOURS = 48                # freshness older than this => amber, never "all clear"
UPCOMING_DAYS = 10
PAID_WINDOW_DAYS = 7


def _parse_ts(ts):
    if not ts:
        return None
    try:
        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _clean_name(instance_name):
    """Instance names are '<bill> YYYY-MM'; strip the cycle tag for display."""
    return re.sub(r"\s+\d{4}-\d{2}$", "", instance_name or "").strip()


# ---- Assembly (S4.1) ------------------------------------------------------

def assemble(get, today, recipient_to, recipient_cc, now=None):
    """Read live state and produce the digest payload. No writes."""
    now = now or dt.datetime.now(dt.timezone.utc)
    instances = get(f"{P}_billinstances?$select={P}_name,{P}_billkey,{P}_status,"
                    f"{P}_duedate,{P}_paiddate,{P}_expectedamount,{P}_actualamount,"
                    f"{P}_variancepct,{P}_notes,{P}_freshnessts")
    accounts = get(f"{P}_accounts?$select={P}_name,{P}_freshnessts,{P}_sourceenv")
    items = get(f"{P}_plaiditems?$select={P}_label,{P}_active,{P}_lastsyncstatus,{P}_lastsyncts")
    txns = (get(f"{P}_transactions?$select={P}_posteddate,{P}_amount,{P}_merchantraw,"
                f"{P}_categorydetailed,{P}_istransfer,{P}_isremoved,{P}_sourceenv")
            if _budget else [])

    # Freshness / health gate (R13): any active item not 'ok', or any production
    # account staler than STALE_HOURS, blocks the green "all clear" state.
    active_items = [i for i in items if i.get(f"{P}_active")]
    sync_ok = all((i.get(f"{P}_lastsyncstatus") or "").startswith("ok") for i in active_items)
    freshness = [_parse_ts(a.get(f"{P}_freshnessts")) for a in accounts
                 if a.get(f"{P}_sourceenv") == "production"]
    freshness = [f for f in freshness if f]
    oldest = min(freshness) if freshness else None
    stale = (not sync_ok) or (oldest is None) or ((now - oldest).total_seconds() > STALE_HOURS * 3600)
    source_env = accounts[0].get(f"{P}_sourceenv") if accounts else "unknown"
    fresh_ts = oldest.isoformat() if oldest else None

    def meta(value_count, empty_reason=None, confidence="high"):
        return {"freshness_ts": fresh_ts, "confidence": confidence, "source_env": source_env,
                "empty_reason": (empty_reason if value_count == 0 else None)}

    paid_from = today - dt.timedelta(days=PAID_WINDOW_DAYS)
    upcoming_to = today + dt.timedelta(days=UPCOMING_DAYS)

    paid, upcoming = [], []
    missed_by_bill, pending_by_bill = {}, {}
    for r in instances:
        status = r.get(f"{P}_status")
        due = r.get(f"{P}_duedate")
        paid_date = r.get(f"{P}_paiddate")
        billkey = r.get(f"{P}_billkey") or ""
        name = _clean_name(r.get(f"{P}_name"))
        exp = float(r.get(f"{P}_expectedamount") or 0)
        act = r.get(f"{P}_actualamount")
        act = float(act) if act is not None else None

        if status in ("arrived", "drifted") and paid_date:
            pd = dt.date.fromisoformat(paid_date[:10])
            if paid_from <= pd <= today:
                paid.append({"name": name, "date": pd, "amount": act if act is not None else exp})
        elif status == "upcoming" and due:
            dd = dt.date.fromisoformat(due[:10])
            if today <= dd <= upcoming_to:
                upcoming.append({"name": name, "date": dd, "amount": exp})
        elif status == "missed":
            # Attention is MISSED only -- drift is deliberately excluded (over-
            # surfacing trains the reader to ignore the digest). Grouped by bill.
            dd = dt.date.fromisoformat(due[:10]) if due else None
            m = missed_by_bill.setdefault(billkey, {"name": name, "amount": exp,
                                                    "count": 0, "latest": dd})
            m["count"] += 1
            if dd and (m["latest"] is None or dd > m["latest"]):
                m["latest"] = dd
        elif status == "unobservable":
            pending_by_bill[billkey] = name

    paid.sort(key=lambda x: x["date"])
    upcoming.sort(key=lambda x: x["date"])
    missed = sorted(missed_by_bill.values(), key=lambda m: m["latest"] or today, reverse=True)
    pending_stmt = sorted(set(pending_by_bill.values()))

    income_total = sum(a for _, a in INCOME_ACTIVE)
    gap = income_total - MINIMUM_NUT

    budget_payload = (_budget.compute(txns, today) if _budget
                      else {"shown": False, "empty_reason": "budget_module_missing"})

    return {
        "generated_at": now.isoformat(),
        "asof": today.isoformat(),
        "stale": stale,
        "recipient_to": recipient_to,
        "recipient_cc": recipient_cc,
        "sync": {"ok": sync_ok, "oldest_account": fresh_ts,
                 "items": [(i.get(f"{P}_label"), i.get(f"{P}_lastsyncstatus")) for i in active_items]},
        "paid": {"items": paid, "total": round(sum(p["amount"] for p in paid), 2),
                 "meta": meta(len(paid), "clean_empty")},
        "upcoming": {"items": upcoming, "total": round(sum(u["amount"] for u in upcoming), 2),
                     "meta": meta(len(upcoming), "clean_empty")},
        "attention": {"missed": missed, "pending_statement": pending_stmt,
                      "meta": meta(len(missed),
                                   "awaiting_applecard_statement" if pending_stmt else "clean_empty")},
        "nut": {"minimum": MINIMUM_NUT, "income": income_total, "gap": round(gap, 2),
                "income_lines": INCOME_ACTIVE, "covered": gap >= 0,
                "meta": {"freshness_ts": fresh_ts, "confidence": "config",
                         "source_env": "monthly-nut-v2", "empty_reason": None}},
        "budget": budget_payload,
    }


# ---- Rendering (S4.2) -----------------------------------------------------
# "Burly" heraldic styling: navy + gold crest bands bookend a clean, readable body.
# The chrome is heavier; the information is not louder (Amanda-first). render() is
# the real email body; render_preview() wraps it with a gating note for local review
# and is NEVER emailed.
try:                                    # asset is optional -- never break the digest
    from crest_asset import CREST_DATA_URI
except Exception:                       # noqa: BLE001
    CREST_DATA_URI = ""


def _money(v):
    return f"${v:,.0f}" if abs(v) >= 100 else f"${v:,.2f}"


def _fmt_date(d):
    return f"{d:%a} {d:%b} {d.day}" if d else "TBD"        # avoid %-d (non-portable)


def _fmt_full(d):
    return f"{d:%B} {d.day}, {d.year}"


def _fmt_gen(ts):
    if not ts:
        return "?"
    h = ts.hour % 12 or 12
    return f"{ts:%a} {h}:{ts:%M} {ts:%p} UTC"


def subject(payload):
    return ("⚠ Sunday check-in — needs a look" if payload["stale"]
            else "☀ Sunday check-in")


_CSS = """
*{box-sizing:border-box;-webkit-text-size-adjust:100%}
body{margin:0;background:#eceff3;font-family:-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:#1a2332;line-height:1.45;padding:22px 14px 44px}
.card{max-width:460px;margin:0 auto;background:#fff;border:1px solid #d3dae4;border-radius:16px;overflow:hidden;box-shadow:0 10px 34px rgba(14,26,53,.14)}
.crest-band{background:#0E1A35;background:linear-gradient(160deg,#16294d 0%,#0a1530 100%);padding:24px 20px 18px;text-align:center;border-bottom:4px solid #C8A24B}
.crest-img{width:92px;height:92px;display:block;margin:0 auto 8px;border-radius:50%;border:2px solid rgba(200,162,75,.45)}
.house{font-family:Georgia,"Times New Roman",serif;font-size:18px;font-weight:700;letter-spacing:.11em;color:#EBDCA9;margin:2px 0 0;text-transform:uppercase}
.motto{font-family:Georgia,"Times New Roman",serif;font-style:italic;font-size:12px;color:#B99B54;letter-spacing:.02em;margin:3px 0 0}
.band-rule{height:2px;width:54px;background:#C8A24B;margin:11px auto 9px;opacity:.75;border-radius:2px}
.kicker{font-size:11px;letter-spacing:.15em;text-transform:uppercase;color:#93a6c6;margin:0;font-weight:600}
.body{padding:18px 18px 8px}
.lead{font-size:15px;font-weight:700;color:#0E1A35;margin:0 0 13px}
.stale-banner{background:#fdf2d4;border:2px solid #ecd08f;border-radius:11px;padding:12px 14px;font-size:13px;margin:0 0 16px;font-weight:600;color:#6f4e12}
.stale-banner b{color:#8a5a00}
.hero{border-radius:13px;padding:16px 18px;margin-bottom:20px}
.hero .label{font-size:11.5px;font-weight:800;text-transform:uppercase;letter-spacing:.09em}
.hero .big{font-size:38px;font-weight:800;line-height:1.04;margin-top:3px;letter-spacing:-.02em}
.hero .subbig{font-size:13px;font-weight:700;margin-top:4px}
.hero .caption{font-size:13px;color:#55606f;margin-top:9px;line-height:1.5}
/* hero colors are set INLINE in _card (Word/Outlook ignores chained .hero.ok selectors) */
.sec{margin-bottom:16px}
.sec h3{font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:#0E1A35;margin:0 0 6px;padding-bottom:6px;border-bottom:2px solid #C8A24B}
.row{display:flex;justify-content:space-between;align-items:baseline;padding:8px 0;font-size:14.5px;border-bottom:1px solid #eef1f5}
.sec .row:last-of-type{border-bottom:none}
.row .l{font-weight:600}
.row .when{color:#8a93a1;font-size:12px;font-weight:500;display:block;margin-top:1px}
.row .amt{font-weight:800;white-space:nowrap}
.sectotal{display:flex;justify-content:space-between;font-size:12.5px;font-weight:700;color:#55606f;border-top:2px solid #e4e8ee;margin-top:6px;padding-top:8px}
.watch{background:#fdf2d4;border:2px solid #ecd08f;border-left:6px solid #C8A24B;border-radius:11px;padding:11px 13px;font-size:13.5px;margin-bottom:8px;color:#5f4a1c}
.watch b{color:#8a5a00}
.note{font-size:13px;color:#55606f;padding:6px 2px;line-height:1.5}
.allgood{font-size:14px;color:#14713c;font-weight:700;padding:6px 2px}
.empty{font-size:13px;color:#8a93a1;padding:6px 2px}
.footer{background:#0E1A35;background:linear-gradient(160deg,#16294d,#0a1530);color:#93a6c6;padding:14px 18px 16px;font-size:11.5px;text-align:center;border-top:4px solid #C8A24B}
.footer .ok{color:#7fd3a3;font-weight:700}
.footer .bad{color:#f0c869;font-weight:700}
.budget-note{font-size:12px;color:#8a93a1;margin:-2px 0 12px}
.cat{margin-bottom:13px}
.cat-top{display:flex;justify-content:space-between;align-items:baseline;font-size:14px;margin-bottom:5px}
.cat-name{font-weight:700}
.cat-amt{font-weight:700;white-space:nowrap}
.cat-of{color:#8a93a1;font-weight:500;font-size:12.5px}
.over{color:#c0392b}
.bar{width:100%;border-collapse:collapse;border-radius:6px;overflow:hidden}
.bar td{height:11px;line-height:11px;font-size:1px}
"""

_PREVIEW_CSS = """
.preview-note{max-width:460px;margin:0 auto 14px;font-size:12px;color:#55606f;background:#fff;border:1px dashed #cbd3de;border-radius:11px;padding:11px 14px;line-height:1.6}
.preview-note b{color:#1a2332}
"""


def _card(payload):
    p = payload
    stale = p["stale"]
    nut = p["nut"]
    hero_ok = nut["covered"] and not stale

    # The big number is the monthly margin AFTER essential bills + essential
    # spending (tier 1+2), BEFORE any discretionary. Not free cash -- both facts
    # must be explicit in the caption or it reads as surplus.
    if stale:
        hlabel = "Numbers may be stale"
        hbig = _money(nut["gap"])
        hsub = ""
        hcap = "We don't have fresh bank data. Treat this week as 'probably fine, not confirmed.'"
    elif hero_ok:
        hlabel = "Covering the essentials? Yes"
        hbig = f"+{_money(nut['gap'])}/mo"
        hsub = "left after essential bills &amp; spending, before anything extra"
        hcap = (f"Income still coming in is {_money(nut['income'])}/mo. Essentials "
                f"&mdash; every fixed bill plus groceries, gas, and the like &mdash; run "
                f"{_money(nut['minimum'])}/mo. That leaves {_money(nut['gap'])} a month, "
                f"which is what's available for anything discretionary and for savings.")
    else:
        hlabel = "Tight this month"
        hbig = f"{_money(nut['gap'])}/mo"
        hsub = "essentials cost more than the income still coming in"
        hcap = (f"Essentials &mdash; fixed bills plus groceries, gas, and the like &mdash; "
                f"run {_money(nut['minimum'])}/mo, which is {_money(-nut['gap'])} more than "
                f"the {_money(nut['income'])}/mo of income still coming in. The difference has "
                f"to come from savings until income rises.")
    if hero_ok:
        h_bg, h_bd, h_fg = "#e8f6ee", "#a9d9bd", "#14713c"   # green: essentials covered
    else:
        h_bg, h_bd, h_fg = "#fdf2d4", "#ecd08f", "#8a5a00"   # amber: tight or stale

    def rows(items):
        return "".join(
            f'<div class="row"><span class="l">{i["name"]}'
            f'<span class="when">{_fmt_date(i["date"])}</span></span>'
            f'<span class="amt">{_money(i["amount"])}</span></div>'
            for i in items)

    paid, upcoming, att = p["paid"], p["upcoming"], p["attention"]

    att_html = ""
    for m in att["missed"]:
        cycles = ("" if m["count"] <= 1
                  else f" Last {m['count']} cycles have gone by with no charge.")
        att_html += (f'<div class="watch"><b>{m["name"]} hasn\'t posted.</b> '
                     f'Expected ~{_money(m["amount"])}'
                     f'{" around " + _fmt_date(m["latest"]) if m["latest"] else ""}.{cycles} '
                     f'Worth a quick check &mdash; cancelled, or just missed?</div>')
    if att["pending_statement"]:
        names = ", ".join(att["pending_statement"][:4])
        more = f" +{len(att['pending_statement']) - 4} more" if len(att["pending_statement"]) > 4 else ""
        att_html += (f'<div class="note">Waiting on the Apple Card statement to confirm: '
                     f'{names}{more}. Not overdue &mdash; just not visible until the statement imports.</div>')
    if not att_html:
        att_html = '<div class="allgood">Nothing needs attention &mdash; checked and confirmed.</div>'

    stale_banner = ""
    if stale:
        stale_banner = ('<div class="stale-banner"><b>&#9888; Heads up:</b> the bank data '
                        'isn\'t fresh, so this week\'s picture is "probably fine, not confirmed." '
                        'John\'s been notified.</div>')

    gen = _parse_ts(p["generated_at"])
    asof = dt.date.fromisoformat(p["asof"])
    crest_img = (f'<img class="crest-img" src="{CREST_DATA_URI}" width="92" height="92" '
                 f'alt="Cappuccio family crest">' if CREST_DATA_URI else "")
    footer_status = ('<span class="ok">bank data fresh &mdash; nothing overdue, confirmed &#10003;</span>'
                     if not stale else
                     '<span class="bad">bank data stale &mdash; not confirmed this week</span>')
    budget_html = _budget.render_section(p["budget"]) if _budget and p.get("budget") else ""

    return f"""<div class="card">
<div class="crest-band">{crest_img}
<p class="house">Cappuccio Household</p>
<p class="motto">Strength Through Unity</p>
<div class="band-rule"></div>
<p class="kicker">Weekly Check-in &middot; {_fmt_full(asof)}</p></div>
<div class="body">
<p class="lead">This week, in one look</p>
{stale_banner}
<div class="hero" style="background:{h_bg};border:2px solid {h_bd}">
<div class="label" style="color:{h_fg}">{hlabel}</div>
<div class="big" style="color:{h_fg}">{hbig}</div>
{f'<div class="subbig" style="color:{h_fg}">{hsub}</div>' if hsub else ''}
<div class="caption">{hcap}</div>
</div>
<div class="sec"><h3>Paid this week</h3>
{rows(paid['items']) if paid['items'] else '<div class="empty">Nothing posted in the last 7 days.</div>'}
{f'<div class="sectotal"><span>{len(paid["items"])} paid</span><span>{_money(paid["total"])}</span></div>' if paid['items'] else ''}
</div>
<div class="sec"><h3>Coming up (next {UPCOMING_DAYS} days)</h3>
{rows(upcoming['items']) if upcoming['items'] else '<div class="empty">Nothing due in the next ' + str(UPCOMING_DAYS) + ' days.</div>'}
{f'<div class="sectotal"><span>{len(upcoming["items"])} bills</span><span>{_money(upcoming["total"])}</span></div>' if upcoming['items'] else ''}
</div>
<div class="sec"><h3>Needs attention</h3>{att_html}</div>
{budget_html}
</div>
<div class="footer">Generated {_fmt_gen(gen)} &middot; {footer_status}</div>
</div>"""


def _doc(inner, extra_css=""):
    return ('<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
            '<title>Cappuccio Household &mdash; Weekly Finance</title>'
            f'<style>{_CSS}{extra_css}</style></head><body>{inner}</body></html>')


def render(payload):
    """Production email body (no preview chrome). This is what gets sent."""
    return _doc(_card(payload))


def render_preview(payload):
    """Local/HTTP preview: the exact email body plus a delivery-gating note.
    NEVER emailed -- the send path uses render(). build_digest.py uses this."""
    p = payload
    to_line = p["recipient_to"] + (", " + ", ".join(p["recipient_cc"]) if p["recipient_cc"] else "")
    cc_note = "" if p["recipient_cc"] else " &nbsp;(Amanda CC intentionally off until go-live)"
    note = (f'<div class="preview-note"><b>PREVIEW &mdash; not sent, delivery gated.</b><br>'
            f'To: {to_line}{cc_note}<br>'
            f'Subject: <b>{subject(p)}</b><br>'
            f'source_env: {p["nut"]["meta"]["source_env"]} / bank {p["paid"]["meta"]["source_env"]}</div>')
    return _doc(note + _card(payload), _PREVIEW_CSS)
