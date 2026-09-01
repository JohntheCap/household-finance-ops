# SOP — Month-end close (financial agent ops)

`OPERATING-CADENCE.md` says **when** and **why**. This is the **how**: the ordered
procedure, the register rules, and the traps. Written 2026-09-01 from the first
close run end-to-end; the traps below are ones this system actually hit.

**When:** 1st-3rd of the new month, ~45-60 min. **Each step gates the next** —
reviewing unverified data produces a confident, wrong answer.

**Phase 0 (BLOCKING, John only):** export last month's Apple Card CSV —
Wallet -> Apple Card -> Export Transactions. Nothing past step 5 is trustworthy
without it, and the agent cannot do this step.

## The run

| # | Step | Who |
|---|---|---|
| 1 | **Open the session.** Agent reads `OPERATING-CADENCE.md` + latest KICKOFF first. Never assert registry state from memory — query `hf_bill` or grep `bill_seed_review.csv`. | John |
| 2 | **Ingest the card CSV**, dry-run first: `py scripts/ingest_applecard.py <url> "<csv>"`. Note rows, date range, transfer count. | Agent |
| 3 | **Verify the double-count guard.** Every checking-side `APPLECARD GSBANK PAYMENT` must have `hf_istransfer=true`. Expected: **0 unflagged**. If not — STOP, spend is counted twice. | Agent |
| 4 | **Re-run matching:** `GET /api/match`. Record `bills_matched`, `superseded`, `by_status`, every transition. NOT `refresh_and_resend_digest.ps1` — that also resends. | Agent |
| 5 | **Envelope check:** `py scripts/envelope_check.py <url> <new-month-01>`. Confirm start/end-dated lines flipped correctly. | Agent |
| 6 | **Income.** Total real deposits, **always excluding `hf_istransfer`**. | Review |
| 7 | **Spending vs budget** via `functions/budget.py` — never hand-rolled categories. Then read untracked outflows; the 10 categories don't cover fixed bills, and in a deficit month the fixed side is the story. | Review |
| 8 | **Reconcile.** Every recurring debit maps to a registered bill. Query match patterns *before* calling anything unregistered (the Tesla-lease lesson). | Review |
| 9 | **Drift audit** — triage every `drifted` instance (table below). | Review |
| 10 | **One update script:** `scripts/apply_updates_<YYYY-MM-DD>.py` (`b`/`c`/`d` for same-day follow-ups). Idempotent via an `hf_notes` marker; audited with one `hf_auditlog` row per change carrying before/after/evidence; dry-run, apply, then **re-run to prove idempotency** (`applied 0, skipped N`); evidence in the docstring. **Never hand-edit Dataverse.** | Agent |
| 11 | **Re-run `/api/match`, re-check the envelope.** Confirm expected transitions and that nothing new went `missed`. | Agent |
| 12 | **Decisions:** sweep size (`SWEEP` in `add_savings_sweep.py`), extra payment on the highest-APR debt, perimeter additions, and **ONE** system improvement (proposal first if it touches Amanda's digest). **Bug fixes producing wrong output are exempt from the cap — ship immediately.** | John only |
| 13 | **Update the KICKOFF** — new envelope, what changed, what's open, absolute dates (never "next week"). | Agent |
| 14 | **Commit + push** scripts and KICKOFF together; message carries the reasoning. State plainly what was NOT finished. | Agent |

## Triaging a drifted bill

`drifted` = matched a transaction but the amount fell outside tolerance. An
**amount** signal, not a date signal. A bill matching **nothing** is a different
failure — check the pattern before concluding the payment was missed.

| Bucket | Evidence | Action |
|---|---|---|
| Stale seed | Actuals cluster tightly at a value that isn't `expectedamount` | Fix `expectedamount` + `monthlyequivalent` |
| Genuinely variable | Wide spread, usage/season-driven (utilities) | `amounttype=variable` + tolerance covering the worst observed month |
| Resolved price change | Recent months already sit at the registered value | None; it ages out |
| Single anomaly | One month off against a stable history | Watch. **Never move the amount on one data point** |

## What may be registered

**Register:** an observed cadence (2+ occurrences at a consistent interval), or a
known annual charge. **Anchor annual and bimonthly bills to their first observed
charge** — `due_dates()` refuses cycles before the anchor month, which stops a
2-cycle lookback on an annual bill inventing MISSED cycles for years we had no
data (the GoDaddy lesson).

**Do NOT register:**
- A merchant seen **exactly once**. One data point is not a cadence.
- **Per-visit spend** (naturopath, walk-in) — flags MISSED every month it doesn't happen.
- Anything **nobody can identify**. Chase the statement first.
- A **guessed match pattern**. If the descriptor has never appeared in
  `hf_transaction`, set `paymentaccount` honestly and leave `matchmode=none` until
  a real posting reveals it. A guessed pattern is fake match config and produces
  false MISSED flags — an Amanda-first violation.

**When a change is ambiguous, HOLD it.** If the data supports two readings and only
John can choose, gate it behind a `"hold"` flag in the update script with the
reasoning inline, apply everything else, and put the question in the KICKOFF.

## Standing traps

Each has actually bitten. The incident is what makes the rule stick.

| Rule | What happened |
|---|---|
| **Transfers aren't income** | August read $4,297.20 against a true $3,992.97 — Apple Cash and card ACH transfers were summed as deposits |
| **`anchordate` ≠ `startdate`** | `anchordate` controls which cycles exist (matcher); `startdate` controls the envelope window (`digest.py`). Setting `startdate` on the Amex move would have dropped $175 out of a month it was still owed |
| **Descriptors rotate** | Google Fi's pattern was pinned to one month's random token; it matched once by luck and would have reported MISSED forever. Pin the stable prefix, and check the whole history for collisions before widening |
| **Arrears aren't drift** | Two PGE payments in August looked like a matcher gap; they were catch-up on a past-due balance. **Don't widen the match window** — that lets one cycle claim the next cycle's txn. Arrears *balances* are modelled nowhere; `hf_bill` holds cycles, not payoff balances |
| **Hold what's ambiguous** | Harris & Harris: four actuals of exactly $100.00 against a registered $137.50 — either a bad seed or four short payments on a collections account. Opposite actions from identical data |
| **Partial ≠ clean** | Absent data is absent data, never evidence of non-payment (`clean_empty` vs `sync_failed`) |
| **Registry beats memory** | Query before asserting what is or isn't registered. Applies to the agent most of all |
