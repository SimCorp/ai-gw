// infra/bicep/modules/acr.bicep
// ACR names must be globally unique and alphanumeric only (no dashes)

param name string
param location string
param tags object = {}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: 'Standard'
  }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
    zoneRedundancy: 'Disabled'
  }
}

output acrLoginServer string = acr.properties.loginServer
output acrId string = acr.id
