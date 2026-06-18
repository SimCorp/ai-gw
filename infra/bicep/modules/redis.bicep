// infra/bicep/modules/redis.bicep

param name string
param location string
param peSubnetId string
param env string
param tags object = {}

resource redisCache 'Microsoft.Cache/redis@2023-08-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'Premium'
      family: 'P'
      capacity: 1
    }
    enableNonSslPort: false
    minimumTlsVersion: '1.2'
    publicNetworkAccess: 'Disabled'
    redisConfiguration: {
      'rdb-backup-enabled': 'false'
      'maxmemory-policy': 'allkeys-lru'
    }
  }
}

resource privateEndpoint 'Microsoft.Network/privateEndpoints@2023-09-01' = {
  name: 'pe-redis-aigw-${env}-sdc'
  location: location
  properties: {
    subnet: {
      id: peSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: 'pe-redis-conn'
        properties: {
          privateLinkServiceId: redisCache.id
          groupIds: ['redisCache']
        }
      }
    ]
  }
}

output redisFqdn string = redisCache.properties.hostName
output redisId string = redisCache.id
output redisName string = redisCache.name
