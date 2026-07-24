# Weekly Digest - Go-Live Checklist

**Owner:** John | **Created:** 2026-07-24 | **Status:** pre-deploy
Operational checklist for taking the Sprint 4 weekly digest from built-code to
live-to-Amanda. Work top to bottom; each phase gates the next. Detail for any step
is in [RUNBOOK.md](RUNBOOK.md) -> "Sprint 4 - weekly digest". Deep breaths - the
whole thing is designed so nothing reaches Amanda by accident.

**The one rule that governs everything below:** Amanda is the *last* switch, flipped
on purpose. Every phase before go-live sends to John only. She cannot receive a
digest until `DIGEST_CC` is explicitly set - she is never in code.

---

## Phase 0 - Content sign-off (no Azure, no risk)

- [ ] Run the local preview and open it:
      `cd scripts && python build_digest.py https://org29b77f3e.crm.dynamics.com --out digest_preview.html`
- [ ] Hero number reads right (essentials margin, `+$898/mo` framing).
- [ ] `MINIMUM_NUT` and `INCOME_ACTIVE` in `functions/digest.py` are current. **Update the
      Oregon UI figure** once the award letter confirms it (it is a placeholder).
- [ ] Paid / Coming up / Needs attention all look sane against reality.
- [ ] Happy with wording, section order, and what is *excluded* (routine drift stays out).

*Iterate here freely - this step touches nothing in production.*

## Phase 1 - App settings (BEFORE deploy - ordering matters)  -- DONE 2026-07-24

> If `DIGEST_SCHEDULE` is missing when the new code deploys, the Function App fails to
> load **and the nightly sync goes down with it.** Set these first.

**PLATFORM NOTE (learned 2026-07-24):** this app is **Linux Consumption** (`kind:
functionapp,linux`, `reserved:true`). Azure does **NOT** support `WEBSITE_TIME_ZONE`
or `TZ` for timer triggers on Linux Consumption -- setting either is ignored AND can
cause SSL/metrics breakage (diagnostic AZFD0010; host issue #9203 = CryptographicException).
So: **no timezone app setting**, and all NCRONTAB expressions are **UTC**. The nightly
sync's `TIMER_SCHEDULE` (13:00 UTC) is left exactly as soaked -- untouched.

- [x] Set the schedule + recipient + send-off (UTC cron; do NOT set a timezone):
```
az functionapp config appsettings set -g rg-household-finance -n func-hfin-hf7x2 --settings \
  DIGEST_SCHEDULE="0 0 14 * * 0" \
  DIGEST_TO="john@johnthecap.com" \
  DIGEST_SEND="false"
```
  `0 0 14 * * 0` = Sunday 14:00 UTC = **7am PDT** (summer). Fixed-UTC can't track DST, so
  it lands **6am PST** in winter -- accepted 1h seasonal drift (weekly Sunday email).
- [x] `TIMER_SCHEDULE` left at `0 0 13 * * *` (13:00 UTC) -- sync unchanged.
- [x] Confirm `DIGEST_CC` is **not set** (Amanda stays out).
- [x] Sanity-check: `az functionapp config appsettings list ...` shows SCHEDULE=`0 0 14 * * 0`,
      TO, SEND=false, no CC, no TZ/WEBSITE_TIME_ZONE.

## Phase 2 - Graph mail setup (John in the portal - only John can do this)  -- DONE 2026-07-24

App reg: **hf-plaid-sync** (client id `76d228f9-346d-41b2-b574-4f6136fc52e2`, tenant
johnthecap.com `7e8aa92f-...`).

- [x] App registration (`hf-plaid-sync`, same one used for Dataverse) -> API permissions ->
      added **Microsoft Graph -> Application -> Mail.Send**.
- [x] **Granted admin consent** -- verified: SP `82032ae6-...` holds Graph app-role
      `b633e1c5-b582-4048-a93e-9f11b44c7e96` (Mail.Send) and nothing else.
- [x] `DIGEST_FROM="john@johnthecap.com"` set as an app setting.
- [ ] (Recommended, not blocking) scope Mail.Send to just john@johnthecap.com with an
      Exchange **ApplicationAccessPolicy**, so the app can't send as any other mailbox.

## Phase 3 - Deploy + dry run (still nothing sent)  -- DONE 2026-07-24 (deploy fe91fa0)

- [x] Deployed: `func azure functionapp publish func-hfin-hf7x2 --python`. Remote build ok.
- [x] Deploy summary listed all 5: `weekly_digest`, `manual_digest`, `nightly_sync`,
      `manual_sync`, `manual_match`. `weekly_digest` registered => `%DIGEST_SCHEDULE%` bound,
      startup fine.
- [x] **Sync still healthy** - `GET /api/sync` => `status: ok` (USAA checking ok; bill match
      24 matched). Sync unaffected by the deploy.
- [x] Production build previewed: `GET /api/digest` => HTTP 200, crest present, hero `+$898/mo`,
      zero `preview-note` (clean email body, no preview chrome).
- [ ] Wait for / confirm the first Sunday dry run (2026-07-26, 14:00 UTC): audit log shows
      `digest.render` (built, not sent) because `DIGEST_SEND=false`.

## Phase 4 - First real send, John only  -- IN PROGRESS (John-only ride armed 2026-07-24)

- [x] Fired a real send: `GET /api/digest?send=true` => `delivery: sent`.
- [x] Arrived in john@johnthecap.com; renders correctly on Outlook desktop AND mobile
      (hero green box fixed via inline colors; crest shows; budget bars via bgcolor tables).
- [x] Audit log shows `digest.sent`.
- [x] `DIGEST_SEND="true"` set, `DIGEST_CC` still unset -- **John-only Sunday sends are ON**
      (first auto-send Sun 2026-07-26, 14:00 UTC = 7am PDT). Let it ride a week or two.

**Also live (Sprint 5):** 6 months of Apple Card statements imported (Dec 2025-Jun 2026),
so the budget-review section is active and shows the latest complete month (June 2026).

## Phase 5 - Go-live to Amanda (the deliberate final switch)

- [ ] You are genuinely happy with two-plus weeks of John-only digests.
- [ ] Amanda knows it's coming (a heads-up, not a surprise in her inbox).
- [ ] Set her in: `az functionapp config appsettings set ... --settings DIGEST_CC="amanda@..."`
- [ ] Next Sunday, confirm she's on the `To`/`Cc` line and the digest reads well *for her*
      (she's the Amanda-first acceptance test - if a section makes her read worse, pull it).

## Rollback / stop (any time)

- [ ] Stop all sends immediately: `DIGEST_SEND="false"` (timer reverts to silent dry run).
- [ ] Drop Amanda only: unset/blank `DIGEST_CC` (back to John-only, sends continue).
- [ ] Neither touches the nightly sync or any bill data - the digest is read-only.

---

### Quick reference - the gates

| Setting | Off/default | On |
|---|---|---|
| `DIGEST_SEND` | `false` -> builds + audits, sends nothing | `true` -> sends |
| `DIGEST_CC` | unset -> John only | `amanda@...` -> Amanda included |
| `DIGEST_FROM` | unset -> send fails safe (audited) | mailbox -> Graph can send |

All three must be set the "on" way for Amanda to receive anything. That is the design.
