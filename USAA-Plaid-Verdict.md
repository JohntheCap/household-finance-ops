# USAA–Plaid Compatibility Verdict

**Sprint:** 2 (Azure Foundation + Plaid Sync) | **Phase:** 7 (7-night production soak + verdict)
**Author:** John | **Date:** 2026-07-14
**Decision:** ✅ **R1 RETIRED.** USAA is Plaid-compatible for our use case. No re-auth prompts, no sync failures across the full soak.

---

## Verdict in one line

USAA authenticated cleanly via Plaid's production OAuth flow and delivered **7 consecutive nightly `ok` syncs with zero `ITEM_LOGIN_REQUIRED` and zero `sync_failed` events.** The risk that motivated R1 — that USAA would force frequent re-auth and make an automated feed impractical — **did not materialize.** R1 is retired; USAA runs as a live automated feed, not parked manual-entry.

## Institutions tested

| Institution | Plaid Item | Accounts covered | Products | Result |
|---|---|---|---|---|
| USAA | 1 Item (`usaa-checking`, KV secret `plaid-access-token-usaa`) | 3 — Classic Checking …0666 (primary, forecast target), Classic Checking …0658, Signature Visa …7082 | `transactions` | **Pass** |

USAA's portal auto-included all three accounts under a single Link authorization, so the original CR-2 scope (checking + a card) landed inside **1 Item** rather than the 2 budgeted. The separate card-issuer Item planned for Wave 1 was **not consumed** — Apple Card ingestion was pivoted to monthly statement-CSV export during the soak (see SPRINT3-NOTES.md), so no second production Item was spent.

## Error codes observed

**None.** No `ITEM_LOGIN_REQUIRED`, no `sync_failed`, no Plaid error codes of any kind across all 7 production nights (2026-07-08 → 2026-07-14). The R13 forced-failure path (`ITEM_LOGIN_REQUIRED` → `plaid.sync.sync_failed`, no silent empty) was proven **at the source** in Phase 4 (sandbox), so the pipeline's failure handling is verified even though production never exercised it.

## Item slots consumed

**1 of 10** (Trial plan, lifetime cap). USAA = 1 Item. 9 slots remain. The planned card-issuer Item was released back to the budget by the Apple Card CSV pivot.

## Soak record (7 consecutive `ok` nights)

All runs: `trigger: timer`, `source_env: production`, timer fired 13:00 UTC nightly, freshness_ts ~13:00:05 UTC.

| Night | Date | Status | added / modified / removed | Notes | run_id |
|---|---|---|---|---|---|
| 1 | 2026-07-08 | ok | 1 / 0 / 0 | | f2310ac5 |
| 2 | 2026-07-09 | ok | 3 / 0 / 0 | | f91d6ae8 |
| 3 | 2026-07-10 | ok | 4 / 0 / 0 | back-filled from audit log | 0a8b8c5a |
| 4 | 2026-07-11 | ok | 0 / 0 / 0 | `clean_empty` (distinguishable from failure) | 645edbeb |
| 5 | 2026-07-12 | ok | 14 / 1 / 0 | | 0e1b0dd9 |
| 6 | 2026-07-13 | ok | 0 / 0 / 0 | `clean_empty` | 4e084162 |
| 7 | 2026-07-14 | ok | 15 / 0 / 0 | | bc5c9f86 |

**Soak totals:** 37 transactions added, 1 modified, 0 removed. Initial production backfill (2026-07-07, pre-soak) loaded 476 transactions.

Two `clean_empty` nights (4 and 6) that reported `ok`/`empty_reason: clean_empty` — rather than looking like failures — confirm the R13 contract holds in production, not just in the sandbox test: a quiet night and a broken night are distinguishable in the audit log.

## Sprint exit criteria — status

- ✅ 7 consecutive nightly syncs from real accounts; rows landing with correct `hf_freshnessts` + `hf_sourceenv=production`.
- ✅ Phase 4 forced-failure produced `sync_failed` (never silent empty); clean-empty control produced `clean_empty`.
- ✅ USAA compatibility verdict documented (this file) — **pass, R1 retired.**
- ✅ IaC + function code pushed to the private repo (`github.com/JohntheCap/household-finance-ops`).
- ⏳ Plaid production per-item pricing — **still not captured.** Not shown on the Trial plan; capture at the Pay-as-you-go upgrade (Decisions Log §4 remains open). This is the one outstanding exit item and it carries into Sprint 3.

## Standing operational notes (carry forward)

- **`ITEM_LOGIN_REQUIRED` is still expected eventually** — USAA can force re-auth at any time. It did not during this soak, but the runbook recovery holds: re-run the Plaid quickstart Link in **update mode** (token stays valid, **no new Item consumed**), log the date. Frequency of this event over time remains the living R1 signal.
- **Free-trial cliff eliminated** — subscription upgraded to Pay-as-you-go 2026-07-07, so the Aug 5 trial expiry no longer threatens the sync.
- **hf-plaid-sync client secret expires ~2027-07-07** — rotate via `az ad app credential reset` + update Key Vault `dataverse-client-secret` before then, or the sync 401s.
