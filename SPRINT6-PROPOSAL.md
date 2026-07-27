# Sprint 6 Proposal - Household Finance Ops Agent

**Author:** Claude (drafted with John) | **Date:** 2026-07-27 | **Status:** SIGNED OFF 2026-07-27

**Decisions (John, 2026-07-27):** cushion **$200**; income modeled per-line with cadence
derived from deposit history; **option (b)** - the monthly envelope stays a plan, the new
weekly runway line is the honest-cash view and excludes Oregon UI until it actually posts;
**cash-runway is this sprint** (reliability hardening is Sprint 7, before Amanda go-live).

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

## Open questions - RESOLVED 2026-07-27 (John)

1. **Cushion size = $200.** Tight, reflecting the limited income during the runway. Checking
   should never be forecast below $200 before payday without flagging it.
2. **Model each income line's own pay date** (more accurate). Cadence DERIVED from
   `hf_transaction` deposit history 2026-07-27 (not guessed):
   - **VA disability** - monthly, fixed **$1,256.90**, posts the **last business day** of the
     prior month (observed 4/29, 5/28, 6/29 -> "for the 1st," a day or two early).
   - **Amanda (Viking Vet)** - **biweekly, every 14 days, Fridays**. Anchor **2026-07-24**;
     next **2026-08-07**, then 8/21, 9/4... Amount varies (~$1,200-1,840; recent ~$1,335) -
     forecast uses a recent typical, not the smoothed monthly-equivalent.
   - **Oregon UI** - **not started; no deposits yet.** Excluded from forecast income until the
     first payment posts (same event that resolves the placeholder amount + start date). Until
     then the envelope's income is overstated by $3,908.67 - see note below.
   - *(Valley Ridge payroll, John's former job, ends with the 7/17 final check - correctly not
     an active income line.)*
3. **One line** under the envelope (default), unless review shows it earns its own section.

## Note surfaced during cadence derivation (2026-07-27)

The envelope headline currently counts **$3,908.67/mo of Oregon UI that has not begun** (no
deposits observed). The number is honest as a *plan* (income John expects) but optimistic as
*cash*. Two clean options, John's call - can ride in this sprint or stand alone:
  - **(a)** Flip the UI income line to a not-yet-active status (or set its `startdate` to the
    real UI start once known) so it drops out of the *envelope* until cash actually arrives,
    with a one-line "assumes UI starts <date>" note; or
  - **(b)** Leave it (plan view) and let only the *runway* line exclude it, so the monthly
    envelope stays a plan while the weekly cash line stays real.
Recommendation: **(b)** - keep the envelope a plan, make the new runway line the honest-cash
view. That's exactly the monthly-plan-vs-weekly-cash split this sprint exists to create.

## Risks

- **A wrong "safe" is worse than no line.** If the balance is stale or income timing is off,
  the runway line could say "safe" into an overdraft. Mitigation: hard freshness gate on the
  balance snapshot, and conservative cushion. When unsure, it under-promises.
- **Income-timing maintenance.** Pay dates drift (UI especially). If they're wrong the forecast
  misleads. Keep the cadence data small and human-verified; show the assumed next-income date
  in the line so a wrong date is visible, not silent.
- **Scope creep into full forecasting.** The pull toward "just show the whole month's curve" is
  real. Hold the line at next-payday; the curve is Sprint 7+.
