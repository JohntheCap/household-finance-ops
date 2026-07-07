# Deployment Values — Household Finance Ops Agent

Non-secret configuration values referenced by RUNBOOK.md placeholders.
**Never put secrets here** (Plaid secrets, client secrets, access tokens → Key Vault only).

| Placeholder | Value | Set in phase |
|---|---|---|
| `<TENANT_ID>` | `7e8aa92f-ab3d-40c3-a7a9-e62694b29cbb` | 0.1 |
| Azure subscription | `Azure subscription 1` — `60094871-01b5-4148-a3cc-f1f0c98bb138` (free trial started 2026-07-07 — **upgrade to pay-as-you-go before ~2026-08-05** or sync dies) | 0.1 |
| GitHub repo | `https://github.com/JohntheCap/household-finance-ops` (private) | 0.4 |
| `<DATAVERSE_URL>` | `https://org29b77f3e.crm.dynamics.com` | 1.1 |
| Environment ID | `1ed355e4-14e3-e58a-aa58-e9410d45c011` | 1.1 |
| Security group | `Household Finance Members` (John, Amanda) | 1.1 |
| `<PLAID_CLIENT_ID>` | *(fill in — Plaid dashboard → Developers → Keys; the client_id is not a secret)* | 0.2 |
| `<CLIENT_ID>` (hf-plaid-sync app registration) | `76d228f9-346d-41b2-b574-4f6136fc52e2` | 1.3 |
| `suffix` (Bicep param) | `hf7x2` | 2.1 |
| `<KV>` (Key Vault name) | `kv-hfin-hf7x2` | 2.1 |
| `<FUNCTION_APP_NAME>` | `func-hfin-hf7x2` | 2.1 |
| Function managed identity principal | `f69412e9-de34-4a00-b232-42d110d9ad78` | 2.1 |
| Subscription upgraded to PAYG | 2026-07-07 — Aug 5 trial cliff eliminated | 2.1 |
| `<PLAID_CLIENT_ID>` (confirmed) | `6a4d1cce93b190000d90e7a2` | 0.2 |
| Dataverse publisher prefix | `hf` | 1.2 |
| hf-plaid-sync client secret expiry | **~2027-07-07** — rotate via `az ad app credential reset` + update Key Vault `dataverse-client-secret`, or sync 401s | 1.3 |
| Plaid plan | Trial (10-Item lifetime cap) — items used: **1/10** (usaa, 2026-07-07) | 0.2 |
| Plaid production per-item price | Not shown on Trial plan as of 2026-07-07; capture at Pay-as-you-go upgrade | 0.2 |
| USAA item | 3 accounts: **Classic Checking …0666 (primary — forecast target)**, Classic Checking …0658, Signature Visa …7082 (USAA portal auto-included all; net effect = original CR-2 scope in 1 Item). KV secret `plaid-access-token-usaa` (rotated 2026-07-07 after screenshot exposure). First production sync 2026-07-07: 476 txns | 6.2 |
