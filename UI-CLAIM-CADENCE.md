# UI Claim — Weekly Pursuit Cadence

How John and the agent work the Oregon UI claim until it pays. Written 2026-08-31,
after a chat that ended in "check back Wednesday" with no timeline and no reference number.

**The problem this solves:** every contact so far has ended with "try back in a few days."
That is a loop, not progress. This cadence is a **ladder** — if a week passes with no
movement, the next contact happens at a higher level automatically. John never has to
decide "is it time to escalate yet?"; the calendar decides.

---

## The rhythm

| When | What | Who |
|---|---|---|
| **Wednesday** | Status check (chat or phone). Log the result. | John, 10 min |
| **Sunday** | Agent review during the weekly finance check-in: read the log, decide if the ladder advances, prep next week's contact. | Agent |
| **Monday** | Execute whatever rung the ladder advanced to. | John |

Two contacts a week, maximum. More than that wastes John's energy on front-line reps who
have no authority over the wage unit.

---

## The escalation ladder

**Advance one rung whenever a week passes with no material change.** "Material change" means
the claim status changed, a determination issued, or someone gave a named commitment with a
date. "Still being worked" is NOT material change — it is the trigger to advance.

| Rung | Action | Advance if... |
|---|---|---|
| **1. Status check** | Frances chat or 877-345-3484. Ask the scripted questions below. | No status change after one week. |
| **2. Written record** | Send a **Contact Us** message through Frances with the full chronology. Chat notes are thin; a written message creates a durable paper trail and may route to a different queue. | No response in 5 business days. |
| **3. Supervisor** | Formally request supervisor escalation, in writing, citing the 19-day failure to initiate. Ask for the supervisor's name. | No supervisor contact within one week. |
| **4. Constituent services** | State representative AND state senator. Send the hardship one-pager plus the contact log. This is the rung that actually moves stuck claims. | No movement within one week. |
| **5. Agency leadership** | Oregon Employment Department director's office / Governor's constituent services. | No movement within one week. |
| **6. Formal posture** | Ask in writing for a written determination so appeal rights attach. **Verify current Oregon procedure before relying on this** — do not assert deadlines or appeal rights that have not been confirmed. | — |

**Rung 4 is not a last resort.** Given a 45-day-old claim with an admitted internal failure,
it is already justified. Do not spend three more weeks on rungs 1–3 out of politeness.

---

## What to ask at every contact (script)

1. What is the current status of the wage investigation, and has anything changed since
   the last contact on `<date>`?
2. Has a determination been issued? If not, what specifically is outstanding?
3. Has the Department contacted Techifi directly for the unreported wages? What happens
   if the employer does not respond?
4. Can the wages be credited from the W-2 and pay stubs already submitted rather than
   waiting on the employer?
5. Please confirm in writing that back pay is approved for all weeks claimed, as rep
   Joshua confirmed 2026-08-18.
6. Please note the financial hardship in my claim record.

**Close every contact with:** "Please note in my claim record that I contacted you today
and what you told me." Frances does not issue reference numbers (confirmed 8/31), so
**screenshot every chat before closing the window** — that is the only record John controls.

---

## What to log, every time

Append a row. This log is the evidence package for rungs 4 and 5 — it is what turns
"I've been waiting forever" into a documented pattern.

| Date | Channel | Rep | What they said | Rung | Next action |
|---|---|---|---|---|---|
| 2026-07-29 | Frances msg | Ranette Gonzales | Requested docs; John supplied all same day | — | — |
| 2026-07-30 | Frances msg | Ranette Gonzales | "Created a Review of Wages" (investigation NOT actually requested) | — | — |
| 2026-08-18 | Phone | Joshua | Found investigation never requested; initiated it; confirmed back pay; verified no gaps in weekly reporting | — | — |
| 2026-08-31 | Chat | Angela | Investigation staged 8/18, wages shown provided 8/26, now "being worked." No timeline. No reference numbers issued. Wage unit is a separate department. Referred to 211. | 1 | Wednesday 9/2 status check |
| 2026-09-02 | | | | | |

---

## Parallel track — do not let the claim be the only plan

Waiting is not a strategy. These run every week regardless of what UI says:

- **Mortgage servicer (M&T).** Ask about hardship/forbearance options **while current** —
  far easier before a missed payment than after. Do this once, early; then only if status changes.
- **211 / Oregon assistance.** Food, energy assistance, school supplies. Angela was right
  that it cannot touch the claim, but it is a real front door for immediate needs.
- **SNAP eligibility (ODHS).** Worth checking given current household income; expedited
  processing exists for households in immediate need. Verify current rules — not asserted here.
- **Weekly claim filing.** Never miss one. Back pay only covers weeks actually claimed.
  Verified gap-free as of 8/18 — keep it that way. This is the one thing that could still
  cost John money, and it is entirely within his control.

---

## Stop conditions

Close this cadence out when **all** of the following are true:

- A determination has issued and the claim is valid.
- The back-pay lump has actually posted (verify in `hf_transaction`, do not take a
  statement as proof — the whole history of this claim is statements that were not true).
- Weekly benefits are arriving on a normal schedule.

Then: record the lump as a one-time transaction, and **only then** consider whether a
recurring UI income line belongs in the registry. Never restore a monthly UI figure on the
strength of a promise.

---

## What NOT to do

- **Don't accept "check back later" as the only outcome of a contact.** Every contact must
  produce either a status change, a named commitment, or a rung advance.
- **Don't re-ask something already answered in writing.** It burns credibility with reps who
  are actually helping. Angela answered the 8/18 question when pushed — that is worth keeping.
- **Don't push front-line reps harder.** They have no authority over the wage unit. Go around,
  not through. Escalation is the lever; volume is not.
- **Don't put John's SSN, DOB, or full address in any file in this repo.** It pushes to GitHub.
  Screenshots of Frances chats stay local, and redact the identity-verification exchange.
- **Don't let a week pass with no contact.** Silence is how a claim goes cold, and this one
  already sat 19 days because nobody was watching it.
- **Don't assert a payment arrived from memory** — query `hf_transaction` for deposits first.

---

## Agent's Sunday job (add to the weekly finance check-in)

1. Read the contact log. Was there a contact this week? What changed?
2. Decide the rung: material change → hold; no change → **advance one rung** and say so plainly.
3. Prep next week's contact — the script above, tailored to what was said last time.
4. Check `hf_transaction` for any UI deposit (the lump, or first weekly payment).
5. Update this file's log table and the KICKOFF file.
6. If the ladder has reached rung 4+, draft the constituent-services package before John asks.
