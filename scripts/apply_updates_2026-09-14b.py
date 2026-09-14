"""Correction 2026-09-14b: UI gross weekly is 902.00, not 757.68.

ONE change, correcting apply_updates_2026-09-14.py (A) same-session.

John: the weekly benefit is $902/week. That reconciles ALL the evidence:
  902.00 x 0.84 = 757.68 EXACTLY -- the observed deposits were net of 16%
  withholding (10% federal + 6% Oregon state), which is what Frances Online
  was showing him. The 9/4 back-pay 3,788.40 = 5 x 757.68 net = 5 weeks at
  902 gross. With withholding now OFF, future deposits land at 902.00/wk.

Monthly equivalent = 902.00 x 52 / 12 = 3,908.67 -- coincidentally the exact
figure of the original seed placeholder (which was zeroed 2026-08-30 when no
UI had ever paid). It returns now because the evidence supports it, not
because the placeholder was trusted.

income-oregon-ui-john: monthlyequivalent + expectedamount 3,283.28 -> 3,908.67.

Envelope effect (Sept + Oct): +3,175.11 -> +3,800.50.
VERIFY next weekly deposit lands at exactly 902.00 (confirms withholding off).

Idempotent (notes marker). Audited.
Usage:
  py scripts/apply_updates_2026-09-14b.py https://org29b77f3e.crm.dynamics.com [--dry-run]
"""
import datetime as dt, json, os, subprocess, sys, uuid, requests

_AZ_SHELL = os.name == "nt"
ENV_URL = sys.argv[1].rstrip("/"); DRY = "--dry-run" in sys.argv
API = f"{ENV_URL}/api/data/v9.2"; P = "hf"
ACTOR = "apply_updates_2026-09-14b"
MARKER = "[2026-09-14b ui-902]"

PATCH = {
    f"{P}_monthlyequivalent": 3908.67,
    f"{P}_expectedamount": 3908.67,
}
NOTE_ADD = (f" {MARKER} CORRECTION: gross weekly benefit is 902.00 (John). "
            "902 x 0.84 = 757.68 exactly -- observed deposits were net of 16% "
            "withholding (10% fed + 6% OR); back-pay 3,788.40 = 5 wks net. "
            "Withholding OFF -> future deposits 902.00/wk. Monthly 3908.67 "
            "(x52/12). Matches the original seed figure, now evidence-backed.")


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
              f"&$select={P}_billid,{P}_notes,{P}_monthlyequivalent")
    r.raise_for_status()
    rows = r.json()["value"]
    if not rows:
        sys.exit("income-oregon-ui-john not found")
    row = rows[0]
    if MARKER in (row.get(f"{P}_notes") or ""):
        print(f"already applied ({MARKER} present) -- nothing to do")
        return
    print(f"before: monthlyequivalent={row[f'{P}_monthlyequivalent']}")
    if DRY:
        print("--dry-run: would patch", json.dumps(PATCH))
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
        f"{P}_timestamp": now(), f"{P}_actor": ACTOR,
        f"{P}_action": "bill.amount_corrected",
        f"{P}_entitytype": "Bill", f"{P}_entityid": guid,
        f"{P}_context": json.dumps({
            "run_id": run_id, "bill_key": "income-oregon-ui-john",
            "monthlyequivalent": {"from": 3283.28, "to": 3908.67},
            "evidence": {"gross_weekly": 902.00,
                         "net_check": "902 x 0.84 = 757.68 = observed deposits",
                         "withholding_was": "16% (10% fed + 6% OR), now OFF",
                         "backpay_3788.40": "5 weeks net at 757.68"},
            "corrects": "apply_updates_2026-09-14 run 5008e9e3",
            "source_env": "production"})[:4000],
    }))
    if ar.status_code not in (200, 204):
        sys.exit(f"AUDIT ROW FAILED HTTP {ar.status_code}: {ar.text[:400]} "
                 "(bill was patched -- write the audit row before moving on)")
    print(f"applied + audited (run {run_id}). Re-run /api/match, verify envelope "
          "(expect +3,800.50).")


if __name__ == "__main__":
    main()
