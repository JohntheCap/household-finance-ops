# household-finance-ops — Claude Code context

Household Finance Ops Agent: a household-scale AP + cash-management **control system** (not a budgeting app) for John (operator) and Amanda (co-principal). Plan of record: `Household-Finance-Ops-Agent-PRD-and-Architecture-v1.1.docx` (in the parent Claude folder) — its **v1.1 Reframe Addendum (A1–A12) supersedes v1.0** wherever they conflict. Decisions already made live there and in the Decisions Log; cite, don't re-argue.

## Non-negotiables — never violate

1. **No money movement, ever.** This system reads, organizes, proposes. Humans authorize at the biller. UI verbs are "Acknowledge / Flag", never "Approve / Reject".
2. **Every state change and agent action** writes an `hf_auditlog` row (append-only). No exceptions.
3. **Storage is Dataverse for Teams.** Picked once. No migrations, no side databases.
4. **Tool contract:** every tool response returns `{value, freshness_ts, confidence, source_env}`, and `empty_reason` when empty. A clean-empty result must never be indistinguishable from a failure (`clean_empty` vs `sync_failed` — proven pattern, keep it).
5. **Amanda-first:** if a change makes her weekly digest worse, reject it.
6. **M365-first, low-code-first**, custom code (Azure Functions/Python) only where M365 can't deliver. John maintains this solo. Infra cost cap ~$150/mo (actual ~$0–5/mo — keep it there).

## Environment

- Dataverse: `https://org29b77f3e.crm.dynamics.com` — API `/api/data/v9.2`, solution `householdfinance` (publisher prefix `hf`).
- Auth for scripts: borrow `az login` (see `scripts/create_tables.py`); never hardcode credentials. Function app uses Key Vault (`plaid-access-token-usaa`, `dataverse-client-secret`).
- Tables: `hf_account`, `hf_transaction`, `hf_plaiditem`, `hf_auditlog` — exact columns and alternate keys in `scripts/create_tables.py`. Key facts: `hf_transaction.hf_plaidtxnid` has an alternate key (idempotent upserts); **amounts: negative = outflow** (PRD §6.2); `hf_posteddate` DateOnly; `hf_sourceenv` distinguishes `production` / `sandbox` / (planned) `applecard-csv`.
- Nightly sync: Azure Functions timer 13:00 UTC → Plaid `/transactions/sync` → Dataverse upserts. Live since 2026-07-07, R13 failure contract proven. RUNBOOK.md has ops history.
- Plaid: 1 of 10 Items (USAA — checking …0666 primary/forecast target, checking …0658, Visa …7082). **Visa transactions do NOT arrive via the sync** (payments-only visibility). PAYG since 2026-07-07; per-item price still uncaptured (Decisions Log §4 — open).
- Standing ops: `hf-plaid-sync` client secret expires ~2027-07-07 (`az ad app credential reset` + update KV before then). `ITEM_LOGIN_REQUIRED` recovery: Plaid Link **update mode** (no new Item consumed), log the date.

## Current sprint: 3R (rescoped 2026-07-23 after John's job loss)

The bill-registry *content* is already done: `Household-Monthly-Nut-v2.xlsx` (parent Claude folder) holds every recurring obligation, human-verified — seed data for `hf_bill`. Scope: (a) `hf_bill` table + seed, (b) bill-matching in the nightly sync (arrived/upcoming/missed/drifted, all matches audited), (c) store Plaid `personal_finance_category.detailed`, (d) Apple Card statement-CSV ingest (synthetic key `applecard-<sha256(date|merchant|amount)>` vs the `hf_plaidtxnid` alt key; reclassify checking `APPLECARD GSBANK PAYMENT` as transfers once card spend lands — double-counting is the #1 correctness risk), (e) capture Plaid PAYG pricing. Deferred: retries, immutable audit mirror, digest rendering (Sprint 4). Do not expand scope mid-sprint; when done, propose the next sprint and stop.

## Conventions

- Idempotent everything: re-running any script or import must be safe (check-then-create, alternate-key upserts).
- Python: stdlib + `requests`; match the style of `scripts/create_tables.py` and `functions/function_app.py`.
- Any PowerShell John runs must be **ASCII-only** (Windows PowerShell 5.1 misreads unmarked UTF-8 — em dashes break parsing).
- Word docs for anything shared with Amanda or Jim; markdown for internal notes. File naming: `Household-Finance-Ops-Agent-<topic>-<version>.<ext>`.
- Verify volatile facts (Plaid pricing, Dataverse caps) against current sources before quoting.
