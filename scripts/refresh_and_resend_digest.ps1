# Re-run bill matching (regenerate hf_billinstance rows from the now-updated hf_bill
# registry), then resend the weekly digest via the production Graph path. ASCII-only.
#
# Why: editing hf_bill (Comcast -> $70; Primo/LMNT/Apple -> cancelled) does not touch
# hf_billinstance. The digest's "Coming up" / "Needs attention" sections read the
# instances, so they stay stale until match_bills re-runs. Matching reuses existing
# transactions (no Plaid sync, no cost) and:
#   - rebuilds the Comcast instance at the new $70 expected amount,
#   - supersedes the orphaned Primo / LMNT / Apple installment instances (cancelled
#     bills are no longer generated), removing them from the digest.
# Budget-review month is NOT affected here (it needs the July Apple Card CSV imported).
#
# Requires an active az login (John@johnthecap.com).

$ErrorActionPreference = "Stop"
$app = "func-hfin-hf7x2"

Write-Host "Locating function app '$app'..."
$rg = az functionapp list --query "[?name=='$app'].resourceGroup" -o tsv
if (-not $rg) { throw "Function app '$app' not found under the current az login." }
$key = az functionapp keys list --name $app --resource-group $rg --query "functionKeys.default" -o tsv
if (-not $key) { throw "Could not retrieve a function key (check permissions)." }

# 1) Re-run matching (no sync). Regenerates instances from live hf_bill.
Write-Host "`nStep 1/2: re-running bill matching..."
$match = Invoke-RestMethod -Uri "https://$app.azurewebsites.net/api/match?code=$key" -Method Get -TimeoutSec 120
Write-Host "  status:      $($match.status)"
Write-Host "  bills matched: $($match.bills_matched)   superseded: $($match.superseded)"
Write-Host "  by_status:   $($match.by_status | ConvertTo-Json -Compress)"
if ($match.transitions) {
    Write-Host "  transitions:"
    foreach ($t in $match.transitions) { Write-Host "    - $($t.bill): $($t.from) -> $($t.to)" }
}

# 2) Resend the digest (production render + Graph sendMail, John only).
Write-Host "`nStep 2/2: resending the digest..."
$resp = Invoke-RestMethod -Uri "https://$app.azurewebsites.net/api/digest?send=true&code=$key" -Method Get -TimeoutSec 120
Write-Host "  envelope: $($resp.envelope | ConvertTo-Json -Compress)"
Write-Host "  upcoming: $($resp.upcoming)   missed: $($resp.missed)   pending_statement: $($resp.pending_statement)"
Write-Host "  stale:    $($resp.stale)"
if ($resp.delivery -eq "sent") {
    Write-Host "`nDELIVERED to $($resp.to) (cc: $($resp.cc -join ', '))  ->  check your inbox."
} else {
    Write-Host "`nNOT SENT -- delivery=$($resp.delivery). error: $($resp.error)"
}
