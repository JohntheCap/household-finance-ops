# Oregon UI Claim — Session Handoff

**Paste this into a new session to continue work on John's unemployment claim.**
Written 2026-08-31. Everything below is verified from primary sources (Frances Online
message thread, phone calls, and Dataverse transaction records) — not recollection.

---

## Bottom line

John's UI claim has paid **$0.00** since it was filed **2026-07-17**. The cause is known
and is **not** anything John did:

1. His former employer, **Techifi, never reported his wages**, so the claim was ruled
   **monetarily ineligible**.
2. The Department requested documentation on 7/29. John supplied **all of it the same day**.
3. A "Review of Wages" was created 7/30 — but the underlying **investigation was never
   actually requested**. That was discovered by a rep on 8/18, costing **19 days**.

Every claimant-side obligation has been met and **verified by the Department's own staff**.
The remaining delay is entirely internal to the agency.

## Verified chronology

| Date | Event | Source |
|---|---|---|
| 2026-07-17 | Claim filed. Also John's final payroll from prior employer. | Claim record; `hf_transaction` deposit `13584 VALLEY RID PAYROLL` $5,100.32 on 7/17 |
| 2026-07-27 | John messages: "I see a message that says I am monetarily ineligible?" | Frances Online thread |
| 2026-07-29 09:19 | Rep **Ranette Gonzales** requests: 2025 tax returns; payroll/checks Jan–Mar 2025; missing wages Q2 2025, Q3 2025, Q4 2025, Q1 2026. | Frances Online |
| 2026-07-29 09:59 | John uploads ZIP: 2025 tax returns, W-2, pay stubs **Jan 2025 – Mar 2026**. Same day. | Frances Online |
| 2026-07-30 14:24 | Ranette confirms: *"I have uploaded everything and have created a Review of Wages."* | Frances Online |
| 2026-08-18 | **Rep Joshua finds the investigation was NEVER requested** — prior handler failed to initiate it. Joshua initiates it. Confirms **back pay** for weekly claims. Verifies **no gaps** in weekly reporting since the claim began. | Phone call (verbal only — NOT yet in writing) |
| 2026-08-31 | Live chat with rep **Angela**. John asked for investigation status + completion date, and requested escalation on hardship grounds. **OUTCOME NOT YET RECORDED — fill this in.** | Chat transcript |

**Two clocks, and they matter:**
- **45 days** since the claim was filed (7/17 → 8/31).
- **13 days** since the investigation actually began (8/18 → 8/31).
- **19 days** lost to the failure to initiate.

Expect the agency to lean on the 13. The answer: it should have been 45, and the reason
it isn't is theirs.

## Household financial impact (already applied to the finance system)

The UI line had been counting **$3,908.67/mo** of income in the household envelope that has
**never arrived**. Verified 2026-08-30 against `hf_transaction`: zero UI deposits in 59
inflow rows spanning 2026-06-01 → 2026-08-30.

- Corrected via `scripts/apply_updates_2026-08-30.py` (idempotent, audited): UI
  `monthlyequivalent` **$3,908.67 → $0.00**. Committed as `141de04` on `sprint-4-digest`.
- **Do NOT restore a monthly UI figure.** When the agency pays, it is a **one-time back-pay
  lump** — record it as a transaction.
- True household envelope: **−$77.25/mo** (income $4,743.14 − Tier 1 fixed $4,820.39). Fixed
  costs alone exceed income, before any groceries or fuel.
- `DIGEST_CC` (Amanda) was **cleared 2026-08-30** so John can tell her directly rather than
  have the Sunday digest do it. Restore **only** on John's explicit say-so.

## Artifacts

- **`../UI-Claim-Hardship-Summary-2026-08-31.docx`** (parent Claude folder) — one-page
  hardship summary: chronology, five asks, income vs. obligations, call-record block.
  Built by `build_hardship3.js`. Verified single page, no split tables.
- **`KICKOFF-2026-08-30.md`** §4 item 2 — same chronology, condensed.
- Frances Online thread: `https://frances.oregon.gov/Claimant/` (messages #5 and #7).

## Open items

- [ ] **Record the 8/31 Angela chat outcome** — what she said about the investigation status,
      completion date, and escalation. Save the transcript.
- [ ] **Get back pay confirmed IN WRITING.** Joshua's 8/18 confirmation was verbal only. One
      rep's verbal assurance already evaporated once on this claim — that is exactly how the
      19 days were lost. Needs to be in the claim record.
- [ ] **Completion date for Joshua's 8/18 investigation.** Still the single most important
      unknown.
- [ ] **Has the Department contacted Techifi directly?** Reporting wages is the employer's
      legal obligation. Ask what happens if the employer does not respond, and whether wages
      can be credited from John's W-2 and pay stubs instead of waiting on Techifi.
- [ ] **Expedited handling** on the grounds that the 19-day loss was internal error.
- [ ] **Alternate base year** — worth asking as a fallback if the wage review stalls.
      NOT verified against current Oregon rules; pose it as a question, not an entitlement.
- [ ] **Reference numbers + rep names** for every contact. Currently held: Ranette Gonzales
      (7/29–7/30, in writing), Joshua (8/18, verbal), Angela (8/31, in chat).

## Escalation path if the agency stalls

**Constituent services at John's state representative and state senator.** Their staff
routinely unstick agency claims, it is free, and it is the lever most people never pull.
Send them the one-page hardship summary. Trigger this if the 8/31 contact produced no
completion date.

## Standing notes for whoever picks this up

- John has done everything correctly. Documents same-day, weekly reporting gap-free, both
  verified by the agency itself. If a rep implies otherwise, ask them to pull Joshua's
  8/18 notes rather than relitigating it.
- Back pay being confirmed changes the household read: the −$77.25/mo is a **gap while owed
  money sits in a queue**, not a steady state. That distinction matters for how this gets
  discussed with Amanda.
- Never assert a UI payment has or hasn't arrived from memory — query `hf_transaction` for
  deposits first (see `scripts/` for the read-only inflow query pattern).
