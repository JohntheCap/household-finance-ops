# Sprint 6 Proposal - Household Finance Ops Agent

**Author:** Claude (drafted with John) | **Date:** 2026-07-27 | **Status:** DRAFT - awaiting John's sign-off

**Predecessor:** Sprint 5 (budget review) + the envelope-headline change (spec v1, live
2026-07-27) are done. The digest now answers *"are we okay this month?"* with a live
number that moves as spend lands, and warns of the Oregon-UI cliff (~Jan 2027).

---

## Why now

The whole project exists to answer one question during the income transition: **"are we
okay, and what's coming?"** We've now got the *monthly* half of that answer live (the
envelope). The half still missing is the *short-horizon* one Amanda actually feels:

> **"Will checking cover what's due before the next paycheck?"**

The envelope can read healthy while checking is about to dip below zero mid-cycle, because
the envelope is a whole-month plan, not a running cash balance. During a UI-funded runway
with an end date the system already knows about, the timing of cash in vs. bills out is the
risk that bites. This sprint closes that gap.

It's also the right moment structurally: the digest is running John-only (Phase 4), with a
2-week soak before Amanda comes on (Phase 5). Adding the cash line now means that when
Amanda joins, the "are we okay" answer is complete rather than half-built.

## Objective

A **short-horizon cash-runway line** in the weekly digest: current checking balance, minus
bills due before the next income, against a cushion - answering "safe to next payday?" in
plain language. Read-only, same tool contract, same Amanda-first bar.

## Proposed scope

### 1. Store the account balance (the enabling change)
The nightly Plaid sync already fetches the checking balance and **discards it** (flagged in
the Sprint 4 proposal). Add a balance + `balance_asof` column to `hf_account` and persist it
each sync. One column, a few lines in `function_app.py`. Balance is a *snapshot*, so it
carries `freshness_ts` and never renders without it (a stale balance is worse than none).

### 2. Income timing (so "next paycheck" has a date)
The income lines seeded into `hf_bill` (kind='income') carry a monthly amount but **no pay
cadence** yet. Add due-day / anchor data to those rows (reuse the existing `hf_dueday` /
`hf_anchordate` columns) so the forecast knows when the next inflow lands. Human-verified,
same as the bill cadences.

### 3. The runway computation
`checking_balance - (bills due between today and next income) - cushion = safe-to-payday
figure`. Uses `hf_billinstance` upcoming dues (already computed nightly) and the income
cadence from #2. Cushion is a single configurable constant (human-set, like `MINIMUM_NUT`).
Pure function, unit-tested offline like `compute_envelope`.

### 4. Digest render (one line, decision-first)
A single line under the envelope hero: *"Checking $X today; $Y in bills due before the next
paycheck (Aug 1) leaves ~$Z - safe"* or, if it dips, a neutral flag: *"...leaves -$Z before
payday; may need to move something up."* Amber, not alarm. If the balance snapshot is stale
or the account didn't sync, the line says so and shows nothing else (R13 discipline).

### 5. Close the oldest open item: capture Plaid PAYG pricing
Open since Sprint 2 (Decisions Log §4). It's a dashboard read - record the per-Item rate +
last invoice so infra cost is a known line during the tight-budget period. Cheap; it's been
carried three sprints. Fold it in and close it.

## Explicitly deferred (not this sprint)

- **Full forecast v1** (multi-week projected-balance curve, PRD S5). This sprint does the
  *next-payday* slice only - the actionable one. The 30/60/90 projection is its own sprint
  once the single-horizon number is trusted.
- **Reliability hardening** - institution-outage retries (the sync still resets its soak
  counter on a transient failure) + the immutable audit-log mirror (PRD 5.3.4). Deferred
  since Sprint 2. **Strong candidate for Sprint 7, ideally before or alongside Amanda
  go-live** - a silent stale sync is most dangerous exactly when Amanda depends on it. Called
  out here so it doesn't slip a fifth time.
- **Visa …7082 spend visibility** - still payments-only via Plaid; unchanged.
- **"Plan updated" note line** (envelope spec edge case) - needs prior-state comparison; minor.

## Out of scope forever (unchanged)
- Anything touching money movement. The runway line says "you may need to move something up";
  the human moves it, at the biller.

## Open questions for John

1. **Cushion size.** What's the floor you want checking to never drop below (the minus-cushion
   in the runway math)? A number, or "just tell me the raw balance-after-bills."
2. **"Next income" granularity.** Model each income line's own pay date (VA ~1st, Amanda's
   payroll cadence, UI weekly), or simplify to the next date *any* income lands? The former is
   more accurate; the latter is less data to maintain.
3. **One line or a small section?** A single line under the envelope, or its own "Cash this
   week" section? (Amanda-first leans toward one line unless it's earning the space.)

## Risks

- **A wrong "safe" is worse than no line.** If the balance is stale or income timing is off,
  the runway line could say "safe" into an overdraft. Mitigation: hard freshness gate on the
  balance snapshot, and conservative cushion. When unsure, it under-promises.
- **Income-timing maintenance.** Pay dates drift (UI especially). If they're wrong the forecast
  misleads. Keep the cadence data small and human-verified; show the assumed next-income date
  in the line so a wrong date is visible, not silent.
- **Scope creep into full forecasting.** The pull toward "just show the whole month's curve" is
  real. Hold the line at next-payday; the curve is Sprint 7+.
