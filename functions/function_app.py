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
from datetime import datetime, timezone

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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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

    def get(self, path):
        r = self.s.get(f"{self.base}/{path}")
        r.raise_for_status()
        return r.json()

    def create(self, table, record):
        r = self.s.post(f"{self.base}/{table}", data=json.dumps(record))
        r.raise_for_status()

    def upsert(self, table, keycol, keyval, record):
        # Alternate-key upsert: PATCH /table(keycol='keyval')
        r = self.s.patch(f"{self.base}/{table}({keycol}='{keyval}')", data=json.dumps(record))
        r.raise_for_status()

    def update(self, table, guid_, record):
        r = self.s.patch(f"{self.base}/{table}({guid_})", data=json.dumps(record))
        r.raise_for_status()

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
        dv.upsert(f"{P}_transactions", f"{P}_plaidtxnid", t["transaction_id"], {
            f"{P}_posteddate": t["date"],
            f"{P}_amount": -t["amount"],  # Plaid: positive = outflow; our model: negative = outflow (§6.2)
            f"{P}_merchantraw": (t.get("name") or "")[:200],
            f"{P}_category": (t.get("personal_finance_category") or {}).get("primary", ""),
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
           "status": run_status, "items": results, "finished_at": _now()}
    dv.audit(f"plaid.sync.{run_status}", "SyncRun", run_id, run)
    logging.info("sync run %s: %s", run_id, run_status)
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
