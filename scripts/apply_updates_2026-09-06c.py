"""Registry correction 2026-09-06c: Google Fi plan change (John, with statement PDF).

Evidence — Google Fi statement Sep 2, 2026 (John supplied the PDF this session):
  Total $73.36 = Flexible plan $20.00 + last month's DATA $49.02 (4.902 GB at
  $10/GB) + taxes/fees $4.34.
Cause: John's line now carries his data (previously a work eSIM did). The August
$40.14 jump the KICKOFF flagged ("watch if this sticks") was the same effect
starting — it stuck and grew.
Decision (John's): switch Flexible $20 -> UNLIMITED STANDARD $50/mo, effective
2026-10-02. Costs more monthly but caps the overrun exposure (break-even vs
$10/GB is ~3 GB; he used ~4.9).

ONE change. cell-google-fi:
  - expectedamount + monthlyequivalent 40.00 -> 55.00 (=$50 plan + ~$5
    taxes/fees, scaled from this statement's fee lines; Tier 1 rises 15.00).
  - variancetolerancepct stays 50: band 27.50-82.50 covers BOTH the known
    September one-off ($73.36, +33%) and the new steady state (~55, 0%), so
    the September debit binds without a false "needs attention" and no second
    edit is needed mid-month.
  - amounttype stays fixed — Unlimited genuinely is.
OCTOBER FOLLOW-UP: read the first real Unlimited bill (statement ~Nov 2, debit
~Nov 13-15), true-up expectedamount to the observed total, and TIGHTEN the
tolerance back toward 15 — 50% is only there to bridge September.

Envelope effect: 2,642.90 -> 2,627.90 (September and October).

Idempotent (notes marker). Audited (one hf_auditlog row).
Usage:
  py scripts/apply_updates_2026-09-06c.py https://org29b77f3e.crm.dynamics.com [--dry-run]
"""
import datetime as dt, json, os, subprocess, sys, uuid, requests

_AZ_SHELL = os.name == "nt"
ENV_URL = sys.argv[1].rstrip("/"); DRY = "--dry-run" in sys.argv
API = f"{ENV_URL}/api/data/v9.2"; P = "hf"
ACTOR = "apply_updates_2026-09-06c"
MARKER = "[2026-09-06c fi-unlimited]"

PATCH = {f"{P}_expectedamount": 55.00, f"{P}_monthlyequivalent": 55.00}
NOTE_ADD = (f" {MARKER} PLAN CHANGE: Flexible $20 -> Unlimited Standard $50 "
            "effective 2026-10-02 (John's line now carries his data; work eSIM "
            "gone). Sep 2 statement $73.36 = $20 + $49.02 data (4.902 GB x $10) "
            "+ $4.34 fees — known one-off, inside the 50% band. Expected 55.00 "
            "= 50 + ~5 fees. NOVEMBER: true-up expected from the first real "
            "Unlimited bill and tighten tolerance 50 -> ~15.")


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
    r = s.get(f"{API}/{P}_bills?$filter={P}_billkey eq 'cell-google-fi'"
              f"&$select={P}_billid,{P}_notes,{P}_expectedamount,{P}_monthlyequivalent")
    r.raise_for_status()
    rows = r.json()["value"]
    if not rows:
        sys.exit("cell-google-fi not found")
    row = rows[0]
    if MARKER in (row.get(f"{P}_notes") or ""):
        print(f"already applied ({MARKER} present) — nothing to do")
        return
    print(f"before: expected={row[f'{P}_expectedamount']}, "
          f"monthly={row[f'{P}_monthlyequivalent']}")
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
        f"{P}_action": "bill.plan_change", f"{P}_entitytype": "Bill",
        f"{P}_entityid": guid,
        f"{P}_context": json.dumps({
            "run_id": run_id, "bill_key": "cell-google-fi",
            "evidence": {"statement_date": "2026-09-02", "total": 73.36,
                         "plan": 20.00, "data_overrun": 49.02, "fees": 4.34,
                         "gb_used": 4.902},
            "plan_change": {"from": "Flexible $20", "to": "Unlimited Standard $50",
                            "effective": "2026-10-02"},
            "expectedamount": {"from": 40.00, "to": 55.00},
            "source_env": "production"})[:4000],
    }))
    if ar.status_code not in (200, 204):
        sys.exit(f"AUDIT ROW FAILED HTTP {ar.status_code}: {ar.text[:400]}")
    print(f"applied + audited (run {run_id}). Re-run /api/match, then verify the envelope.")


if __name__ == "__main__":
    main()
