# Digest Change Spec - Envelope Countdown Headline (v1)

**Date:** 2026-07-27 | **Author:** Claude (Cowork session) w/ John | **Status:** Approved direction, ready to build
**Applies to:** weekly household digest (Sunday email). Supersedes the static "+$898/mo" headline.

## Problem

The current headline is a *plan* number: `active income - essentials estimate` from the Register. It is constant week to week because nothing in it reads actual transactions. John and Amanda expected a number that moves when they spend. Keep the plan number, demote it to a footnote; make actuals the headline.

## New headline metric: the Monthly Envelope

```
Envelope(month)   = active monthly income - Tier 1 fixed bills (monthly-if-kept)
                  = 8,652 - 4,708 = 3,944   (values as of 2026-07-27; READ LIVE from
                                             income table + hf_bill, never hardcode)
Spent(month-to-date) = sum of qualifying variable spend this calendar month (rules below)
Headline          = Envelope - Spent, with days remaining in month
```

Display: **"$X left of July's $3,944 envelope - N days to go"** plus a one-line pace check
("you're at 62% spent with 55% of the month gone"). ALL variable spending - groceries, gas,
dining, Amazon, cash - counts against one envelope. No category envelopes in v1.

**The envelope is allowed to go negative and must display honestly when it does** (neutral
wording, no blame - Amanda-first). At current variable run rates (~6,100/mo est) it WILL go
negative until cuts land; that visibility is the point of the feature.

## Spend rules - one source per layer, never both

**Layer 1 - Envelope countdown (weekly digest, timely):** source = `hf_transaction`,
`hf_sourceenv=production`, current calendar month, `hf_amount < 0`, `hf_isremoved=false`.

- INCLUDE `APPLECARD GSBANK PAYMENT` rows as card-spend proxy. Rationale: John zeroes the
  Apple Card within ~24h of each purchase, so checking payments mirror card spend in dollars
  with ~1-day lag (verified: 41 discrete payments over 4 months, no monthly lump).
- EXCLUDE rows matched to a Tier 1 bill in `hf_bill` (mortgage, Tesla lease, utilities,
  insurance, Synchrony, Harris & Harris, USAA Visa payment, etc.) - those are the fixed side.
- EXCLUDE refunds/credits netting: positive amounts in qualifying categories reduce Spent.
- Transfers to Banner Bank ...5444 (travel savings), if they ever appear in checking: count as
  spend (money leaving the household budget is spend, even when it's saving for travel).

**Layer 2 - Category detail (monthly, when statement CSVs are ingested):** source = Apple Card
CSV rows, `Type != Payment`. Payments excluded here because Layer 1 already counted the dollars.
Used for the monthly workbook/registry refresh, never for the weekly countdown.

## Income side

Sum of income rows flagged active: VA 1,256.90 + Viking Vet est 3,486 + Oregon UI 3,909
(PLACEHOLDER - replace with actual WBA when first payment posts; carries end date ~late Jan
2027, after which it drops out automatically and the envelope shrinks - the digest should
show a one-line warning starting 4 weeks before that cliff).

## Digest layout (Amanda-first)

1. Headline: envelope remaining + days left + pace line.
2. Paid this week (existing fixed-bill list - keep).
3. Upcoming bills next 7 days (from hf_bill expected dates).
4. Footnote: "Plan check: essentials covered, +$898/mo structural headroom" (the old headline).
5. Freshness line: "As of last night's sync (Sat)." If the last sync was not `ok`, say so
   plainly - never render a countdown from stale data without a warning (tool contract:
   empty/stale must never look clean).

## Edge cases

- Month boundary: envelope is calendar-month. First digest of a new month shows the fresh
  envelope plus one recap line for last month (spent vs envelope, over/under).
- `clean_empty` sync nights are normal - not a freshness warning.
- Mid-month plan changes (a cut, UI amount lands): envelope recalculates from live values;
  add a "plan updated" note line that week.

## Acceptance

- Two consecutive weekly digests show DIFFERENT headline numbers when spending occurred.
- A test grocery purchase moves the countdown by that amount within 2 syncs.
- Sum(Layer 1 spend) for a closed month reconciles to workbook variable actuals within the
  card-timing lag; no transaction counted in both layers.
- Digest generation writes an `hf_auditlog` row (non-negotiable #7).
