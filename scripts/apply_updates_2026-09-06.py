"""Registry correction 2026-09-06: Oregon UI is LIVE — restore it from evidence.

ONE change. John reported at the weekly check-in that UI payments started, with
6 weeks of back pay. Verified in hf_transaction after the USAA re-link
(ITEM_LOGIN_REQUIRED 9/4-9/6, recovered this session via Link update mode):

    2026-09-04  +3,788.40  "EMPLOYMT BENEFIT UI BENEFIT"  (checking ...0666)

3,788.40 / 6 weeks = exactly 631.40/week. Monthly equivalent 631.40 x 52 / 12
= 2,736.07. The originally seeded 3,908.67 was a placeholder and is NOT
restored — the observed benefit is the number.

A. income-oregon-ui-john:
   - monthlyequivalent + expectedamount 0.00 -> 2,736.07 (income convention:
     both fields carry the monthly figure; see seed_income.to_record).
   - enddate 2026-08-31 -> None. The old end date assumed the Substrate draw
     replaced UI on 9/1; the draw has NOT started (EIN just arrived, first
     draw unscheduled). UI runs until the draw is real. STANDING RULE: John
     cannot draw business income and collect UI — when DRAW_START is set for
     real, set this row's enddate to the same date in the same script.
   - frequency "" -> weekly, anchordate -> 2026-09-04 (first observed deposit,
     a Friday) so the cash-runway sees the weekly cadence.
   - matchmode stays "none": kind=income rows are excluded from the matcher
     by design (seed_income.py).

The back-pay lump itself is already in hf_transaction as an ordinary
transaction — per the 2026-08-30 rule it is NOT modeled as monthly income.

Envelope effect (September): -93.17 -> +2,642.90.

Idempotent (notes marker). Audited (one hf_auditlog row).
Usage:
  py scripts/apply_updates_2026-09-06.py https://org29b77f3e.crm.dynamics.com [--dry-run]
"""
import datetime as dt, json, os, subprocess, sys, uuid, requests

_AZ_SHELL = os.name == "nt"
ENV_URL = sys.argv[1].rstrip("/"); DRY = "--dry-run" in sys.argv
API = f"{ENV_URL}/api/data/v9.2"; P = "hf"
ACTOR = "apply_updates_2026-09-06"
MARKER = "[2026-09-06 ui-live]"

PATCH = {
    f"{P}_monthlyequivalent": 2736.07,
    f"{P}_expectedamount": 2736.07,
    f"{P}_enddate": None,
    f"{P}_frequency": "weekly",
    f"{P}_anchordate": "2026-09-04",
}
NOTE_ADD = (f" {MARKER} UI IS PAYING: first deposit 2026-09-04 +3,788.40 "
            "'EMPLOYMT BENEFIT UI BENEFIT' = 6 weeks back pay = 631.40/wk exactly; "
            "monthly 2736.07 (x52/12) derived from evidence, not the 3908.67 "
            "placeholder. enddate cleared until the Substrate draw actually starts "
            "(cannot draw + collect UI; end this row the day the draw begins). "
            "Back-pay lump stays a transaction, not monthly income.")


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def main():
    tok = subprocess.run(["az", "account", "get-access-token", "--resource", ENV_URL,
                          "--query", "accessToken", "-o", "tsv"],
                         capture_output=True, text=True, check=True, shell=_AZ_SHELL).stdout.strip()
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}", "OData-MaxVersion": "4.0",
                      "OData-Version": "4.0", "Accept": "application/json",
                      "Content-Type": "application/json"})

    r = s.get(f"{API}/{P}_bills?$filter={P}_billkey eq 'income-oregon-ui-john'"
              f"&$select={P}_billid,{P}_notes,{P}_monthlyequivalent,{P}_enddate")
    r.raise_for_status()
    rows = r.json()["value"]
    if not rows:
        sys.exit("income-oregon-ui-john not found")
    row = rows[0]
    if MARKER in (row.get(f"{P}_notes") or ""):
        print(f"already applied ({MARKER} present) — nothing to do")
        return
    print(f"before: monthlyequivalent={row[f'{P}_monthlyequivalent']}, "
          f"enddate={row[f'{P}_enddate']}")
    if DRY:
        print("--dry-run: would patch", json.dumps(PATCH, indent=2))
        return

    patch = dict(PATCH)
    patch[f"{P}_notes"] = ((row.get(f"{P}_notes") or "") + NOTE_ADD)[:4000]
    patch[f"{P}_freshnessts"] = now()
    guid = row[f"{P}_billid"]
    pr = s.patch(f"{API}/{P}_bills({guid})", data=json.dumps(patch))
    if pr.status_code not in (200, 204):
        sys.exit(f"patch failed HTTP {pr.status_code}: {pr.text[:400]}")

    run_id = str(uuid.uuid4())[:8]
    ar = s.post(f"{API}/{P}_auditlogs", data=json.dumps({
        f"{P}_timestamp": now(),
        f"{P}_actor": ACTOR,
        f"{P}_action": "bill.income_restored",
        f"{P}_entitytype": "Bill",
        f"{P}_entityid": guid,
        f"{P}_context": json.dumps({
            "run_id": run_id, "bill_key": "income-oregon-ui-john",
            "evidence_txn": {"date": "2026-09-04", "amount": 3788.40,
                             "merchant": "EMPLOYMT BENEFIT UI BENEFIT",
                             "weeks_covered": 6, "weekly": 631.40},
            "monthlyequivalent": {"from": 0.00, "to": 2736.07},
            "enddate": {"from": "2026-08-31", "to": None},
            "frequency": {"from": "", "to": "weekly"},
            "source_env": "production"})[:4000],
    }))
    if ar.status_code not in (200, 204):
        sys.exit(f"AUDIT ROW FAILED HTTP {ar.status_code}: {ar.text[:400]} "
                 "(bill was patched — write the audit row before moving on)")
    print(f"applied + audited (run {run_id}). Re-run /api/match, then verify the envelope.")


if __name__ == "__main__":
    main()
