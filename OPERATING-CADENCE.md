# Operating Cadence — how John engages the finance agent

Two ceremonies: a **weekly check-in** (Sunday/Monday, ~10 min) and a
**month-end close** (1st–3rd, ~30 min). Everything else is ad-hoc ("Amanda
told me X" — just open a session and say it). Written 2026-08-27.

**Starting any session:** open Claude Code in the Claude folder and say
"Finance check-in — read household-finance-ops/OPERATING-CADENCE.md and the
latest KICKOFF file, then run the weekly [or monthly] routine." Keep one
KICKOFF-<date>.md current; the agent updates it as part of each session.

---

## Weekly check-in (after the Sunday 14:00 UTC digest) — ~10 min

The digest is the agent's report card. The weekly is you grading it and
feeding back what the data can't see. Depth belongs in the month-end.

**You, before opening a session (2 min):**

1. Read the digest. Envelope feel right? Anything in "Needs attention"
   actually wrong? Did Amanda get it, and did anything confuse her?
   (Her confusion is a defect, not user error — non-negotiable #5.)

**In the session (~8 min):**

2. **Report life changes.** Cancelled or signed up for something, a price
   changed, Amanda mentioned a payment or debt you haven't seen. The
   registry knows only what the data shows plus what you say.
3. **Name any false flags** from the digest so the agent can fix the bill's
   tolerance/latency/pattern rather than let the noise stand.
4. **Ask what changed and what's stale** — make the agent verify, not just
   record.
5. **Confirm the KICKOFF file was updated** before you close the session.

**The agent's side, every time (no need to ask):**

- Life changes → an idempotent, audited `apply_updates_<date>.py`, run it,
  then re-run `/api/match`, and print the envelope before/after.
- New payments Amanda mentions → search `hf_transaction` FIRST (descriptor +
  amount), report evidence, then register. Externally-paid items get
  `paymentaccount=external, matchmode=none` — never fake match patterns.
- Update the current KICKOFF file's numbers before the session ends.

**Rule of thumb:** past ~15 minutes, the overflow is a month-end or backlog
item — park it, don't expand the session.

---

## Month-end close (1st–3rd of the new month)

> **Step-by-step runbook: `SOP-MONTH-END-CLOSE.md`.** This section is the
> shape of the ceremony; the SOP is the ordered procedure, the register/
> don't-register rules, and the standing traps. Follow the SOP when running
> an actual close.

**1. Feed the card data (you, 5 min).** Wallet → Apple Card → Export
Transactions (prior month) → then in the session:
`py scripts/ingest_applecard.py <url> "<csv>"`. The budget review only
advances once the month's CSV is in.

**2. Close the month (agent, with you watching).**
- `py scripts/envelope_check.py <url> <new-month-01>` — confirm the new
  month's envelope and that any start/end-dated lines flipped correctly
  (sweep start, UI end, future changes).
- Spending review vs budget: what ran hot/cold, one-line verdict per
  category. Decide any budget changes now, not mid-month.
- Reconcile: every recurring debit in checking maps to a registered bill
  (the Tesla-lease lesson: query `hf_bill` match patterns before declaring
  anything "unregistered"). New strays → register or explicitly exclude.
- Debt snapshot: balances/payoff for Harris, Synchrony, USAA Visa, Amex —
  update notes when you have fresh numbers; agent recomputes payoff dates.

**3. Tune the plan (5 min, decisions only you can make).**
- Savings sweep up/down? (`SWEEP` in `scripts/add_savings_sweep.py`, re-run.)
- Extra payment against the highest-APR debt (Amex 16.4%) from any surplus?
- Anything Amanda pays externally that should join the perimeter? (Plaid
  Item #2 decision — weigh PAYG cost, still uncaptured.)

**4. Improvements (last, capped at one).** Each month pick AT MOST one
system improvement (new digest section, matching fix, coverage gap). The
agent proposes candidates from the month's friction; you pick; it ships it
Sprint-style — proposal first if it touches the digest Amanda sees. Bug
fixes for wrong output are exempt from the cap; ship those immediately.

---

## What NOT to do

- Don't edit Dataverse rows by hand — everything goes through an audited
  script (non-negotiable #2), even one-field tweaks.
- Don't change DIGEST_* settings without the restart + verify-cc dance
  (RUNBOOK).
- Don't add bills for things the data can't see without marking them
  `external/none` — fake match config creates false "missed" flags, which
  violates Amanda-first.
- Don't let the agent claim something is/isn't in the registry from memory
  — it must grep `bill_seed_review.csv` or query `hf_bill` first.
