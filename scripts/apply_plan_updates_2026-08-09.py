"""Apply three registry plan updates + verify the envelope (2026-08-09).

Requested by John:
  1. Water delivery (Primo)  -> cancelled, end date today.
  2. LMNT electrolytes (card) -> cancelled, end date today.
  3. Internet (Comcast)       -> renegotiated to $70.00/mo (expected + monthly equiv).
Then: report the LIVE status of the Apple Card installment and Tesla FSD rows,
recompute the monthly envelope from live hf_bill state, and print before/after.

Every change writes an hf_auditlog row (non-negotiable #2). Idempotent: a change
already applied is detected and skipped (no duplicate patch, no duplicate audit),
so re-running is safe.

Auth: borrows your Azure CLI login (az login), same as seed_bills.py / seed_income.py.

Usage:
  python apply_plan_updates_2026-08-09.py https://org29b77f3e.crm.dynamics.com
  python apply_plan_updates_2026-08-09.py https://org29b77f3e.crm.dynamics.com --dry-run
"""
import datetime as dt
import json
import os
import subprocess
import sys
import uuid

import requests

ENV_URL = sys.argv[1].rstrip("/")
DRY_RUN = "--dry-run" in sys.argv
API = f"{ENV_URL}/api/data/v9.2"
P = "hf"
TODAY = dt.date(2026, 8, 9)              # "today" per the request (pinned, not now())
_AZ_SHELL = os.name == "nt"             # az is a .cmd on Windows, plain exe on POSIX

# ---- the three changes, declaratively ------------------------------------
# Each is a target billkey + a dict of fields to set. Cancellations also stamp
# an end date and mirror the existing convention (name tag + dated note).
CANCEL_NOTE = "CANCELLED by John 2026-08-09. No further billing."

CHANGES = [
    {"billkey": "water-delivery-primo", "action": "bill.deactivate",
     "set": {f"{P}_status": "cancelled", f"{P}_enddate": "2026-08-09"},
     "name_tag": "(CANCELLED)", "note_prefix": CANCEL_NOTE,
     "skip_if": lambda r: r.get(f"{P}_status") == "cancelled"},
    {"billkey": "lmnt-electrolytes-card", "action": "bill.deactivate",
     "set": {f"{P}_status": "cancelled", f"{P}_enddate": "2026-08-09"},
     "name_tag": "(CANCELLED)", "note_prefix": CANCEL_NOTE,
     "skip_if": lambda r: r.get(f"{P}_status") == "cancelled"},
    {"billkey": "internet-comcast", "action": "bill.update_amount",
     "set": {f"{P}_expectedamount": 70.0, f"{P}_monthlyequivalent": 70.0},
     "note_prefix": "Renegotiated to $70.00/mo (John, 2026-08-09).",
     "skip_if": lambda r: (float(r.get(f"{P}_expectedamount") or 0) == 70.0
                           and float(r.get(f"{P}_monthlyequivalent") or 0) == 70.0)},
    # Installment finished paying (John, 2026-08-09) -- all 12 payments completed,
    # ahead of the Nov-2026 end date. Deactivate so its $53.25 drops out of Tier 1.
    # 'cancelled' is the only inactive status the schema allows; the note records
    # that this was completion, not a cancellation.
    {"billkey": "apple-card-installment-plan", "action": "bill.deactivate",
     "set": {f"{P}_status": "cancelled", f"{P}_enddate": "2026-08-09"},
     "name_tag": "(PAID OFF)",
     "note_prefix": "Installment PAID IN FULL / all payments completed (John, 2026-08-09). No further billing.",
     "skip_if": lambda r: r.get(f"{P}_status") != "active"},
]

# Rows to report on but not change (the "confirm already inactive" ask).
REPORT_ONLY = ["tesla-fsd-subscription-cancelled"]


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def session():
    token = subprocess.run(
        ["az", "account", "get-access-token", "--resource", ENV_URL,
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, check=True, shell=_AZ_SHELL).stdout.strip()
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}",
                      "OData-MaxVersion": "4.0", "OData-Version": "4.0",
                      "Accept": "application/json", "Content-Type": "application/json"})
    return s


def get_bill(s, billkey):
    r = s.get(f"{API}/{P}_bills({P}_billkey='{billkey}')")
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def all_bills(s):
    sel = (f"{P}_billkey,{P}_name,{P}_kind,{P}_tier,{P}_status,"
           f"{P}_monthlyequivalent,{P}_startdate,{P}_enddate")
    out, url = [], f"{API}/{P}_bills?$select={sel}"
    while url:
        r = s.get(url)
        r.raise_for_status()
        j = r.json()
        out.extend(j.get("value", []))
        url = j.get("@odata.nextLink")
    return out


def _dateonly(v):
    return dt.date.fromisoformat(v[:10]) if v else None


def project(bills, changes):
    """Apply each change's target fields to an in-memory copy of the bills, so the
    envelope can be previewed BEFORE anything is written (dry-run) and cross-checked
    after (live). Only fields that affect the envelope matter, but we copy all set
    fields for fidelity."""
    by_key = {b.get(f"{P}_billkey"): dict(b) for b in bills}
    out = {k: dict(v) for k, v in by_key.items()}
    for ch in changes:
        row = out.get(ch["billkey"])
        if row is None:
            continue
        for f, v in ch["set"].items():
            row[f] = v
    return list(out.values())


def envelope(bills, today):
    """Mirror digest.compute_envelope's headline math: active income (in window)
    minus active Tier 1 bills. Returns (income, tier1, envelope)."""
    income = 0.0
    for b in bills:
        if b.get(f"{P}_kind") != "income" or b.get(f"{P}_status") != "active":
            continue
        start, end = _dateonly(b.get(f"{P}_startdate")), _dateonly(b.get(f"{P}_enddate"))
        if (start and today < start) or (end and today > end):
            continue
        income += float(b.get(f"{P}_monthlyequivalent") or 0)
    tier1 = 0.0
    for b in bills:
        if (b.get(f"{P}_kind") == "bill" and str(b.get(f"{P}_tier")) == "1"
                and b.get(f"{P}_status") == "active"):
            tier1 += float(b.get(f"{P}_monthlyequivalent") or 0)
    return round(income, 2), round(tier1, 2), round(income - tier1, 2)


def audit(s, ts, action, billkey, context):
    body = json.dumps({
        f"{P}_timestamp": ts,
        f"{P}_actor": "apply_plan_updates_2026-08-09",
        f"{P}_action": action,
        f"{P}_entitytype": "Bill",
        f"{P}_entityid": billkey,
        f"{P}_context": json.dumps(context)[:4000],
    })
    r = s.post(f"{API}/{P}_auditlogs", data=body)
    if r.status_code >= 400:
        sys.exit(f"AUDIT FAILED for {billkey}: HTTP {r.status_code}\n{r.text[:500]}")


def apply_change(s, ch, ts):
    key = ch["billkey"]
    row = get_bill(s, key)
    if row is None:
        print(f"  !! {key}: NOT FOUND -- skipping")
        return
    if ch.get("skip_if") and ch["skip_if"](row):
        print(f"  == {key}: already in target state -- skipping (idempotent)")
        return

    before = {f: row.get(f) for f in ch["set"]}
    patch = dict(ch["set"])

    # Convention mirror for cancellations: tag the name once, prepend a dated note.
    if ch.get("name_tag"):
        nm = row.get(f"{P}_name") or ""
        if ch["name_tag"] not in nm:
            patch[f"{P}_name"] = f"{nm} {ch['name_tag']}".strip()[:120]
    if ch.get("note_prefix"):
        old_note = row.get(f"{P}_notes") or ""
        if ch["note_prefix"] not in old_note:
            patch[f"{P}_notes"] = f"{ch['note_prefix']} {old_note}".strip()[:4000]
    patch[f"{P}_freshnessts"] = ts

    fields = ", ".join(f"{k.split('_', 1)[1]}={v}" for k, v in ch["set"].items())
    print(f"  -> {key}: {fields}")
    if DRY_RUN:
        return

    r = s.patch(f"{API}/{P}_bills({P}_billkey='{key}')", data=json.dumps(patch))
    if r.status_code >= 400:
        sys.exit(f"PATCH FAILED for {key}: HTTP {r.status_code}\n{r.text[:800]}")
    audit(s, ts, ch["action"], key,
          {"billkey": key, "before": before, "after": ch["set"],
           "requested_by": "John", "asof": TODAY.isoformat()})


def main():
    s = session()
    ts = now()

    print(f"== Plan updates {TODAY.isoformat()} =="
          f"{'  (DRY RUN -- nothing written)' if DRY_RUN else ''}")

    bills0 = all_bills(s)
    inc0, t1_0, env0 = envelope(bills0, TODAY)
    print(f"\nEnvelope BEFORE: income {inc0:,.2f} - Tier1 {t1_0:,.2f} = {env0:,.2f}")

    # Projected envelope from the intended changes, computed in memory so the
    # preview is meaningful even in dry-run (where nothing is written yet).
    incp, t1p, envp = envelope(project(bills0, CHANGES), TODAY)
    print(f"Envelope PROJECTED after changes: income {incp:,.2f} - Tier1 {t1p:,.2f} "
          f"= {envp:,.2f}  (change {envp - env0:+,.2f}, new headline ~ ${envp:,.0f})")

    print("\nApplying changes:")
    for ch in CHANGES:
        apply_change(s, ch, ts)

    print("\nReport-only (confirm status, no change):")
    for key in REPORT_ONLY:
        row = get_bill(s, key)
        if row is None:
            print(f"  ?? {key}: NOT FOUND")
            continue
        st = row.get(f"{P}_status")
        me = row.get(f"{P}_monthlyequivalent")
        end = row.get(f"{P}_enddate")
        active = "ACTIVE (counts in envelope)" if st == "active" else f"inactive ({st})"
        print(f"  -- {key}: status={st} -> {active}; monthly_equiv={me}; end={end}")

    if DRY_RUN:
        print(f"\n--dry-run: no rows written, no audit logged. "
              f"Projected new headline ~ ${envp:,.0f} (run without --dry-run to apply).")
        return

    # Live: re-read and confirm the actual envelope matches what we projected.
    inc1, t1_1, env1 = envelope(all_bills(s), TODAY)
    print(f"\nEnvelope AFTER (live re-read): income {inc1:,.2f} - Tier1 {t1_1:,.2f} = {env1:,.2f}")
    print(f"Envelope change: {env1 - env0:+,.2f}  (new headline ~ ${env1:,.0f})")
    if round(env1, 2) != round(envp, 2):
        print(f"  !! WARNING: live envelope {env1:,.2f} != projected {envp:,.2f} "
              f"-- investigate before trusting the digest.")


if __name__ == "__main__":
    main()
