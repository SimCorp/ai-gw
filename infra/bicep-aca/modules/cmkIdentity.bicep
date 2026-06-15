// infra/bicep/modules/cmkIdentity.bicep
// User-assigned managed identity used for Service Bus CMK encryption.

param name string
param location string
param tags object = {}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: name
  location: location
  tags: tags
}

output identityId string = identity.id
output principalId string = identity.properties.principalId
