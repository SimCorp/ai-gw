// infra/bicep/modules/storage.bicep
// Foundation storage for the ACA-Jobs spawn runtime (Component 2):
// an Azure Files share mounted into agent-runner / scanner-runner job executions
// as the I/O exchange dir (worker writes inputs.json, reads outputs.json).
// Deterministic naming so containerApps.bicep can reference it as `existing`
// without a shared param: account `staigwruns${env}sdc`, share `aigw-runs`.

param env string
param location string
param tags object = {}

resource runsStorage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: 'staigwruns${env}sdc'
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
}

resource fileService 'Microsoft.Storage/storageAccounts/fileServices@2023-01-01' = {
  parent: runsStorage
  name: 'default'
}

resource runsShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-01-01' = {
  parent: fileService
  name: 'aigw-runs'
  properties: {
    shareQuota: 100
  }
}

output storageAccountName string = runsStorage.name
output storageAccountId string = runsStorage.id
