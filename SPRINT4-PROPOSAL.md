# Sprint 4 Proposal - Household Finance Ops Agent

**Author:** John (drafted with Claude) | **Date:** 2026-07-24 | **Status:** SIGNED OFF 2026-07-24

## Decisions (John, 2026-07-24)

- **Surface:** email to john@johnthecap.com. CC Amanda — but **Amanda CC stays OFF
  until the final go-live stage.** All development/test digests go to John only; do
  not load Amanda's inbox with test runs. Adding her CC is an explicit final step.
- **Cadence:** weekly, Sunday 7am.
- **Nut detail:** minimum nut vs. income-still-active gap only. Not the tier breakdown.
- **Attention:** do NOT surface routine bill drift — it will train Amanda to ignore
  the digest. Missed / actionable only.

---

**Predecessor:** Sprint 3R complete - bill registry + matcher live in production (PR #1). Expected-vs-actual bill state (`arrived / upcoming / missed / drifted / unobservable / superseded`) is computed nightly and audited. What's missing is the part a human reads.

---

## Why now

Sprint 3R built the control system's *engine*: every night the matcher knows which bills arrived, which are coming, which are late, which drifted. But that state lives in Dataverse rows nobody looks at. Sprint 4 is the **readout** - the weekly digest that was always the point of the project, and which now has a sharp real-world purpose: during the income transition (Valley Ridge job loss, UI runway to ~Feb 2027), John and Amanda need a shared, trustworthy weekly answer to *"are we okay this week, and what's coming."*

This is the sprint that makes the system Amanda-facing. Non-negotiable 5 (Amanda-first) stops being aspirational and becomes the acceptance test.

## Objective

One weekly artifact, delivered on a rhythm, that answers four questions from data already in Dataverse:

1. **What got paid** this week (arrived bills + amounts).
2. **What's coming** (upcoming bills, next ~10 days, with expected amounts).
3. **What needs attention** (missed, drifted, and any bill still `unobservable` because its Apple Card statement hasn't been imported).
4. **Nut status** - minimum nut vs. income still active, and the gap, tracked against the monthly-nut analysis.

Everything above is a read over `hf_billinstance` + `hf_transaction` + `hf_bill`. No new data sources. The work is rendering, delivery, and the judgment about what Amanda should see.

## Proposed scope

### 1. Digest data assembly (Azure Function or Power Automate)
A read-only assembler that pulls the week's bill instances and transactions and produces a single digest payload: paid / upcoming / attention / nut-status, each with the `{value, freshness_ts, confidence, source_env, empty_reason}` contract intact. Empty sections must say *why* (`clean_empty` vs `sync_failed` vs `awaiting_applecard_statement`) - a blank "nothing due" must never be indistinguishable from a broken sync. This is the same R13 discipline, applied to the reader.

### 2. Rendering
HTML digest (email + Teams-postable), styled from the existing `Amanda-Sunday-Digest-Mock-Sprint1` mock as the visual baseline. Plain-language, decision-first: what's the number, what needs a human. **Acceptance test: if a section would make Amanda's read worse or more anxious, it's cut or reworded.** Drifted/variable bills need care - "Gas was $67, ~$30 over the usual" is a note, not an alarm.

### 3. Delivery rhythm
Sunday-morning cadence (matches the Sprint 1 mock and the PRD S4 "Sunday rhythm"). Delivery via Outlook + Teams (M365-first). One standing scheduled run; failure to deliver is itself an audited event.

### 4. Close the loop on the two open Sprint 3R threads
- **Item (e) - Plaid pricing.** Fold the dashboard read (per-Item rate + last invoice) into this sprint so infra cost is a known line during the tight-budget period. Small, but it's the last Sprint 2/3 exit item.
- **Apple Card monthly ritual.** The digest surfaces `unobservable` cycles; importing the monthly statement (`ingest_applecard.py`, already built) resolves them. Document this as a named monthly step so the `unobservable` bills (LMNT, Apple Card installment) actually get resolved rather than lingering.

## Explicitly deferred (still not this sprint)

- **Institution-outage retries** - the nightly sync still resets its soak counter on a transient failure. Real hardening, but it doesn't block the digest. Sprint 5.
- **Immutable audit-log mirror** (PRD 5.3.4) - append-only blob mirror of `hf_auditlog`. Compliance-grade durability, not a digest dependency. Sprint 5.
- **Forecast v1** (projected balance line, PRD S5) - the nut-status section gives the near-term answer; full forecasting is its own sprint once the digest rhythm is proven.
- **Live "pool spent so far" line** (John, 2026-07-24) - the nut-margin number (e.g. +$898/mo) is currently a static monthly estimate: income-still-active minus the essential nut. Make it live by tracking discretionary spend already posted this month against that margin, so the digest shows "of your $898 monthly room, $X is already spent, $Y left" rather than a flat estimate. Turns the "are we okay" number from a plan into a running balance. Needs a clean tier-3/discretionary spend rollup from `hf_transaction` (categories are stored now, so the data is there) and a month-to-date window. Natural pairing with Forecast v1.
- **Weekly "funds available this week" framing** (John, 2026-07-24) - John raised reframing the hero from a monthly margin to what's actually spendable *this week*. Two interpretations, deferred together: (a) true cash available = current checking balance minus bills due before next income minus a cushion - **requires storing the account balance, which the sync currently fetches from Plaid and discards** (one column + one line to add); (b) weekly slice of the monthly discretionary pool. Revisit as a set with the two items above - they're the same "make the number live and time-boxed" theme. Current plan keeps the monthly essentials-margin hero for now.

## Out of scope forever (unchanged)
- Anything touching money movement. The digest reads and reports; humans act at the biller.

## Open questions - RESOLVED 2026-07-24 (see Decisions block above)

- **Digest surface** - email to John; Amanda CC deferred to go-live. (Teams optional later.)
- **Cadence** - Sunday 7am. Confirmed.
- **Nut detail** - minimum nut vs. income-active + gap only.
- **Attention threshold** - missed/actionable only; routine drift excluded.

## Risks

- **Over-surfacing kills trust.** The single biggest risk: a digest that cries wolf (every variable-bill drift flagged) gets ignored, and then a real missed bill is missed. The attention section must be ruthlessly curated. Amanda-first is the tie-breaker on every inclusion call.
- **`unobservable` read as a problem.** Card-side bills with no statement yet are *absent data*, not late payments; the digest must phrase them as "pending statement," never as a miss.
- **Stale digest on a failed sync.** If Saturday's sync failed, Sunday's digest is stale. It must say so loudly (`freshness_ts` front-and-center) rather than render confidently on old data.
