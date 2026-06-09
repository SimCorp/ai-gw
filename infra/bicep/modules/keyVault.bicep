// infra/bicep/modules/keyVault.bicep

param name string
param location string
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
    enableRbacAuthorization: false
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    enablePurgeProtection: false
    accessPolicies: [
      {
        tenantId: subscription().tenantId
        objectId: deployingPrincipalId
        permissions: {
          secrets: ['get', 'list', 'set', 'delete']
          certificates: ['get', 'list', 'import', 'delete']
        }
      }
    ]
  }
}

resource secretAgentRelay 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'agent-relay-secret'
  properties: { value: agentRelaySecret }
}

resource secretAdminToken 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'admin-internal-token'
  properties: { value: adminInternalToken }
}

resource secretIdentityKey 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'identity-key-secret'
  properties: { value: identityKeySecret }
}

resource secretIdentityToken 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'identity-service-token'
  properties: { value: identityServiceToken }
}

resource secretLibrarianToken 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'librarian-service-token'
  properties: { value: librarianServiceToken }
}

output kvName string = kv.name
output kvUri string = kv.properties.vaultUri
output kvId string = kv.id
