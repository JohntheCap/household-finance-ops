"""Household Finance Ops Agent — plaid_sync (Sprint 2).

Contract (v1.1 addendum A4/A9, R13):
- Every run and every item result carries source_env (= PLAID_ENV, asserted at startup).
- Every run writes an AuditLog row (append-only). Failures write status=sync_failed.
- Empty results are never silent: empty_reason is clean_empty | sync_failed | sync_stale.
- freshness_ts on Account rows is set only after a *successful* sync of their item.
- No money movement: only /transactions/sync and /accounts/get are called. Ever.
"""

import json
import logging
import os
import uuid
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone

import azure.functions as func
import requests
from azure.identity import DefaultAzureCredential, ClientSecretCredential
from azure.keyvault.secrets import SecretClient

app = func.FunctionApp()

# ---------------------------------------------------------------- config

PLAID_HOSTS = {
    "sandbox": "https://sandbox.plaid.com",
    "production": "https://production.plaid.com",
}

SOURCE_ENV = os.environ.get("PLAID_ENV", "")
if SOURCE_ENV not in PLAID_HOSTS:  # A9: assert env on startup
    raise RuntimeError(f"PLAID_ENV must be sandbox|production, got '{SOURCE_ENV}'")

KEY_VAULT_URI = os.environ["KEY_VAULT_URI"]
DATAVERSE_URL = os.environ["DATAVERSE_URL"].rstrip("/")
P = os.environ.get("DATAVERSE_PREFIX", "hf")  # publisher prefix

_credential = DefaultAzureCredential()
_secrets = SecretClient(vault_url=KEY_VAULT_URI, credential=_credential)

# Checking-side rows that move money between our own accounts rather than out of
# the household. Only the Apple Card payment is listed, and deliberately so: we
# ingest Apple Card statement detail, so counting both the payment and the
# purchases behind it would double-count. Synchrony and the USAA Visa are NOT
# here -- we have no line-item feed for either, so their payments ARE the only
# record of that spending and must keep counting as outflow.
TRANSFER_PATTERNS = ("APPLECARD GSBANK PAYMENT",)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_transfer(name: str) -> bool:
    upper = (name or "").upper()
    return any(p in upper for p in TRANSFER_PATTERNS)


# ---------------------------------------------------------------- dataverse

class Dataverse:
    def __init__(self):
        tenant = _secrets.get_secret("dataverse-tenant-id").value
        client = _secrets.get_secret("dataverse-client-id").value
        secret = _secrets.get_secret("dataverse-client-secret").value
        cred = ClientSecretCredential(tenant, client, secret)
        token = cred.get_token(f"{DATAVERSE_URL}/.default").token
        self.s = requests.Session()
        self.s.headers.update({
            "Authorization": f"Bearer {token}",
            "OData-MaxVersion": "4.0", "OData-Version": "4.0",
            "Accept": "application/json", "Content-Type": "application/json",
        })
        self.base = f"{DATAVERSE_URL}/api/data/v9.2"

    @staticmethod
    def _check(r):
        """Like raise_for_status, but keeps Dataverse's error body — losing it cost a
        debugging round-trip on 2026-07-07 (hf_amount range bug). Never again."""
        if r.status_code >= 400:
            raise DataverseError(r.status_code, r.request.url, r.text[:500])

    def get(self, path):
        r = self.s.get(f"{self.base}/{path}")
        self._check(r)
        return r.json()

    def create(self, table, record):
        self._check(self.s.post(f"{self.base}/{table}", data=json.dumps(record)))

    def upsert(self, table, keycol, keyval, record):
        # Alternate-key upsert: PATCH /table(keycol='keyval')
        self._check(self.s.patch(f"{self.base}/{table}({keycol}='{keyval}')", data=json.dumps(record)))

    def update(self, table, guid_, record):
        self._check(self.s.patch(f"{self.base}/{table}({guid_})", data=json.dumps(record)))

    def audit(self, action, entity_type, entity_id, context: dict):
        """Append-only audit trail. Never raises into the caller's control flow decisions."""
        self.create(f"{P}_auditlogs", {
            f"{P}_timestamp": _now(),
            f"{P}_actor": "plaid_sync",
            f"{P}_action": action,
            f"{P}_entitytype": entity_type,
            f"{P}_entityid": str(entity_id),
            f"{P}_context": json.dumps({**context, "source_env": SOURCE_ENV})[:4000],
        })


# ---------------------------------------------------------------- plaid

def plaid_post(path, body):
    body = {
        "client_id": os.environ["PLAID_CLIENT_ID"],
        "secret": _secrets.get_secret(f"plaid-secret-{SOURCE_ENV}").value,
        **body,
    }
    r = requests.post(f"{PLAID_HOSTS[SOURCE_ENV]}{path}", json=body, timeout=30)
    if r.status_code != 200:
        err = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        raise PlaidError(err.get("error_code", f"HTTP_{r.status_code}"), err.get("error_message", r.text[:500]))
    return r.json()


class PlaidError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(f"{code}: {message}")


class DataverseError(Exception):
    def __init__(self, status, url, body):
        self.code = f"DATAVERSE_{status}"
        super().__init__(f"HTTP {status} at {url}: {body}")


# ---------------------------------------------------------------- sync

def sync_item(dv: Dataverse, item: dict) -> dict:
    """Sync one Plaid Item. Returns per-item result for the run log."""
    item_guid = item[f"{P}_plaiditemid"]
    label = item[f"{P}_label"]
    access_token = _secrets.get_secret(item[f"{P}_kvsecretname"]).value
    cursor = item.get(f"{P}_cursor") or ""
    added, modified, removed = [], [], []

    # Full pagination BEFORE applying anything (per Plaid docs), so a mid-page
    # failure never half-applies a batch or advances the cursor.
    next_cursor = cursor
    while True:
        resp = plaid_post("/transactions/sync", {"access_token": access_token, "cursor": next_cursor, "count": 500})
        added += resp["added"]
        modified += resp["modified"]
        removed += resp["removed"]
        next_cursor = resp["next_cursor"]
        if not resp["has_more"]:
            break

    # Upsert accounts + capture per-account freshness (drives digest T9).
    accounts = plaid_post("/accounts/get", {"access_token": access_token})["accounts"]
    ts = _now()
    for a in accounts:
        dv.upsert(f"{P}_accounts", f"{P}_plaidaccountid", a["account_id"], {
            f"{P}_name": a["name"],
            f"{P}_mask": a.get("mask") or "",
            f"{P}_type": f"{a['type']}/{a.get('subtype')}",
            f"{P}_freshnessts": ts,
            f"{P}_sourceenv": SOURCE_ENV,
        })

    for t in added + modified:
        pfc = t.get("personal_finance_category") or {}
        name = (t.get("name") or "")[:200]
        dv.upsert(f"{P}_transactions", f"{P}_plaidtxnid", t["transaction_id"], {
            f"{P}_posteddate": t["date"],
            f"{P}_amount": -t["amount"],  # Plaid: positive = outflow; our model: negative = outflow (§6.2)
            f"{P}_merchantraw": name,
            f"{P}_category": pfc.get("primary", ""),
            f"{P}_categorydetailed": pfc.get("detailed", "")[:100],
            f"{P}_istransfer": _is_transfer(name),
            f"{P}_ispending": t["pending"],
            f"{P}_isremoved": False,
            f"{P}_plaidaccountid_text": t["account_id"],
            f"{P}_freshnessts": ts,
            f"{P}_sourceenv": SOURCE_ENV,
        })
    for t in removed:
        # Append-only spirit: flag, never delete.
        dv.upsert(f"{P}_transactions", f"{P}_plaidtxnid", t["transaction_id"], {f"{P}_isremoved": True})

    # Cursor advances only after all writes succeeded.
    dv.update(f"{P}_plaiditems", item_guid, {
        f"{P}_cursor": next_cursor,
        f"{P}_lastsyncstatus": "ok",
        f"{P}_lastsyncts": ts,
    })

    n = len(added) + len(modified) + len(removed)
    return {
        "item": label, "status": "ok", "source_env": SOURCE_ENV, "freshness_ts": ts,
        "added": len(added), "modified": len(modified), "removed": len(removed),
        "empty_reason": "clean_empty" if n == 0 else None,  # R13: empty is explicit, never silent
    }


# ---------------------------------------------------------------- bill matching

# How far either side of the due date a posting still counts as this cycle. Due
# days are medians of observed postings, not contractual dates, so they wobble.
MATCH_WINDOW = {"monthly": 10, "bimonthly": 20, "quarterly": 20, "annual": 30}
STEP_MONTHS = {"monthly": 1, "bimonthly": 2, "quarterly": 3, "annual": 12}

# Cycles generated behind and ahead of today. Two back is enough to catch a bill
# that posts late; one ahead gives the digest its "upcoming" list.
LOOKBACK_CYCLES, LOOKAHEAD_CYCLES = 2, 1


def _add_months(d: date, n: int) -> date:
    """Step whole months, clamping the day (Jan 31 + 1 month -> Feb 28)."""
    month = d.month - 1 + n
    year, month = d.year + month // 12, month % 12 + 1
    return date(year, month, min(d.day, monthrange(year, month)[1]))


def due_dates(bill: dict, today: date) -> list:
    """Cycle due dates around today, stepped from the bill's cadence anchor.

    Anchoring on a real observed charge is what makes bimonthly and annual work:
    garbage is not "every 2 months" in the abstract, it is every 2 months from a
    specific month, and a phase error would invent MISSED cycles that never existed.
    """
    freq = bill.get(f"{P}_frequency") or "monthly"
    step = STEP_MONTHS.get(freq)
    anchor_raw, due_day = bill.get(f"{P}_anchordate"), bill.get(f"{P}_dueday")
    if not step or not anchor_raw or not due_day:
        return []
    anchor = date.fromisoformat(anchor_raw[:10])

    # Jump straight to the cycle nearest today rather than iterating from anchor.
    months_apart = (today.year - anchor.year) * 12 + (today.month - anchor.month)
    base = anchor
    if step:
        base = _add_months(anchor, (months_apart // step) * step)

    out = []
    for k in range(-LOOKBACK_CYCLES, LOOKAHEAD_CYCLES + 1):
        d = _add_months(base, k * step)
        cycle = date(d.year, d.month, min(int(due_day), monthrange(d.year, d.month)[1]))
        # Never invent cycles that predate the bill's first observed charge. On an
        # annual bill a 2-cycle lookback reaches back two YEARS, and GoDaddy was
        # reported MISSED for 2024 and 2025 -- years before we had any data, and
        # before the obligation is known to have existed.
        if cycle < anchor.replace(day=1):
            continue
        out.append(cycle)
    return out


def _statement_covers(txns: list, when: date) -> bool:
    """Has an Apple Card statement covering `when` actually been imported?

    Without this a card bill with no statement yet would be indistinguishable
    from a card bill that genuinely went unpaid. Absent data is not evidence of a
    missed payment -- it is absent data (R13's clean_empty vs sync_failed, applied
    to bills).
    """
    return any(t.get(f"{P}_sourceenv") == "applecard-csv"
               and (t.get(f"{P}_posteddate") or "")[:7] == when.isoformat()[:7]
               for t in txns)


def match_one(bill: dict, due: date, txns: list, today: date, claimed: set) -> dict:
    """Decide one cycle's state. Pure function of its inputs -- no writes."""
    # '|'-separated alternatives: one bill can post under several descriptors
    # (a renamed servicer, a merchant's own variant spellings).
    patterns = [p for p in (bill.get(f"{P}_matchpattern") or "").upper().split("|") if p]
    mode = bill.get(f"{P}_matchmode")
    expected = float(bill.get(f"{P}_expectedamount") or 0)
    tolerance = float(bill.get(f"{P}_variancetolerancepct") or 15)
    latency = int(bill.get(f"{P}_latencydays") or 35)
    freq = bill.get(f"{P}_frequency") or "monthly"
    window = MATCH_WINDOW.get(freq, 10)

    candidates = []
    for t in txns:
        txid = t.get(f"{P}_plaidtxnid")
        if txid in claimed or t.get(f"{P}_isremoved") or t.get(f"{P}_istransfer"):
            continue
        posted_raw = t.get(f"{P}_posteddate")
        if not posted_raw:
            continue
        posted = date.fromisoformat(posted_raw[:10])
        drift_days = abs((posted - due).days)
        if drift_days > window:
            continue
        merchant = (t.get(f"{P}_merchantraw") or "").upper()
        if not any(merchant.startswith(p) for p in patterns):
            continue
        actual = abs(float(t.get(f"{P}_amount") or 0))
        within = expected and abs(actual - expected) / expected * 100 <= tolerance
        # merchant+amount means the pattern alone is ambiguous (Tesla connectivity
        # and Tesla FSD post identically), so amount is required to bind, not
        # merely to judge drift.
        if mode == "merchant+amount" and not within:
            continue
        candidates.append((drift_days, t, actual, within))

    if candidates:
        drift_days, txn, actual, within = min(candidates, key=lambda c: c[0])
        variance = ((actual - expected) / expected * 100) if expected else 0.0
        # Confidence degrades with date drift; a same-day exact match is 1.0.
        confidence = round(max(0.5, 1.0 - drift_days / (window * 2.0)) * (1.0 if within else 0.7), 2)
        return {
            "status": "arrived" if within or not expected else "drifted",
            "actual": actual, "variance": round(variance, 2),
            "txnid": txn.get(f"{P}_plaidtxnid"),
            "paiddate": (txn.get(f"{P}_posteddate") or "")[:10],
            "confidence": confidence, "empty_reason": None,
            "note": f"matched '{txn.get(f'{P}_merchantraw')}' {drift_days}d from due",
        }

    if due > today:
        return {"status": "upcoming", "confidence": 1.0, "empty_reason": None,
                "note": "cycle not yet due"}

    observable = bill.get(f"{P}_paymentaccount") != "applecard" or _statement_covers(txns, due)
    if not observable:
        return {"status": "unobservable", "confidence": 1.0,
                "empty_reason": "awaiting_applecard_statement",
                "note": f"no applecard-csv rows for {due.isoformat()[:7]}"}
    if (today - due).days <= latency:
        return {"status": "upcoming", "confidence": 1.0, "empty_reason": None,
                "note": f"within {latency}d match latency"}
    return {"status": "missed", "confidence": 1.0, "empty_reason": None,
            "note": f"no match {(today - due).days}d past due (latency {latency}d)"}


def match_bills(dv: Dataverse, trigger: str, today: date = None) -> dict:
    """Reconcile expected bills against posted transactions.

    Reads and writes state only. Proposes nothing, moves nothing (non-negotiable 1).
    """
    today = today or datetime.now(timezone.utc).date()
    run_id = str(uuid.uuid4())[:8]
    ts = _now()

    # All bills, so cancelled ones still provide a name for superseding their
    # orphaned instances below. Only active + matchable bills are matched.
    all_bills = dv.get(f"{P}_bills?$filter={P}_kind eq 'bill'")["value"]
    name_of = {b[f"{P}_billkey"]: (b.get(f"{P}_name") or "") for b in all_bills}
    active = [b for b in all_bills
              if b.get(f"{P}_status") == "active"
              and b.get(f"{P}_matchmode") in ("merchant", "merchant+amount")]

    # One read of the transaction window, reused across every bill.
    earliest = _add_months(today, -(LOOKBACK_CYCLES + 12)).isoformat()
    txns = dv.get(f"{P}_transactions?$filter={P}_posteddate ge {earliest}"
                  f"&$select={P}_plaidtxnid,{P}_posteddate,{P}_amount,{P}_merchantraw,"
                  f"{P}_isremoved,{P}_istransfer,{P}_sourceenv")["value"]

    existing = {r[f"{P}_instancekey"]: r
                for r in dv.get(f"{P}_billinstances?$select={P}_instancekey,{P}_status,"
                                f"{P}_matchedtxnid")["value"]}

    claimed, counts, changes, touched = set(), {}, [], set()
    for bill in active:
        key, name = bill[f"{P}_billkey"], bill.get(f"{P}_name") or ""
        for due in due_dates(bill, today):
            r = match_one(bill, due, txns, today, claimed)
            if r.get("txnid"):
                claimed.add(r["txnid"])  # one transaction can settle only one cycle

            ikey = f"{key}|{due.isoformat()[:7]}"
            touched.add(ikey)
            prior = existing.get(ikey)
            prior_status = prior.get(f"{P}_status") if prior else None
            counts[r["status"]] = counts.get(r["status"], 0) + 1

            dv.upsert(f"{P}_billinstances", f"{P}_instancekey", ikey, {
                f"{P}_name": f"{name} {due.isoformat()[:7]}"[:200],
                f"{P}_billkey": key,
                f"{P}_duedate": due.isoformat(),
                f"{P}_expectedamount": float(bill.get(f"{P}_expectedamount") or 0),
                f"{P}_actualamount": r.get("actual"),
                f"{P}_status": r["status"],
                f"{P}_matchedtxnid": r.get("txnid"),
                f"{P}_paiddate": r.get("paiddate") or None,
                f"{P}_variancepct": r.get("variance"),
                f"{P}_matchconfidence": r["confidence"],
                f"{P}_emptyreason": r.get("empty_reason"),
                f"{P}_notes": r["note"][:4000],
                f"{P}_freshnessts": ts,
                f"{P}_sourceenv": SOURCE_ENV,
            })

            # Audit on transition only. Every state change is recorded
            # (non-negotiable 2), but a cycle re-confirmed unchanged each night is
            # not a state change -- logging it would bury the real ones.
            if prior_status != r["status"]:
                changes.append({"bill": name, "cycle": ikey,
                                "from": prior_status, "to": r["status"],
                                "confidence": r["confidence"], "why": r["note"]})
                dv.audit("bill.match.transition", "BillInstance", ikey, {
                    "run_id": run_id, "bill": name, "from": prior_status,
                    "to": r["status"], "amount": r.get("actual"),
                    "variance_pct": r.get("variance"), "confidence": r["confidence"],
                    "matched_txn": r.get("txnid"), "why": r["note"],
                    "empty_reason": r.get("empty_reason"),
                })

    # Supersede orphans: any instance we no longer generate. Two causes -- a bill
    # was cancelled (its instances are no longer produced by any active bill), or
    # its cadence changed and the old cycle months no longer line up. Leaving them
    # frozen would keep a stale MISSED or DRIFTED in Amanda's digest forever. This
    # is a write to operational state, never to the append-only audit log.
    superseded = 0
    for ikey, row in existing.items():
        if ikey in touched or row.get(f"{P}_status") == "superseded":
            continue
        billkey = ikey.rsplit("|", 1)[0]
        dv.upsert(f"{P}_billinstances", f"{P}_instancekey", ikey, {
            f"{P}_status": "superseded", f"{P}_freshnessts": ts,
            f"{P}_notes": "no longer generated (bill cancelled or cadence changed)",
        })
        superseded += 1
        dv.audit("bill.match.transition", "BillInstance", ikey, {
            "run_id": run_id, "bill": name_of.get(billkey, billkey),
            "from": row.get(f"{P}_status"), "to": "superseded",
            "why": "instance no longer generated by an active bill",
        })

    skipped = sum(1 for b in all_bills if b.get(f"{P}_status") == "active") - len(active)
    run = {
        "run_id": run_id, "trigger": trigger, "status": "ok",
        "source_env": SOURCE_ENV, "freshness_ts": ts,
        "bills_matched": len(active), "bills_skipped_needs_review": skipped,
        "cycles": sum(counts.values()), "by_status": counts,
        "superseded": superseded,
        "transitions": changes,
        # A4/R13: zero bills is a seeding problem, not a clean result.
        "empty_reason": ("no_matchable_bills" if not active else
                         "clean_empty" if not counts else None),
    }
    dv.audit("bill.match.run", "MatchRun", run_id, {**run, "transitions": len(changes)})
    logging.info("bill match %s: %s cycles, %s transitions", run_id, run["cycles"], len(changes))
    return run


def run_sync(trigger: str) -> dict:
    run_id = str(uuid.uuid4())[:8]
    dv = Dataverse()
    items = dv.get(f"{P}_plaiditems?$filter={P}_active eq true")["value"]
    results, run_status = [], "ok"

    for item in items:
        label = item.get(f"{P}_label", "?")
        try:
            results.append(sync_item(dv, item))
        except Exception as e:  # noqa: BLE001 — any failure must surface as sync_failed, never vanish (R13)
            run_status = "sync_failed"
            code = getattr(e, "code", type(e).__name__)
            logging.exception("sync_failed for %s", label)
            results.append({
                "item": label, "status": "sync_failed", "source_env": SOURCE_ENV,
                "empty_reason": "sync_failed", "error_code": code,
            })
            try:
                dv.update(f"{P}_plaiditems", item[f"{P}_plaiditemid"], {
                    f"{P}_lastsyncstatus": f"sync_failed:{code}"[:100],
                    # lastsyncts NOT updated — freshness only moves on success
                })
            except Exception:
                logging.exception("could not record item failure state")

    run = {"run_id": run_id, "trigger": trigger, "source_env": SOURCE_ENV,
           "status": run_status, "items": results,
           # A4/R13: an empty run must say why. Zero registered items is a config
           # problem, not a clean sync — this ambiguity cost a round-trip on day 1.
           "empty_reason": "no_active_items" if not results else None,
           "finished_at": _now()}
    dv.audit(f"plaid.sync.{run_status}", "SyncRun", run_id, run)
    logging.info("sync run %s: %s", run_id, run_status)

    # Match only on data we know is current. A failed sync means today's postings
    # may be missing, and matching against a stale window would mark paid bills
    # MISSED — the exact false alarm the latency rules exist to prevent.
    if run_status == "ok":
        try:
            run["bill_match"] = match_bills(dv, trigger)
        except Exception as e:  # noqa: BLE001 — matching must never break the sync
            logging.exception("bill matching failed")
            code = getattr(e, "code", type(e).__name__)
            run["bill_match"] = {"status": "match_failed", "error_code": code,
                                 "empty_reason": "match_failed", "source_env": SOURCE_ENV}
            dv.audit("bill.match.failed", "MatchRun", run_id,
                     {"run_id": run_id, "error_code": code, "empty_reason": "match_failed"})
    else:
        run["bill_match"] = {"status": "skipped", "empty_reason": "sync_failed",
                             "source_env": SOURCE_ENV}
    return run


# ---------------------------------------------------------------- triggers

@app.timer_trigger(schedule="%TIMER_SCHEDULE%", arg_name="timer", run_on_startup=False)
def nightly_sync(timer: func.TimerRequest) -> None:
    run_sync("timer")


@app.route(route="sync", auth_level=func.AuthLevel.FUNCTION)
def manual_sync(req: func.HttpRequest) -> func.HttpResponse:
    run = run_sync("manual")
    return func.HttpResponse(json.dumps(run, indent=2), mimetype="application/json",
                             status_code=200 if run["status"] == "ok" else 502)


@app.route(route="match", auth_level=func.AuthLevel.FUNCTION)
def manual_match(req: func.HttpRequest) -> func.HttpResponse:
    """Re-run matching without a sync — for after an Apple Card CSV import."""
    run = match_bills(Dataverse(), "manual")
    return func.HttpResponse(json.dumps(run, indent=2), mimetype="application/json")
