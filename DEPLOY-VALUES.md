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
| `<CLIENT_ID>` (hf-plaid-sync app registration) | *(fill in at 1.3)* | 1.3 |
| `suffix` (Bicep param) | *(pick 5 chars at 2.1, e.g. `hf7x2`)* | 2.1 |
| `<KV>` (Key Vault name) | *(from Bicep output at 2.1)* | 2.1 |
| `<FUNCTION_APP_NAME>` | *(from Bicep output at 2.1)* | 2.1 |
| Dataverse publisher prefix | `hf` | 1.2 |
| Plaid plan | Trial (10-Item lifetime cap) — items used: 0/10 | 0.2 |
| Plaid production per-item price | *(capture from dashboard screenshot)* | 0.2 |
