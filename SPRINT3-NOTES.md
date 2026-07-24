# Sprint 3 Notes (collected during Sprint 2 soak)

Findings and candidates to fold into the Sprint 3 proposal. Not commitments.

## Apple Card ingestion — pivot (2026-07-09)

**Experiment:** Shortcuts Wallet-transaction automation (fires on Apple Pay tap) logging to a Notes capture log, as a candidate real-time feed.

**Verdict: insufficient coverage — abandoned.** The trigger only fires on Apple Pay taps from the iPhone. It misses card-number online purchases, subscriptions, titanium-card swipes, and Apple Watch taps — which turned out to be the majority of Apple Card activity. Wiring worked end-to-end (trigger → Text → Append to Note); coverage, not mechanics, killed it. Shortcut deleted.

**Plan of record: monthly statement CSV export.** Wallet → Apple Card → Card Balance → statement → Export Transactions → CSV. Complete and authoritative (incl. refunds and Daily Cash adjustments); latency ~1 month, acceptable because the checking-side `APPLECARD GSBANK PAYMENT` rows already provide the monthly cash-flow signal via Plaid — the CSV adds category-level detail.

**Sprint 3 build item:** CSV ingest (script or HTTP endpoint) reusing the existing upsert machinery:

- Synthetic ID `applecard-<sha256 of date|merchant|amount, truncated to fit Text(100)>` against the `hf_plaidtxnid` alternate key (idempotent re-imports).
- `hf_sourceenv = applecard-csv`.
- Negate amounts per outflow convention (§6.2); write `hf_auditlog` row per run.
- Once card spend lands, treat `APPLECARD GSBANK PAYMENT` checking rows as transfers, not spending — otherwise double-counted.

**Rejected alternatives:** FinanceKit (restricted entitlement, not feasible for personal project); FinanceKit-middleware apps like Copilot/Monarch (adds a paid vendor + third data processor for household financials — contrary to project premise).

## Other Sprint 3 candidates (from 2026-07-08 data-quality review)

- **Store Plaid `personal_finance_category.detailed`**, not just primary — biggest value gap found (groceries vs. restaurants both land as FOOD_AND_DRINK today).
- **Card-payment vs. spending semantics:** LOAN_PAYMENTS rows that are credit-card payments (Apple Card, Synchrony) need transfer treatment in any downstream budget rollup.
- **Verify `hf_merchantraw` stores plain text** — one row (Autumn Counseling) appeared to contain a markdown-formatted URL; likely chat-rendering artifact, confirm no pipeline injection.
- Institution-outage retries for the nightly sync (deferred from Sprint 2 by design).
