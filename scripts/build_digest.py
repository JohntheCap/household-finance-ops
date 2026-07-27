"""Local preview of the weekly digest (Sprint 4).

Thin wrapper: the assemble+render logic lives in functions/digest.py so the preview
and the production Function App run identical code (no drift). This script only
supplies a Dataverse reader from your az-login session and writes the HTML to a
file. It NEVER sends -- delivery is the Function App's job, gated on John's
go-ahead, and Amanda is never a recipient until go-live.

Auth: borrows your Azure CLI login (az login).

Usage:
  python build_digest.py https://org29b77f3e.crm.dynamics.com [--asof YYYY-MM-DD] [--out path.html]
"""
import datetime as dt
import os
import subprocess
import sys

import requests

# Import the shared digest logic from ../functions.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "functions"))
import digest  # noqa: E402

ENV_URL = sys.argv[1].rstrip("/")
API = f"{ENV_URL}/api/data/v9.2"

ASOF = None
if "--asof" in sys.argv:
    ASOF = dt.date.fromisoformat(sys.argv[sys.argv.index("--asof") + 1])
OUT = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "digest_preview.html"

# John only; Amanda CC intentionally empty until go-live (do not add her to test).
RECIPIENT_TO = "john@johnthecap.com"
RECIPIENT_CC = []


def main():
    token = subprocess.run(
        ["az", "account", "get-access-token", "--resource", ENV_URL,
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, check=True,
        shell=(os.name == "nt")).stdout.strip()   # az.cmd needs shell on Windows; POSIX must not
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/json",
                      "OData-MaxVersion": "4.0", "OData-Version": "4.0"})

    def get(path):
        r = s.get(f"{API}/{path}")
        r.raise_for_status()
        return r.json()["value"]

    today = ASOF or dt.datetime.now(dt.timezone.utc).date()
    payload = digest.assemble(get, today, RECIPIENT_TO, RECIPIENT_CC)
    html = digest.render_preview(payload)   # framed preview; production uses digest.render()
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(html)

    n = payload
    m = digest._money
    print(f"digest built for week ending {n['asof']}  ->  {OUT}")
    print(f"  stale/health-gate: {'STALE (amber)' if n['stale'] else 'fresh (green ok)'}")
    print(f"  paid: {len(n['paid']['items'])} ({m(n['paid']['total'])})  "
          f"upcoming: {len(n['upcoming']['items'])} ({m(n['upcoming']['total'])})")
    print(f"  attention: {len(n['attention']['missed'])} missed, "
          f"{len(n['attention']['pending_statement'])} pending-statement")
    print(f"  nut: {m(n['nut']['minimum'])} vs income {m(n['nut']['income'])} "
          f"= gap {m(n['nut']['gap'])} ({'covered' if n['nut']['covered'] else 'SHORT'})")
    print(f"  recipient: {n['recipient_to']}  cc: {n['recipient_cc'] or '(none - pre-go-live)'}")
    print("  NOT SENT. Open the HTML to review.")


if __name__ == "__main__":
    main()
