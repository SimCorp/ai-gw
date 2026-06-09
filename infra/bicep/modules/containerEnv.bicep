// infra/bicep/modules/containerEnv.bicep

param name string
param location string
param infrastructureSubnetId string
param lawCustomerId string
@secure()
param lawSharedKey string
@secure()
param tlsCertBase64 string
@secure()
param tlsCertPassword string
param tags object = {}

resource acaEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    vnetConfiguration: {
      internal: true
      infrastructureSubnetId: infrastructureSubnetId
    }
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: lawCustomerId
        sharedKey: lawSharedKey
      }
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}

resource tlsCert 'Microsoft.App/managedEnvironments/certificates@2024-03-01' = {
  parent: acaEnv
  name: 'tls-wildcard-lab'
  location: location
  properties: {
    value: any(tlsCertBase64)
    password: tlsCertPassword
  }
}

output acaEnvId string = acaEnv.id
output acaEnvName string = acaEnv.name
output acaStaticIp string = acaEnv.properties.staticIp
output acaDefaultDomain string = acaEnv.properties.defaultDomain
output tlsCertId string = tlsCert.id
