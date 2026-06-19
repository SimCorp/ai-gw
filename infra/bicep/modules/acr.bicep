// infra/bicep/modules/acr.bicep
// ACR names must be globally unique and alphanumeric only (no dashes)

param name string
param location string
param peSubnetId string
param env string
param tags object = {}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: 'Premium'
  }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
    zoneRedundancy: 'Disabled'
  }
}

resource acrPe 'Microsoft.Network/privateEndpoints@2023-09-01' = {
  name: 'pe-acr-aigw-${env}-sdc'
  location: location
  properties: {
    subnet: {
      id: peSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: 'pe-acr-conn'
        properties: {
          privateLinkServiceId: acr.id
          groupIds: ['registry']
        }
      }
    ]
  }
}

// DNS zones for privatelink.azurecr.io and swedencentral.data.privatelink.azurecr.io
// are managed centrally by the platform team (SimCorp policy blocks creating them here).
// Platform team must:
//   1. Register A record in privatelink.azurecr.io for acraigwdevsdc → PE private IP
//   2. Register A record in swedencentral.data.privatelink.azurecr.io for acraigwdevsdc → PE data IP
//   3. Ensure both zones are linked to vnet-spoke-platformaitooling-dev-sdc-001

output acrLoginServer string = acr.properties.loginServer
output acrId string = acr.id
output acrPeId string = acrPe.id
