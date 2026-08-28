# Operating Cadence — how John engages the finance agent

Two ceremonies: a **weekly check-in** (Sunday/Monday, ~10 min) and a
**month-end close** (1st–3rd, ~30 min). Everything else is ad-hoc ("Amanda
told me X" — just open a session and say it). Written 2026-08-27.

**Starting any session:** open Claude Code in the Claude folder and say
"Finance check-in — read household-finance-ops/OPERATING-CADENCE.md and the
latest KICKOFF file, then run the weekly [or monthly] routine." Keep one
KICKOFF-<date>.md current; the agent updates it as part of each session.

---

## Weekly check-in (after the Sunday 14:00 UTC digest)

The digest is the agent's report card. The weekly session is you grading it
and feeding back what the data can't see.

**1. Read the digest first (2 min, no Claude needed).** Three questions:
- Does the envelope number feel right? (Any surprise = agenda item.)
- Is anything in "Needs attention" actually wrong (false missed/drifted)?
- Did Amanda get it, and did anything confuse her? (Non-negotiable #5:
  her confusion is a defect, not user error.)

**2. Open a session and report life changes (5 min).** The registry only
knows what checking/card data shows plus what you say. Standing prompts:
- "We cancelled / signed up for X" → agent writes an `apply_updates_<date>.py`
  (idempotent, audited), runs it, then re-runs `/api/match`.
- "X's price changed" → same pattern, envelope before/after printed.
- "Amanda mentioned a payment/debt I haven't seen" → agent searches
  `hf_transaction` for it FIRST (descriptor + amount pattern), reports
  evidence, then registers it. Externally-paid items get
  `paymentaccount=external, matchmode=none` — no fake match patterns.

**3. Have the agent verify, not just record (3 min).** Standing checks:
- False flags in "Needs attention" → fix tolerance/latency/pattern on the
  offending bill (Google Fi precedent: latency 30, tolerance 50%).
- Any digest section stale? → `/api/match` was skipped after a bill edit;
  run it (`scripts/refresh_and_resend_digest.ps1` re-matches AND resends —
  only resend if the sent digest was materially wrong).
- Agent updates the current KICKOFF file's numbers before the session ends.

**Rule of thumb:** if a weekly session runs past ~15 minutes, the overflow
is a month-end or backlog item — park it, don't expand the session.

---

## Month-end close (1st–3rd of the new month)

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
