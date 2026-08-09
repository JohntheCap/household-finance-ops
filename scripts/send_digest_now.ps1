# Send the weekly digest NOW via the production path (Graph sendMail), identical to
# the Sunday email. Uses the manual_digest HTTP route with send=true. ASCII-only.
# Recipient is DIGEST_TO (john@johnthecap.com); Amanda is never CC'd unless DIGEST_CC
# is set as an app setting. Requires an active az login (John@johnthecap.com).

$ErrorActionPreference = "Stop"
$app = "func-hfin-hf7x2"

Write-Host "Locating function app '$app'..."
$rg = az functionapp list --query "[?name=='$app'].resourceGroup" -o tsv
if (-not $rg) { throw "Function app '$app' not found under the current az login." }
Write-Host "  resource group: $rg"

Write-Host "Retrieving function host key..."
$key = az functionapp keys list --name $app --resource-group $rg --query "functionKeys.default" -o tsv
if (-not $key) { throw "Could not retrieve a function key (check permissions)." }

$uri = "https://$app.azurewebsites.net/api/digest?send=true&code=$key"
Write-Host "Sending digest (production render + Graph sendMail)..."
$resp = Invoke-RestMethod -Uri $uri -Method Get -TimeoutSec 120

Write-Host ""
Write-Host "=== digest run result ==="
$resp | ConvertTo-Json -Depth 6
Write-Host ""
if ($resp.delivery -eq "sent") {
    Write-Host "DELIVERED to $($resp.to) (cc: $($resp.cc -join ', '))  ->  check your inbox."
} else {
    Write-Host "NOT SENT -- delivery=$($resp.delivery). See 'error' above."
}
