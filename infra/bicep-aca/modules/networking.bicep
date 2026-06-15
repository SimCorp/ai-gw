// infra/bicep/modules/networking.bicep
// Deployed scoped to rg-spoke-platformaitooling-dev-sdc-001

param vnetName string = 'vnet-spoke-platformaitooling-dev-sdc-001'
param peSubnetName string = 'snet-pe-aigw-dev'
param peSubnetPrefix string = '10.179.231.64/26'

resource vnet 'Microsoft.Network/virtualNetworks@2023-09-01' existing = {
  name: vnetName
}

resource peSubnet 'Microsoft.Network/virtualNetworks/subnets@2023-09-01' = {
  parent: vnet
  name: peSubnetName
  properties: {
    addressPrefix: peSubnetPrefix
    privateEndpointNetworkPolicies: 'Disabled'
    privateLinkServiceNetworkPolicies: 'Enabled'
  }
}

output peSubnetId string = peSubnet.id
