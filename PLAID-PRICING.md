# Plaid PAYG pricing — Sprint 3R item (e)

**Status: partially closed — the billing *model* is confirmed; the dollar rate needs John's dashboard.**
Verified 2026-07-24 against Plaid's own documentation, not third-party aggregators.

## What is confirmed (authoritative, from Plaid)

- **Transactions bills as a subscription, per Item, per month.** The fee accrues
  "as long as a valid `access_token` exists for the Item" — not per request, not
  per transaction. `/transactions/refresh` is the exception and bills per call;
  our sync never calls it.
- **Pay-as-you-go has no minimum spend and no commitment.** Plaid positions it for
  "hobbyist use, or for early-stage small businesses."
- **Plaid does not publish a price list.** Their docs state pricing is shown on the
  last page of the Production access request flow, and their pricing page defers to
  sales. Several SEO aggregators claim specific figures; none is sourced to Plaid,
  and the Volatile-Facts memo already flags both previously-recorded figures as
  unverified. **Do not record a number from an aggregator.**

## What this means for the budget

The cost driver is **how many Items exist**, not how much the sync runs. Nightly
syncing 1 Item costs the same as syncing it hourly. Two consequences:

1. **An abandoned Item keeps billing.** If a Link flow is ever started and left
   connected, it accrues a monthly fee until `/item/remove` is called. Currently
   1 of 10 Items is in use (USAA), so exposure is one subscription.
2. **Apple Card via CSV consumes no Item** — it stays free by construction, which
   is worth preserving now that the household budget is tight.

## Usage confirmed 2026-07-24 (from John's dashboard export)

`usage-transactions-cumulative-usage.csv` (Transactions Items, cumulative):
**0 Items billed through 2026-07-06, then exactly 1 Item every day from 2026-07-07
to 2026-07-23** — flat at 1. This confirms:

- **Exposure is exactly one Item** (the USAA production Item, live since 2026-07-07).
  The abandoned-Item risk is disproven — no stray Items are accruing fees.
- **Apple Card via CSV consumes no Item**, as designed.

What the export still does NOT give is the **dollar rate per Item** (it is a
quantity page, not a billing page). For budget purposes the material question —
"is infra cost small?" — is answered: 1 PAYG Transactions Item, nothing else.
John's read on 2026-07-24: "not showing much usage," i.e. satisfied it is minimal.

**Item (e) status:** effectively closed for the budget purpose (quantity bounded,
cost minimal). The exact per-Item dollar figure remains uncaptured; record it from
the billing page if/when a precise number is ever needed.

## If a precise dollar figure is ever needed (needs John — requires login)

Two Dashboard pages, both behind authentication:

1. <https://dashboard.plaid.com/activity/usage> — billable activity: Items billed
   this cycle, per product.
2. Dashboard → Billing / Account → the plan page showing the agreed PAYG rate.

Report back: **Transactions per-Item-per-month rate**, and the **last invoice
total**. Those two numbers close Decisions Log §4. Until then the log should say
"PAYG, subscription-per-Item, rate uncaptured" rather than carrying either of the
prior unverified figures.

Sources:
- [Plaid Docs — Billing](https://plaid.com/docs/account/billing/)
- [Plaid — Pricing](https://plaid.com/pricing/)
