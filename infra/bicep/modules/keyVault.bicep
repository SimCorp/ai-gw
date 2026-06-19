// infra/bicep/modules/keyVault.bicep

param name string
param location string
param peSubnetId string
param env string
param deployingPrincipalId string
param sbEncryptionPrincipalId string
@secure()
param agentRelaySecret string
@secure()
param adminInternalToken string
@secure()
param identityKeySecret string
@secure()
param identityServiceToken string
@secure()
param librarianServiceToken string
@secure()
param litellmMasterKey string
@secure()
param adminSecretKey string
@secure()
param internalApiKey string
@secure()
param scannerWorkerSecret string
param tags object = {}

// Key Vault Administrator — full data-plane access, required by Enforce-GR-KeyVault
var kvAdminRoleId = '00482a5a-887f-4fb3-b363-3b7fe8e74483'
// Key Vault Crypto Service Encryption User — allows managed identity to wrap/unwrap CMK
var kvCryptoUserRoleId = 'e147488a-f6f5-4113-8e2d-b22465e65bf6'

resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    enablePurgeProtection: true
    publicNetworkAccess: 'Disabled'
    // AzureServices bypass lets ARM and Service Bus CMK access KV with public access disabled
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Deny'
    }
  }
}

// Grant the deploying principal full data-plane access via RBAC
resource kvAdminRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, deployingPrincipalId, kvAdminRoleId)
  scope: kv
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', kvAdminRoleId)
    principalId: deployingPrincipalId
    principalType: 'User'
  }
}

// Encryption key for Service Bus CMK
resource sbCmkKey 'Microsoft.KeyVault/vaults/keys@2023-07-01' = {
  parent: kv
  name: 'sb-cmk-key'
  dependsOn: [kvAdminRole]
  properties: {
    kty: 'RSA'
    keySize: 4096
    keyOps: ['encrypt', 'decrypt', 'wrapKey', 'unwrapKey', 'sign', 'verify']
  }
}

// Grant the Service Bus CMK managed identity access to wrap/unwrap the encryption key
resource sbCryptoRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, sbEncryptionPrincipalId, kvCryptoUserRoleId)
  scope: kv
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', kvCryptoUserRoleId)
    principalId: sbEncryptionPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource privateEndpoint 'Microsoft.Network/privateEndpoints@2023-09-01' = {
  name: 'pe-kv-aigw-${env}-sdc'
  location: location
  properties: {
    subnet: {
      id: peSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: 'pe-kv-conn'
        properties: {
          privateLinkServiceId: kv.id
          groupIds: ['vault']
        }
      }
    ]
  }
}

resource secretAgentRelay 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'agent-relay-secret'
  dependsOn: [kvAdminRole]
  properties: { value: agentRelaySecret }
}

resource secretAdminToken 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'admin-internal-token'
  dependsOn: [kvAdminRole]
  properties: { value: adminInternalToken }
}

resource secretIdentityKey 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'identity-key-secret'
  dependsOn: [kvAdminRole]
  properties: { value: identityKeySecret }
}

resource secretIdentityToken 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'identity-service-token'
  dependsOn: [kvAdminRole]
  properties: { value: identityServiceToken }
}

resource secretLibrarianToken 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'librarian-service-token'
  dependsOn: [kvAdminRole]
  properties: { value: librarianServiceToken }
}

resource secretLitellmMasterKey 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'litellm-master-key'
  dependsOn: [kvAdminRole]
  properties: { value: litellmMasterKey }
}

resource secretAdminSecretKey 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'admin-secret-key'
  dependsOn: [kvAdminRole]
  properties: { value: adminSecretKey }
}

resource secretInternalApiKey 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'internal-api-key'
  dependsOn: [kvAdminRole]
  properties: { value: internalApiKey }
}

resource secretScannerWorkerSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'scanner-worker-secret'
  dependsOn: [kvAdminRole]
  properties: { value: scannerWorkerSecret }
}

output kvName string = kv.name
output kvUri string = kv.properties.vaultUri
output kvId string = kv.id
output sbKeyName string = sbCmkKey.name
