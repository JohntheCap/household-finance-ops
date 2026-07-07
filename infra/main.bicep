// Household Finance Ops Agent — Sprint 2 Azure foundation
// Deploy:  az deployment group create -g rg-household-finance -f main.bicep -p suffix=<5char> adminObjectId=<your-entra-object-id>
// A9: PLAID_ENV is a deploy-time parameter; the function asserts it at startup.

@minLength(3)
@maxLength(8)
param suffix string
param adminObjectId string
param location string = resourceGroup().location
@allowed(['sandbox', 'production'])
param plaidEnv string = 'sandbox'
param plaidClientId string = ''
param dataverseUrl string = ''
param dataversePrefix string = 'hf'

var kvName = 'kv-hfin-${suffix}'
var stName = 'sthfin${suffix}'
var funcName = 'func-hfin-${suffix}'
var lawName = 'law-hfin-${suffix}'

resource law 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: lawName
  location: location
  properties: { retentionInDays: 90, sku: { name: 'PerGB2018' } }
}

resource appi 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-hfin-${suffix}'
  location: location
  kind: 'web'
  properties: { Application_Type: 'web', WorkspaceResourceId: law.id }
}

resource st 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: stName
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: { minimumTlsVersion: 'TLS1_2', allowBlobPublicAccess: false }
}

resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: kvName
  location: location
  properties: {
    tenantId: tenant().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
  }
}

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: 'plan-hfin-${suffix}'
  location: location
  sku: { name: 'Y1', tier: 'Dynamic' }
  kind: 'linux'
  properties: { reserved: true }
}

resource func 'Microsoft.Web/sites@2023-12-01' = {
  name: funcName
  location: location
  kind: 'functionapp,linux'
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'Python|3.11'
      ftpsState: 'Disabled'
      appSettings: [
        { name: 'AzureWebJobsStorage', value: 'DefaultEndpointsProtocol=https;AccountName=${st.name};EndpointSuffix=${environment().suffixes.storage};AccountKey=${st.listKeys().keys[0].value}' }
        { name: 'FUNCTIONS_EXTENSION_VERSION', value: '~4' }
        { name: 'FUNCTIONS_WORKER_RUNTIME', value: 'python' }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appi.properties.ConnectionString }
        { name: 'PLAID_ENV', value: plaidEnv }
        { name: 'PLAID_CLIENT_ID', value: plaidClientId }
        { name: 'KEY_VAULT_URI', value: kv.properties.vaultUri }
        { name: 'DATAVERSE_URL', value: dataverseUrl }
        { name: 'DATAVERSE_PREFIX', value: dataversePrefix }
        { name: 'TIMER_SCHEDULE', value: '0 0 13 * * *' } // 13:00 UTC = 6:00 AM Pacific (DST)
      ]
    }
  }
}

// Key Vault Secrets User -> function managed identity
resource kvSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, func.id, 'kv-secrets-user')
  scope: kv
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
    principalId: func.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Key Vault Secrets Officer -> John (to set secrets from CLI)
resource kvSecretsOfficer 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, adminObjectId, 'kv-secrets-officer')
  scope: kv
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7')
    principalId: adminObjectId
    principalType: 'User'
  }
}

output functionAppName string = func.name
output keyVaultName string = kv.name
output functionPrincipalId string = func.identity.principalId
