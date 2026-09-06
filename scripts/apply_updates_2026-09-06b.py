"""Registry correction 2026-09-06b: draw is gated on UI exit / SEA — push placeholders.

John, same session (after UI income went live): "My draws will not start until
I am off unemployment OR accepted into UI Self-Employment program. We will
need to re-assess at that time."

So the 2026-10-01 DRAW_START placeholder is not just unconfirmed, it is
contradicted: there is no draw date and cannot be one until an external event
(UI exit, or Oregon SEA acceptance) with no schedule. Leaving 10/01 in place
makes every October+ envelope read ~$6.1k too high (and double-counts UI+draw).

Two coupled changes (the sweep banks the draw and must NEVER start first):

A. income-substrate-owner-draw: startdate + anchordate 2026-10-01 -> 2027-07-01
   (FAR-FUTURE PLACEHOLDER, deliberately past any plausible date so no interim
   envelope silently counts it; set the real date the day the gate clears).
B. savings-sweep-substrate: startdate 2026-10-01 -> 2027-07-01, lockstep.

STANDING RULE UPDATE (supersedes the 2026-09-06 note's absolute form): when the
draw becomes real —
  - via UI EXIT: set income-oregon-ui-john.enddate = draw start (cannot draw
    business income and collect regular UI);
  - via SEA ACCEPTANCE: UI and draw may legally coexist — do NOT auto-end the
    UI row; re-assess amounts and dates with John at that time.

Idempotent (notes marker per row). Audited (one hf_auditlog row per change).
Usage:
  py scripts/apply_updates_2026-09-06b.py https://org29b77f3e.crm.dynamics.com [--dry-run]
"""
import datetime as dt, json, os, subprocess, sys, uuid, requests

_AZ_SHELL = os.name == "nt"
ENV_URL = sys.argv[1].rstrip("/"); DRY = "--dry-run" in sys.argv
API = f"{ENV_URL}/api/data/v9.2"; P = "hf"
ACTOR = "apply_updates_2026-09-06b"
MARKER = "[2026-09-06b draw-gated]"
NEW_DATE = "2027-07-01"

UPDATES = [
    {"key": "income-substrate-owner-draw",
     "action": "bill.draw_start_pushed",
     "patch": {f"{P}_startdate": NEW_DATE, f"{P}_anchordate": NEW_DATE},
     "note": (f" {MARKER} Draw gated on UI exit OR Oregon SEA acceptance (John, "
              "2026-09-06) — no schedulable date. 2027-07-01 is a FAR-FUTURE "
              "placeholder so no interim envelope counts it; set the real date "
              "when the gate clears. If via SEA, UI may legally continue "
              "alongside the draw — re-assess, do not auto-end the UI row."),
     "from": "2026-10-01"},
    {"key": "savings-sweep-substrate",
     "action": "bill.sweep_start_pushed",
     "patch": {f"{P}_startdate": NEW_DATE},
     "note": (f" {MARKER} Lockstep with the draw (the sweep banks the draw and "
              "must never start first). Re-size when the draw is real — $3,000 "
              "was sized against a $6,500 draw that no longer has a date."),
     "from": "2026-10-01"},
]


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
    for u in UPDATES:
        r = s.get(f"{API}/{P}_bills?$filter={P}_billkey eq '{u['key']}'"
                  f"&$select={P}_billid,{P}_notes,{P}_startdate")
        r.raise_for_status()
        rows = r.json()["value"]
        if not rows:
            sys.exit(f"{u['key']} not found")
        row = rows[0]
        if MARKER in (row.get(f"{P}_notes") or ""):
            print(f"{u['key']}: already applied — skipping")
            continue
        print(f"{u['key']}: startdate {row[f'{P}_startdate']} -> {NEW_DATE}")
        if DRY:
            continue
        patch = dict(u["patch"])
        patch[f"{P}_notes"] = ((row.get(f"{P}_notes") or "") + u["note"])[:4000]
        patch[f"{P}_freshnessts"] = now()
        guid = row[f"{P}_billid"]
        pr = s.patch(f"{API}/{P}_bills({guid})", data=json.dumps(patch))
        if pr.status_code not in (200, 204):
            sys.exit(f"patch failed HTTP {pr.status_code}: {pr.text[:400]}")
        run_id = str(uuid.uuid4())[:8]
        ar = s.post(f"{API}/{P}_auditlogs", data=json.dumps({
            f"{P}_timestamp": now(), f"{P}_actor": ACTOR,
            f"{P}_action": u["action"], f"{P}_entitytype": "Bill",
            f"{P}_entityid": guid,
            f"{P}_context": json.dumps({
                "run_id": run_id, "bill_key": u["key"],
                "startdate": {"from": u["from"], "to": NEW_DATE},
                "reason": "draw gated on UI exit or SEA acceptance; no date exists",
                "source_env": "production"})[:4000],
        }))
        if ar.status_code not in (200, 204):
            sys.exit(f"AUDIT ROW FAILED HTTP {ar.status_code}: {ar.text[:400]}")
        print(f"  applied + audited (run {run_id})")
    if DRY:
        print("--dry-run: nothing written")


if __name__ == "__main__":
    main()
