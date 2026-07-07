"""Create a Plaid *sandbox* Item without Link UI, print the access_token.

Usage:
  set PLAID_CLIENT_ID=...   (PowerShell: $env:PLAID_CLIENT_ID="...")
  set PLAID_SECRET=...      (your SANDBOX secret)
  python sandbox_item.py            -> creates item at First Platypus Bank
  python sandbox_item.py reset TOKEN -> forces ITEM_LOGIN_REQUIRED on TOKEN (R13 forced-failure test)
"""
import os
import sys

import requests

BASE = "https://sandbox.plaid.com"
AUTH = {"client_id": os.environ["PLAID_CLIENT_ID"], "secret": os.environ["PLAID_SECRET"]}


def post(path, body):
    r = requests.post(BASE + path, json={**AUTH, **body}, timeout=30)
    r.raise_for_status()
    return r.json()


if len(sys.argv) > 1 and sys.argv[1] == "reset":
    print(post("/sandbox/item/reset_login", {"access_token": sys.argv[2]}))
    print("Item is now in ITEM_LOGIN_REQUIRED. Next sync run MUST report sync_failed.")
else:
    pub = post("/sandbox/public_token/create", {
        "institution_id": "ins_109508",  # First Platypus Bank
        "initial_products": ["transactions"],
    })["public_token"]
    resp = post("/item/public_token/exchange", {"public_token": pub})
    print("access_token:", resp["access_token"])
    print("item_id:     ", resp["item_id"])
    print("\nStore it:  az keyvault secret set --vault-name <kv> --name plaid-access-token-sandbox-platypus --value <access_token>")
