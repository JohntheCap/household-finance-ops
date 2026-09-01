# SOP — Month-end close (financial agent ops)

`OPERATING-CADENCE.md` says **when** the ceremonies happen and **why**. This is
the **how**: the ordered runbook for the month-end close, written 2026-09-01 from
the first full close actually executed end-to-end, including the traps it hit.

**When:** 1st-3rd of the new month. **Duration:** ~45-60 min with the agent.
**Prerequisite:** last month's Apple Card CSV. Nothing past Phase 2 is trustworthy
without it.

---

## Phase 0 — John's blocking prerequisite

Wallet -> Apple Card -> Export Transactions -> prior month. Everything downstream
(spending review, reconcile, debt snapshot) is incomplete until this lands, and
the digest's budget section deliberately hides itself rather than show a partial
month. Do this first; the agent cannot do it for you.

## Phase 1 — Open the session

```
Finance check-in - read household-finance-ops/OPERATING-CADENCE.md and the latest
KICKOFF file, then run the monthly routine. The Apple Card CSV is at <path>.
```

Agent reads the cadence + the current KICKOFF before touching anything. It must
not assert registry state from memory (non-negotiable: query `hf_bill` or grep
`bill_seed_review.csv` first).

## Phase 2 — Ingest and integrity checks

Run in this order. Each step gates the next.

1. **Ingest the card statement**, dry-run first:
   ```
   py scripts/ingest_applecard.py <url> "<csv>" --dry-run
   py scripts/ingest_applecard.py <url> "<csv>"
   ```
   Note the row count, the covered date range, and the transfer-flagged count.

2. **Verify the double-counting guard.** This is CLAUDE.md's stated #1 correctness
   risk, and it only becomes live once card line items exist. Every checking-side
   `APPLECARD GSBANK PAYMENT` row must have `hf_istransfer = true`. Expected
   result: **0 unflagged**. If any are unflagged, STOP — spend is being counted
   twice (once as the checking payment, once as the card lines behind it).

3. **Re-run matching.** After any ingest or `hf_bill` edit:
   `GET /api/match` on `func-hfin-hf7x2`. Record `bills_matched`, `superseded`,
   `by_status`, and every transition.
   **Do not use `refresh_and_resend_digest.ps1` here** — that also resends the
   digest. Only resend if the digest Amanda (or John) received was materially wrong.

4. **Envelope for the new month:**
   ```
   py scripts/envelope_check.py <url> <new-month-01>
   ```
   Confirm any start/end-dated lines flipped correctly (sweep start, draw start,
   subscription ends). A line flipping unexpectedly is the single fastest way to
   ship a fictional envelope.

## Phase 3 — Review (read-only; decide nothing yet)

5. **Income reconciliation.** Total last month's real deposits.
   **Always exclude `hf_istransfer` rows.** Counting internal transfers as income
   is a mistake this system has actually made: August 2026 was recorded as
   $4,297.20 when the truth was $3,992.97, because Apple Cash payments and ACH
   transfers to the card were summed as deposits.

6. **Spending review vs budget.** Use the system's own classifier
   (`functions/budget.py`) so the numbers match what the digest would say — do not
   hand-roll categories. One line per category: actual, budget, delta. Then read
   the untracked outflows, because the 10 budget categories do not cover fixed
   bills, and in a deficit month the fixed side is the story.

7. **Reconcile.** Every recurring debit in checking must map to a registered bill.
   Query `hf_bill` match patterns **before** declaring anything unregistered (the
   Tesla-lease lesson). Collect the strays for Phase 4.

8. **Drift audit.** Pull every `drifted` instance. `drifted` means *matched a
   transaction but the amount fell outside tolerance* — it is an amount signal,
   not a date signal. Triage each into exactly one bucket:

   | Bucket | Evidence | Action |
   |---|---|---|
   | Stale seed | Actuals cluster tightly at a value that is not `expectedamount` | Fix `expectedamount` + `monthlyequivalent` |
   | Genuinely variable | Wide spread, usage- or season-driven (utilities) | `amounttype=variable` + a tolerance that covers the worst observed month |
   | Resolved price change | Recent months already sit at the registered value | No action; it ages out |
   | Single anomaly | One month off against a stable history | **Watch. Do not move `expectedamount` on one data point** |

   A bill matching **nothing** is a separate failure: check the pattern before
   concluding the payment was missed. See "Rotating descriptors" below.

## Phase 4 — Corrections

9. **One script per close:** `scripts/apply_updates_<YYYY-MM-DD>.py`, suffixed
   `b`, `c`, `d` for follow-ups within the same day. Requirements, all
   non-negotiable:
   - **Idempotent** — a per-row marker in `hf_notes`, checked before writing.
   - **Audited** — one `hf_auditlog` row per change, with before/after + evidence.
   - **`--dry-run` first**, then apply, then **re-run it** to prove idempotency
     (expected: `applied 0, skipped N`).
   - Docstring carries the evidence, so a future session can re-derive the reasoning.
   - **Never hand-edit Dataverse rows**, not even one field.
10. **Re-run `/api/match`** after applying. Confirm the transitions are the ones
    you expected and that nothing new went `missed`.
11. **Re-check the envelope** — registry edits move it, and the new number is what
    goes in the KICKOFF.

### What may and may not be registered

- **Register** only what has an observed cadence. Two-plus occurrences at a
  consistent interval, or a known annual charge with an anchor date.
- **Do NOT register** a merchant seen exactly once. One data point is not a
  cadence; a bill row asserts a cycle that has never been observed.
- **Do NOT register** per-visit or per-use spend (a naturopath, a walk-in). It
  will flag MISSED every month it does not happen.
- **Do NOT register** anything nobody can identify. Chase it on the statement first.
- **Do NOT invent a match pattern.** If the descriptor has never appeared in
  `hf_transaction`, set `paymentaccount` honestly and leave
  `matchmode=none` until a real posting reveals the descriptor. A guessed pattern
  is fake match config and produces false MISSED flags — an Amanda-first violation.
- **Anchor annual and bimonthly bills to their first observed charge.**
  `due_dates()` refuses cycles before the anchor month, which is what stops a
  2-cycle lookback on an annual bill inventing MISSED cycles for years we had no
  data (the GoDaddy lesson).

### When a change is ambiguous, HOLD it

If the data supports two readings and only John can choose, do not guess. Gate the
change behind a `"hold"` flag in the update script with the reasoning inline, apply
everything else, and put the question in the KICKOFF. Worked example: Harris &
Harris, four actuals of exactly $100.00 against a registered $137.50 — either a bad
seed (fix it) or four short payments on a collections account (escalate it). Those
lead to opposite actions, so guessing is worse than waiting.

## Phase 5 — Decisions only John makes

- **Savings sweep** size (`SWEEP` in `scripts/add_savings_sweep.py`).
- **Extra payment** against the highest-APR debt (Amex 16.4%) from any surplus.
- **Perimeter additions** — anything paid outside monitored accounts. If it moves
  to an already-synced account, it joins for free and no Plaid Item is consumed.
- **ONE system improvement**, picked last, capped at one. Proposal first if it
  touches the digest Amanda sees.
  **Bug fixes producing wrong output are exempt from the cap — ship immediately.**

## Phase 6 — Close out

12. Update the current KICKOFF: new envelope, what changed, what is still open,
    with absolute dates (never "next week").
13. Commit the update scripts + KICKOFF together; message carries the reasoning,
    not just the file list. Push.
14. State plainly what was NOT finished and why.

---

## Standing traps (all of these have actually bitten)

- **Transfers are not income.** Exclude `hf_istransfer` from every income total.
- **`anchordate` and `startdate` are different levers.** `anchordate` controls
  which cycles exist (the matcher). `startdate` controls the envelope window
  (`digest.py`). Moving a bill's payment method forward is an `anchordate` change;
  setting `startdate` would wrongly drop the obligation out of the envelope for a
  month it is still owed.
- **Rotating descriptors.** Some billers append a random per-month token, and the
  format itself can change. Never pin a pattern to one month's token — Google Fi
  was pinned to `FI 44wQ28` and matched exactly one month by luck. Pin the stable
  prefix, and check the whole transaction history for collisions before widening.
- **Arrears are not drift.** A second payment to the same biller in one month may
  be catch-up on a past-due balance. Confirm with John before calling it a matching
  defect, and **do not widen the match window** — that lets one cycle claim the next
  cycle's transaction. Note that arrears *balances* are not modelled at all:
  `hf_bill` holds recurring cycles, not payoff balances.
- **A partial month is not a clean month.** Absent data is absent data, never
  evidence of non-payment (`clean_empty` vs `sync_failed`).
- **Registry beats memory.** Query before asserting anything about what is or is
  not registered.
