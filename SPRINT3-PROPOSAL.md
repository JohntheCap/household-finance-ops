# Sprint 3 Proposal — Household Finance Ops Agent

**Author:** John | **Date:** 2026-07-14 | **Status:** Draft for review
**Predecessor:** Sprint 2 complete — Plaid→Dataverse nightly sync proven in production, USAA verdict = pass/R1 retired (see USAA-Plaid-Verdict.md).

---

## Where Sprint 2 left us

The nightly `plaid.sync` (Azure Functions timer → Plaid `/transactions/sync` → Dataverse) is live and stable: 7 consecutive `ok` production nights against real USAA accounts, R13 failure-path proven at the source, IaC in the private repo. What we have is a **sync-only subset** — USAA transactions and accounts land in `hf_transaction` / `hf_account` with correct freshness and source-env stamps. What we don't yet have: Apple Card spend detail, richer categorization, the digest/bill data model, or any resilience hardening. Sprint 3 turns the proven pipe into something usable for actual household budgeting.

## Objectives

1. **Complete the transaction picture** — ingest Apple Card spend so both sides of household spending are captured, without adding a paid third-party data processor.
2. **Make categories trustworthy** — store Plaid's detailed category and get card-payment vs. spending semantics right so nothing is double-counted.
3. **Harden the sync** — institution-outage retries and the immutable audit mirror deferred from Sprint 2.
4. **Extend the data model** — the digest/Bill fields (PRD §6.2) that Sprint 2 deliberately scoped out.
5. **Close the one open Sprint 2 exit item** — capture Plaid production per-item pricing.

## Proposed scope

### 1. Apple Card CSV ingestion (plan of record)

Real-time Apple Card capture was tested and rejected during the soak — the Shortcuts/Wallet Apple Pay trigger only fires on iPhone Apple Pay taps and missed the majority of activity (online card-number purchases, subscriptions, titanium-card swipes, Watch taps). Mechanics worked; coverage didn't. **Plan of record: monthly statement CSV export** (Wallet → Apple Card → statement → Export Transactions → CSV) — complete and authoritative including refunds and Daily Cash, ~1-month latency, acceptable because the checking-side `APPLECARD GSBANK PAYMENT` rows already give the monthly cash-flow signal via Plaid; the CSV adds category-level detail.

Build a CSV ingest (script or HTTP endpoint) that reuses the existing upsert machinery:

- Synthetic idempotency key `applecard-<sha256(date|merchant|amount), truncated to Text(100)>` against the `hf_plaidtxnid` alternate key, so re-imports are safe.
- `hf_sourceenv = applecard-csv`.
- Negate amounts per the outflow convention (§6.2); write one `hf_auditlog` row per import run.
- **Reclassify `APPLECARD GSBANK PAYMENT` checking rows as transfers, not spending**, once card spend lands — otherwise the payment and the underlying purchases double-count.

Rejected alternatives (do not revisit without cause): FinanceKit (restricted entitlement, not feasible for a personal project); FinanceKit-middleware apps like Copilot/Monarch (adds a paid vendor + third data processor for household financials — contrary to the project premise).

### 2. Categorization & semantics fixes (data-quality review, 2026-07-08)

- **Store `personal_finance_category.detailed`, not just primary** — the biggest value gap found. Today groceries and restaurants both collapse to `FOOD_AND_DRINK`. Add a detailed-category column and populate it.
- **Card-payment vs. spending semantics** — `LOAN_PAYMENTS` rows that are actually credit-card payments (Apple Card, Synchrony) need transfer treatment in any downstream budget rollup, same double-count hazard as item 1.
- **Confirm `hf_merchantraw` stores plain text** — one row (Autumn Counseling) appeared to contain a markdown-formatted URL. Almost certainly a chat-rendering artifact, but confirm there's no pipeline injection path writing formatted text into the field.

### 3. Sync hardening (deferred from Sprint 2 by design)

- **Institution-outage retries** — a single failed night currently resets the soak counter and requires manual attention. Add bounded retry/backoff so a transient USAA/Plaid outage doesn't look like a real failure. (Real credential failures like `ITEM_LOGIN_REQUIRED` must still surface, not be retried into silence.)
- **Immutable audit mirror** — the Phase 3 hardening item (PRD §5.3.4): mirror `hf_auditlog` writes to an append-only immutable blob so the audit trail can't be altered in Dataverse.

### 4. Data-model extension — digest / Bill fields

Add the full digest fields (PRD §6.2 Bill etc.) that Sprint 2 scoped out in favor of the sync-only subset. This is the foundation for the actual budgeting/forecasting layer that the primary checking account (…0666) was flagged as the forecast target for.

### 5. Close the open Sprint 2 exit item

**Capture Plaid production per-item pricing** at the Pay-as-you-go upgrade and record it in Decisions Log §4 (both prior figures are unverified per the Volatile-Facts memo). This was the only Sprint 2 exit criterion left open.

## Explicitly out of scope (unchanged, non-negotiable)

- **Anything touching money movement.** Out of scope forever. This project reads and organizes; it never moves money.
- Additional financial institutions beyond USAA + Apple Card, unless a concrete need appears.

## Open questions for review

- **Priority order** — recommend Apple Card CSV ingest (1) + category detail (2) first, since together they complete and de-double-count the spending picture; hardening (3) and the digest model (4) second. Agree?
- **Item budget** — 1/10 Plaid Items used, 9 free. Apple Card via CSV consumes no Item. Any institution we'd want as a live Plaid feed instead of CSV?
- **CSV ingest trigger** — manual drop-a-file-and-run, or a lightweight HTTP endpoint on the existing Function App? Latency is monthly either way, so simplest wins unless there's a reason to automate.

## Risks

- **Apple Card CSV latency (~1 month)** — accepted; the Plaid checking-side payment rows carry the timely cash-flow signal, CSV backfills detail.
- **Double-counting** — the single biggest correctness risk in Sprint 3; both item 1 and item 2 must land the transfer reclassification or card payments inflate spending.
- **Free-trial cliff** — already eliminated (PAYG since 2026-07-07), but the **hf-plaid-sync client secret expires ~2027-07-07**; rotation is a standing operational task, not a Sprint 3 deliverable, but note it so it isn't forgotten.
