// infra/bicep/modules/networking.bicep
// Deployed scoped to rg-spoke-platformaitooling-dev-sdc-001

param vnetName string
param env string
param peSubnetPrefix string  // required — CIDR space is LZ-specific, no safe default
var peSubnetName = 'snet-pe-aigw-${env}'

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
