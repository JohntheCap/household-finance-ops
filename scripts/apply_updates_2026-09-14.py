"""Weekly check-in updates 2026-09-14: UI gross weekly benefit + register Hims.

TWO changes, both from John at the 2026-09-14 weekly check-in.

A. income-oregon-ui-john: monthlyequivalent + expectedamount 2,736.07 -> 3,283.28.
   RESOLVES the 9/14 discrepancy (9/9 deposit 757.68 vs registered 631.40/wk).
   John, from Frances Online: the weekly benefit IS 757.68 gross. The 9/4
   back-pay lump 3,788.40 was 6 weeks GROSS (4,546.08) less tax withholding;
   631.40/wk was the net, not the benefit. John has turned withholding OFF for
   future payments, so deposits will land at the gross 757.68/wk from here on.
   Monthly equivalent = 757.68 x 52 / 12 = 3,283.28. Evidence + John's word,
   not a guess: the 9/9 un-withheld deposit was exactly 757.68.
   NOTE: with withholding off, the tax on UI income is now John's to set aside
   -- the envelope shows gross. Flagged at the check-in; his call.

B. Register supplement-hims: Hims & Hers, 21.00 MONTHLY, Tier 3, Apple Card.
   Observed 2026-09-11 -21.00 "Hims And Hers Inc." (Apple Card CSV, ingested
   this session). John confirms it is a subscription for his hair supplements
   -- a real cadence by his statement, so it registers (unlike the one-off
   Redmond charge, which stays unregistered). **John intends to CANCEL next
   month**: expect at most one more charge (~2026-10-11); when the cancellation
   is confirmed, set status=cancelled + enddate in that session's script (the
   Primo/LMNT pattern). Tier 3 = no envelope effect; a visible cut in motion.

Envelope effect (Sept + Oct): +2,627.90 -> +3,175.11 (income +547.21/mo).

Idempotent (A: notes marker; B: alternate-key existence check). Audited.
Usage:
  py scripts/apply_updates_2026-09-14.py https://org29b77f3e.crm.dynamics.com [--dry-run]
"""
import datetime as dt, json, os, subprocess, sys, uuid, requests

_AZ_SHELL = os.name == "nt"
ENV_URL = sys.argv[1].rstrip("/"); DRY = "--dry-run" in sys.argv
API = f"{ENV_URL}/api/data/v9.2"; P = "hf"
ACTOR = "apply_updates_2026-09-14"
MARKER = "[2026-09-14 ui-gross]"

UI_PATCH = {
    f"{P}_monthlyequivalent": 3283.28,
    f"{P}_expectedamount": 3283.28,
}
UI_NOTE = (f" {MARKER} Weekly benefit is 757.68 GROSS (Frances Online, John "
           "2026-09-14; 9/9 deposit was exactly 757.68). The 9/4 back-pay "
           "3,788.40 was 6 weeks gross less withholding -- 631.40/wk was net. "
           "Withholding now OFF, future deposits 757.68/wk; monthly 3283.28 "
           "(x52/12). Tax on UI is John's to set aside -- envelope is gross.")

HIMS_BILL = {
    f"{P}_billkey": "supplement-hims",
    f"{P}_name": "Hair supplements (Hims)",
    f"{P}_kind": "bill", f"{P}_tier": "3", f"{P}_status": "active",
    f"{P}_amounttype": "fixed",
    f"{P}_expectedamount": 21.00, f"{P}_monthlyequivalent": 21.00,
    f"{P}_frequency": "monthly", f"{P}_dueday": 11,
    f"{P}_anchordate": "2026-09-11",
    f"{P}_paymentaccount": "applecard",
    f"{P}_latencydays": 30, f"{P}_matchmode": "merchant",
    f"{P}_matchpattern": "Hims And Hers", f"{P}_variancetolerancepct": 15,
    f"{P}_notes": ("[2026-09-14] Registered from the Sept Apple Card CSV: "
                   "-21.00 on 2026-09-11 'Hims And Hers Inc.'. John: hair "
                   "supplements subscription, CANCELLING next month -- expect "
                   "at most one more charge (~2026-10-11), then set "
                   "status=cancelled + enddate in that session's script. "
                   "Possibly the successor to the one-off Redmond charge "
                   "(2026-08-06, still unregistered by design)."),
}


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

    # --- A. UI gross weekly -------------------------------------------------
    r = s.get(f"{API}/{P}_bills?$filter={P}_billkey eq 'income-oregon-ui-john'"
              f"&$select={P}_billid,{P}_notes,{P}_monthlyequivalent")
    r.raise_for_status()
    rows = r.json()["value"]
    if not rows:
        sys.exit("income-oregon-ui-john not found")
    row = rows[0]
    if MARKER in (row.get(f"{P}_notes") or ""):
        print(f"A. already applied ({MARKER} present) -- skip")
    else:
        print(f"A. before: monthlyequivalent={row[f'{P}_monthlyequivalent']}")
        if DRY:
            print("   --dry-run: would patch", json.dumps(UI_PATCH))
        else:
            patch = dict(UI_PATCH)
            patch[f"{P}_notes"] = ((row.get(f"{P}_notes") or "") + UI_NOTE)[:4000]
            patch[f"{P}_freshnessts"] = now()
            guid = row[f"{P}_billid"]
            pr = s.patch(f"{API}/{P}_bills({guid})", data=json.dumps(patch))
            if pr.status_code not in (200, 204):
                sys.exit(f"A. patch failed HTTP {pr.status_code}: {pr.text[:400]}")
            run_id = str(uuid.uuid4())[:8]
            ar = s.post(f"{API}/{P}_auditlogs", data=json.dumps({
                f"{P}_timestamp": now(), f"{P}_actor": ACTOR,
                f"{P}_action": "bill.amount_corrected",
                f"{P}_entitytype": "Bill", f"{P}_entityid": guid,
                f"{P}_context": json.dumps({
                    "run_id": run_id, "bill_key": "income-oregon-ui-john",
                    "monthlyequivalent": {"from": 2736.07, "to": 3283.28},
                    "evidence": {"deposit_2026-09-09": 757.68,
                                 "frances_online_weekly_gross": 757.68,
                                 "backpay_3788.40": "6 wks gross less withholding",
                                 "withholding": "OFF for future payments (John, 2026-09-14)"},
                    "source_env": "production"})[:4000],
            }))
            if ar.status_code not in (200, 204):
                sys.exit(f"A. AUDIT ROW FAILED HTTP {ar.status_code}: {ar.text[:400]} "
                         "(bill was patched -- write the audit row before moving on)")
            print(f"   applied + audited (run {run_id})")

    # --- B. Register Hims ---------------------------------------------------
    key = HIMS_BILL[f"{P}_billkey"]
    r = s.get(f"{API}/{P}_bills({P}_billkey='{key}')")
    if r.status_code == 200:
        print(f"B. {key}: already registered -- skip")
    elif r.status_code != 404:
        sys.exit(f"B. GET {key} unexpected: {r.status_code}\n{r.text[:400]}")
    else:
        print(f"B. CREATE {key}: 21.00/monthly tier 3 (applecard)")
        if DRY:
            print("   --dry-run: would upsert")
        else:
            ts = now()
            body = dict(HIMS_BILL)
            body[f"{P}_freshnessts"] = ts
            body[f"{P}_sourceenv"] = "weekly-checkin"
            resp = s.patch(f"{API}/{P}_bills({P}_billkey='{key}')", data=json.dumps(body))
            if resp.status_code >= 400:
                sys.exit(f"B. UPSERT FAILED: {resp.status_code}\n{resp.text[:600]}")
            a = s.post(f"{API}/{P}_auditlogs", data=json.dumps({
                f"{P}_timestamp": ts, f"{P}_actor": ACTOR, f"{P}_action": "bill.register",
                f"{P}_entitytype": "Bill", f"{P}_entityid": key,
                f"{P}_context": json.dumps({
                    "billkey": key, "after": HIMS_BILL,
                    "source": "Sept Apple Card CSV 9/1-9/14; John confirmed subscription 2026-09-14",
                    "cancellation_intent": "next month (~Oct); supersede then",
                    "requested_by": "John"})[:4000]}))
            if a.status_code >= 400:
                sys.exit(f"B. AUDIT FAILED: {a.status_code}\n{a.text[:400]}")
            print("   created + audited")

    print("\nNEXT: run /api/match, then verify the envelope "
          "(expect Sept/Oct +3,175.11).")


if __name__ == "__main__":
    main()
