// infra/bicep/modules/serviceBus.bicep

param name string
param location string
param peSubnetId string
param tags object = {}

resource sbNamespace 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: 'Standard'
    tier: 'Standard'
  }
  properties: {}
}

resource observabilityQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: sbNamespace
  name: 'observability-events'
  properties: {
    maxSizeInMegabytes: 1024
    lockDuration: 'PT1M'
    maxDeliveryCount: 10
    requiresSession: false
  }
}

resource privateEndpoint 'Microsoft.Network/privateEndpoints@2023-09-01' = {
  name: 'pe-sb-aigw-dev-sdc'
  location: location
  properties: {
    subnet: {
      id: peSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: 'pe-sb-conn'
        properties: {
          privateLinkServiceId: sbNamespace.id
          groupIds: ['namespace']
        }
      }
    ]
  }
}

output sbId string = sbNamespace.id
output sbName string = sbNamespace.name
