// infra/bicep/modules/keyVault.bicep

param name string
param location string
param peSubnetId string
param deployingPrincipalId string
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
param tags object = {}

// Key Vault Administrator — full data-plane access, required by Enforce-GR-KeyVault
var kvAdminRoleId = '00482a5a-887f-4fb3-b363-3b7fe8e74483'

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
    // AzureServices bypass lets ARM deployment write secrets even with public access disabled
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

resource privateEndpoint 'Microsoft.Network/privateEndpoints@2023-09-01' = {
  name: 'pe-kv-aigw-dev-sdc'
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

output kvName string = kv.name
output kvUri string = kv.properties.vaultUri
output kvId string = kv.id
