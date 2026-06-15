// infra/bicep/modules/monitoring.bicep

param lawName string
param appiName string
param location string
param tags object = {}

resource law 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: lawName
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appiName
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: law.id
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

output appiConnectionString string = appInsights.properties.ConnectionString
output appiInstrumentationKey string = appInsights.properties.InstrumentationKey
output lawId string = law.id
output lawCustomerId string = law.properties.customerId
@secure()
output lawSharedKey string = law.listKeys('2023-09-01').primarySharedKey
