# Runbook: Sprint 2 — Azure Foundation + Plaid Sync (sandbox → production)

**Owner:** John | **Frequency:** One-time build; Phase 7 checks run nightly for 7 nights
**Last updated:** 2026-07-07 | **Last run:** —

## Purpose

Stand up the minimum Azure subset (§A1 Sprint 2), prove Plaid `/transactions/sync` → Dataverse end-to-end in sandbox, prove the R13 forced-failure path **at the source**, then enroll real USAA checking + one card (CR-2) and retire R1 with a documented USAA verdict. You execute every step; Claude never holds Plaid/Azure credentials. Per CR-1 (2026-07-07), the store is a **full Dataverse environment**, not Dataverse for Teams.

Commands are PowerShell. `<angle-bracket>` values are yours to fill. Stop at any ⛔ gate until the expected result matches.

## Prerequisites

- [ ] Windows machine with: [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli), [Azure Functions Core Tools v4](https://learn.microsoft.com/azure/azure-functions/functions-run-local), Python 3.11, git, a GitHub account
- [ ] M365 household-tenant admin credentials (John)
- [ ] Amanda has read Plaid's data-use disclosure and acknowledged before the first production sync (CR-4 — John executes Link solo; co-presence not required)
- [ ] Credit card for Azure signup (spend in this sprint: ≈ $0–5/mo) and for Power Apps Premium (~$20/user/mo — verify current price at purchase)

## Procedure

### Phase 0 — Accounts, licensing, repo

**0.1 Azure subscription.** Sign up at https://azure.microsoft.com/free with your household-tenant admin account (NOT a personal Microsoft account — the subscription must live in the M365 tenant so Managed Identity and Entra work). Pay-as-you-go after free credits.
**Expected:** `az login` then `az account show` prints your tenant ID matching the M365 tenant.
**If it fails:** `az account show --query tenantId` mismatch → you signed up with the wrong identity; create the subscription from the Azure portal while logged in as the tenant admin.

**0.2 Plaid account + Trial plan.** Create a team at https://dashboard.plaid.com/signup, verify email, then apply at https://dashboard.plaid.com/trial-plan.
**Expected:** Dashboard shows Sandbox keys immediately; Trial plan grants Production access with the 10-Item lifetime cap.
📸 **Capture the price:** if any pricing page is shown during the Production/Trial request, screenshot it and update Decisions Log §4 (both existing figures are unverified — see Volatile-Facts memo).
**If it fails:** Trial plan requires US/Canada teams created on/after 2026-04-15; if rejected, request Pay-as-you-go Production access instead — sandbox phases proceed regardless.

**0.3 Power Apps Premium license (CR-1 prerequisite).** M365 admin center → Billing → Purchase services → Power Apps Premium → 1 license → assign to John.
**Expected:** Power Platform admin center (https://admin.powerplatform.microsoft.com) → Resources → Capacity shows Dataverse database capacity ≥ 1 GB available.
**If it fails:** capacity page shows 0 available → the license hasn't propagated (wait 1h) or the tenant needs the default capacity granted with the first premium license; contact M365 support before proceeding.

**0.4 Private repo (IaC is the DR artifact, PRD §5.2.4).**
```powershell
cd <your-code-folder>; mkdir household-finance-ops; cd household-finance-ops
# copy the Household-Finance-Sprint2 folder contents (infra/, functions/, scripts/) here
git init; git add -A; git commit -m "Sprint 2: Azure foundation + plaid_sync"
gh repo create household-finance-ops --private --source . --push   # or create on github.com and push
```
**Expected:** private repo visible on GitHub with infra/ and functions/.

### Phase 1 — Dataverse environment + tables (CR-1)

**1.1 Create environment.** Power Platform admin center → Environments → New: Name `Household Finance`, Type **Production**, Add Dataverse database = Yes, security group = (create/use a group containing John + Amanda).
**Expected:** environment URL like `https://org12345.crm.dynamics.com` — record it as `<DATAVERSE_URL>`.

**1.2 Create publisher + tables.** In https://make.powerapps.com (Household Finance environment) → Solutions → New solution `HouseholdFinance`, new publisher with prefix **`hf`**. Inside the solution create four tables (Settings → Advanced → set exact schema names):

| Table (schema name) | Columns (schema name → type) |
|---|---|
| `hf_account` | `hf_plaidaccountid` Text(100) **+ alternate key**; `hf_name` Text(120); `hf_mask` Text(10); `hf_type` Text(50); `hf_freshnessts` Text(40); `hf_sourceenv` Text(20) |
| `hf_transaction` | `hf_plaidtxnid` Text(100) **+ alternate key**; `hf_posteddate` Date only; `hf_amount` Currency; `hf_merchantraw` Text(200); `hf_category` Text(60); `hf_ispending` Yes/No; `hf_isremoved` Yes/No; `hf_plaidaccountid_text` Text(100); `hf_freshnessts` Text(40); `hf_sourceenv` Text(20) |
| `hf_plaiditem` | `hf_label` Text(80); `hf_kvsecretname` Text(120); `hf_cursor` Multiline(4000); `hf_active` Yes/No; `hf_lastsyncstatus` Text(100); `hf_lastsyncts` Text(40) |
| `hf_auditlog` | `hf_timestamp` Text(40); `hf_actor` Text(80); `hf_action` Text(80); `hf_entitytype` Text(40); `hf_entityid` Text(80); `hf_context` Multiline(4000) |

Alternate keys: table → Keys → New key on `hf_plaidaccountid` / `hf_plaidtxnid` (enables idempotent upserts).
**Expected:** keys show status Active after a few minutes.
**If it fails:** key stuck "In progress" > 15 min → check for duplicate rows (there are none yet; retry).
*Note:* `hf_auditlog` is append-only by convention in Sprint 2 (the sync only ever creates). The immutable-blob mirror is a Phase 3 hardening item (PRD §5.3.4). Full digest fields (§6.2 Bill etc.) come in Sprint 3 — this is deliberately the sync-only subset.

**1.3 App registration + application user (the Function's identity into Dataverse).**
```powershell
az ad app create --display-name hf-plaid-sync --query appId -o tsv        # -> <CLIENT_ID>
az ad sp create --id <CLIENT_ID>
az ad app credential reset --id <CLIENT_ID> --years 1 --query password -o tsv  # -> <CLIENT_SECRET>, shown once
az account show --query tenantId -o tsv                                   # -> <TENANT_ID>
```
Then: Power Platform admin center → Environments → Household Finance → Settings → Users + permissions → **Application users** → New app user → select `hf-plaid-sync` → Business unit (default) → Security role: create/assign a custom role `HF Sync Writer` with org-level Create/Read/Write on the four `hf_` tables only (least privilege — no delete).
**Expected:** app user listed with the role.
**If it fails:** app not selectable → the `az ad sp create` step was skipped.

### Phase 2 — Azure foundation (IaC)

**2.1 Deploy.**
```powershell
az group create -n rg-household-finance -l westus2
$me = az ad signed-in-user show --query id -o tsv
az deployment group create -g rg-household-finance -f infra/main.bicep `
  -p suffix=<5chars> adminObjectId=$me plaidEnv=sandbox `
     plaidClientId=<PLAID_CLIENT_ID> dataverseUrl=<DATAVERSE_URL>
```
**Expected:** outputs show `functionAppName`, `keyVaultName`, `functionPrincipalId`. Record all three.
**If it fails:** Key Vault name taken (globally unique) → change `suffix`. RBAC role assignment errors → you need Owner on the subscription (you are; re-run, it's idempotent).

**2.2 Secrets into Key Vault.**
```powershell
az keyvault secret set --vault-name <KV> --name plaid-secret-sandbox   --value <PLAID_SANDBOX_SECRET>
az keyvault secret set --vault-name <KV> --name dataverse-tenant-id     --value <TENANT_ID>
az keyvault secret set --vault-name <KV> --name dataverse-client-id     --value <CLIENT_ID>
az keyvault secret set --vault-name <KV> --name dataverse-client-secret --value <CLIENT_SECRET>
```
**Expected:** 4 secrets. (`plaid-secret-production` is added in Phase 6, not before — env separation, §A9.)

**2.3 Deploy the function.**
```powershell
cd functions
func azure functionapp publish <FUNCTION_APP_NAME>
```
**Expected:** publish succeeds and lists `nightly_sync` (timerTrigger) and `manual_sync` (httpTrigger). Startup does not throw — the code asserts `PLAID_ENV` on load (§A9).

### Phase 3 — Sandbox end-to-end ⛔ gate

**3.1 Create a sandbox Item (no Link UI needed).**
```powershell
$env:PLAID_CLIENT_ID="<PLAID_CLIENT_ID>"; $env:PLAID_SECRET="<PLAID_SANDBOX_SECRET>"
python scripts/sandbox_item.py
az keyvault secret set --vault-name <KV> --name plaid-access-token-sandbox-platypus --value <access_token>
```

**3.2 Register the Item in Dataverse.** In the Power Apps table view, add one `hf_plaiditem` row: label `sandbox-platypus`, kvsecretname `plaid-access-token-sandbox-platypus`, active `Yes`, cursor empty.

**3.3 Run and verify.**
```powershell
$code = az functionapp function keys list -g rg-household-finance -n <FUNC> --function-name manual_sync --query default -o tsv
curl.exe "https://<FUNC>.azurewebsites.net/api/sync?code=$code"
```
**Expected:** HTTP 200; JSON shows `"status": "ok"`, `"source_env": "sandbox"`, added > 0. In Dataverse: `hf_transaction` rows exist with `hf_sourceenv = sandbox` and `hf_freshnessts` set; `hf_account` rows exist; one `hf_auditlog` row `plaid.sync.ok`; `hf_plaiditem.hf_cursor` is now non-empty.
**If it fails:** see Troubleshooting. Do not proceed past this gate.

### Phase 4 — R13 forced-failure test ⛔ gate (test at the source, this sprint)

**4.1 Break it deliberately.**
```powershell
python scripts/sandbox_item.py reset <access_token>
curl.exe "https://<FUNC>.azurewebsites.net/api/sync?code=$code"
```
**Expected — all four, exactly:**
1. HTTP **502**, run JSON `"status": "sync_failed"`, item `"empty_reason": "sync_failed"`, `"error_code": "ITEM_LOGIN_REQUIRED"`.
2. `hf_auditlog` row `plaid.sync.sync_failed` exists.
3. `hf_plaiditem.hf_lastsyncstatus = sync_failed:ITEM_LOGIN_REQUIRED`; **`hf_lastsyncts` did NOT advance**; cursor unchanged.
4. Zero new `hf_transaction` rows. A broken sync must never look like a clean empty.

**4.2 Clean-empty control.** Run the sync again *without* fixing anything on a second, healthy sandbox item that has no new transactions (re-run 3.3 twice back-to-back on the fixed item after `/sandbox/item/reset_login` recovery, or create a second item):
**Expected:** `"status": "ok"` with `"empty_reason": "clean_empty"` — the two empties are distinguishable in the run log. This is the R13 contract, proven at the source.

⛔ Both 4.1 and 4.2 must pass before any real account is touched.

### Phase 5 — Flip to production (Trial plan)

```powershell
az keyvault secret set --vault-name <KV> --name plaid-secret-production --value <PLAID_PRODUCTION_SECRET>
az functionapp config appsettings set -g rg-household-finance -n <FUNC> --settings PLAID_ENV=production
```
Deactivate the sandbox item row (`hf_active = No`). Sandbox rows stay in Dataverse, clearly marked `hf_sourceenv = sandbox` — filter them out of anything downstream; purge is optional at sprint end.
**Expected:** next run with no active items = `ok` with zero items processed.

### Phase 6 — USAA Link session (John solo per CR-4, ~30 min, Wave 1 per CR-2)

**Item budget reminder:** Trial = 10 Production Items, lifetime, no refunds on removal. This session should consume exactly 2 (USAA = 1 Item covering checking; card issuer = 1 Item). Abort a Link attempt *before* credential submission if anything looks off — abandoned pre-auth attempts don't create Items.

**6.1** Clone and run Plaid quickstart to host Link locally:
```powershell
git clone https://github.com/plaid/quickstart; cd quickstart\python
# .env: PLAID_CLIENT_ID, PLAID_SECRET=<production secret>, PLAID_ENV=production, PLAID_PRODUCTS=transactions
```
Follow the quickstart README to run backend + frontend; open http://localhost:3000.

**6.2** Link → search **USAA** → authenticate (expect USAA's own OAuth flow; MFA prompts are normal) → select checking. Copy the `access_token` + `item_id` the quickstart prints. Repeat for the credit card institution.
```powershell
az keyvault secret set --vault-name <KV> --name plaid-access-token-usaa --value <token1>
az keyvault secret set --vault-name <KV> --name plaid-access-token-<cardissuer> --value <token2>
```
Add two `hf_plaiditem` rows (labels `usaa-checking`, `<cardissuer>-card`), active Yes. Delete the tokens from the quickstart terminal/scrollback. ⛔ **CR-4 gate: do not run the first production sync (6.3) until Amanda has read Plaid's data-use disclosure (PRD §3.3) and acknowledged.**

**6.3** Trigger a manual sync (as 3.3).
**Expected:** `ok`, `source_env: production`, real transactions in Dataverse. **If USAA fails Link or errors persistently:** that is a *finding, not a blocker* — record the exact `error_code`s, park USAA as manual-entry per Decisions Log §3, and write the verdict (Phase 7). The card item alone can still prove the pipeline.

### Phase 7 — 7-night soak + verdict

The timer is already live (13:00 UTC nightly). Each morning, check the latest `hf_auditlog` row (or App Insights) and fill the History table below. Any `sync_failed` night resets the consecutive counter (institution-outage retries are Sprint 3 hardening — for now a failed night is a failed night, honestly logged).

After 7 consecutive `ok` nights (or a definitive USAA failure): write `USAA-Plaid-Verdict.md` — institutions tested, error codes if any, item slots consumed (n/10), whether R1 is retired or USAA is parked manual-entry. Either outcome completes the sprint (kickoff exit criteria).

## Verification (sprint exit criteria)

- [ ] 7 consecutive nightly syncs from real accounts, rows landing with correct `hf_freshnessts` + `hf_sourceenv=production`
- [ ] Phase 4 forced-failure produced `sync_failed` (never silent empty); clean-empty control produced `clean_empty`
- [ ] USAA compatibility verdict documented (pass **or** parked-as-manual-entry)
- [ ] IaC + function code pushed to the private repo; Plaid production pricing captured in Decisions Log §4

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Function startup error `PLAID_ENV must be...` | App setting missing/typo'd | `az functionapp config appsettings set ... PLAID_ENV=sandbox` |
| 401/403 from Dataverse | App user missing role, or wrong `DATAVERSE_URL` | Re-check Phase 1.3 role assignment; URL must be the org URL, no trailing path |
| `INVALID_API_KEYS` from Plaid | Sandbox secret used against production or vice versa | Key Vault secret name must match `plaid-secret-<PLAID_ENV>` |
| Upsert 400 "key not found" | Alternate keys not activated | Phase 1.2 Keys step; wait for Active |
| Timer never fires | `TIMER_SCHEDULE` setting missing | It's set by Bicep; check app settings, restart app |
| `ITEM_LOGIN_REQUIRED` on real USAA after days of `ok` | USAA forced re-auth (this is R1 living its truth) | Re-run quickstart Link in update mode; token stays valid, no new Item consumed. Log the date — frequency of this IS the verdict data |
| Rows in Dataverse but wrong sign on amounts | Plaid outflow convention | Code negates (§6.2: negative = outflow); don't "fix" it twice |

## Rollback

- Azure: `az group delete -n rg-household-finance` removes everything billable. Key Vault soft-delete retains secrets 90 days (`az keyvault recover`).
- Plaid: `/item/remove` each Item — **Trial slots are NOT refunded**; only remove items you're abandoning permanently.
- Dataverse: delete the `HouseholdFinance` solution/environment. Export tables to CSV first (monthly export discipline, R12).
- License: cancel Power Apps Premium in M365 admin center (data becomes read-only when capacity lapses — export first).

## Escalation

| Situation | Contact | Method |
|---|---|---|
| Architecture change beyond CR-1/CR-2 (e.g., Dataverse licensing surprise) | Jim | Working session; bring the Volatile-Facts memo |
| Plaid errors not in this table / Trial plan issues | Plaid support | dashboard.plaid.com/support |
| USAA OAuth refusal | Nobody — it's the verdict | Park per Decisions Log §3, document, move on |
| Anything touching money movement | Stop. | Out of scope forever (non-negotiable) |

## History (7-night soak tracker)

| Date | Run by | Status | Notes |
|---|---|---|---|
| 2026-07-08 | timer | ok | night 1 — plaid.sync.ok 13:00:05 UTC, usaa-checking added 1/modified 0/removed 0, run_id f2310ac5 |
| 2026-07-09 | timer | ok | night 2 — plaid.sync.ok 13:00:11 UTC, usaa-checking added 3/modified 0/removed 0, run_id f91d6ae8 |
| 2026-07-10 | timer | ok | night 3 — plaid.sync.ok 13:00:11 UTC (freshness 13:00:07), usaa-checking added 4/modified 0/removed 0, run_id 0a8b8c5a (back-filled 2026-07-13 from audit log) |
| 2026-07-11 | timer | ok | night 4 — plaid.sync.ok 13:00:09 UTC (freshness 13:00:05), clean_empty, usaa-checking added 0/modified 0/removed 0, run_id 645edbeb (back-filled 2026-07-13 from audit log) |
| 2026-07-12 | timer | ok | night 5 — plaid.sync.ok 13:00:09 UTC, usaa-checking added 14/modified 1/removed 0, run_id 0e1b0dd9 (back-filled 2026-07-13 from audit log) |
| 2026-07-13 | timer | ok | night 6 — plaid.sync.ok 13:00:09 UTC (freshness 13:00:05), clean_empty, usaa-checking added 0/modified 0/removed 0, run_id 4e084162 |
| | timer | | night 7 |
