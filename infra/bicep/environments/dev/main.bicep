targetScope = 'subscription'

param location string = 'swedencentral'
param env string = 'dev'
param vnetResourceGroup string
param vnetName string
param acaInfraSubnetId string
param deployingPrincipalId string

@secure()
param postgresAdminPassword string
@secure()
param tlsCertBase64 string
@secure()
param tlsCertPassword string

var rgName = 'rg-aigw-${env}-sdc'
var kvName = 'kv-aigw-${env}-sdc'
var tags = { environment: env, workload: 'aigw', managedBy: 'bicep' }

// Inter-service secrets — deterministic, derived from subscription+env
var agentRelaySecret = uniqueString(subscription().id, env, 'agent-relay')
var adminInternalToken = uniqueString(subscription().id, env, 'admin-token')
var identityKeySecret = uniqueString(subscription().id, env, 'identity-key')
var identityServiceToken = uniqueString(subscription().id, env, 'identity-svc')
var librarianServiceToken = uniqueString(subscription().id, env, 'librarian-svc')

// ── Resource group ────────────────────────────────────────────────────────────
resource rg 'Microsoft.Resources/resourceGroups@2023-07-01' = {
  name: rgName
  location: location
  tags: tags
}

// ── PE subnet in LZ VNet (cross-RG) ──────────────────────────────────────────
module networking '../../modules/networking.bicep' = {
  name: 'networking'
  scope: resourceGroup(vnetResourceGroup)
  params: {
    vnetName: vnetName
  }
}

// ── Key Vault (inter-service secrets) ─────────────────────────────────────────
module keyVault '../../modules/keyVault.bicep' = {
  name: 'keyVault'
  scope: rg
  params: {
    name: kvName
    location: location
    tags: tags
    peSubnetId: networking.outputs.peSubnetId
    deployingPrincipalId: deployingPrincipalId
    agentRelaySecret: agentRelaySecret
    adminInternalToken: adminInternalToken
    identityKeySecret: identityKeySecret
    identityServiceToken: identityServiceToken
    librarianServiceToken: librarianServiceToken
  }
}

// ── PostgreSQL ─────────────────────────────────────────────────────────────────
module postgres '../../modules/postgres.bicep' = {
  name: 'postgres'
  scope: rg
  params: {
    name: 'psql-aigw-${env}-sdc'
    location: location
    tags: tags
    peSubnetId: networking.outputs.peSubnetId
    administratorPassword: postgresAdminPassword
  }
}

// ── Redis ─────────────────────────────────────────────────────────────────────
module redis '../../modules/redis.bicep' = {
  name: 'redis'
  scope: rg
  params: {
    name: 'redis-aigw-${env}-sdc'
    location: location
    tags: tags
    peSubnetId: networking.outputs.peSubnetId
  }
}

// ── ACR ───────────────────────────────────────────────────────────────────────
module acr '../../modules/acr.bicep' = {
  name: 'acr'
  scope: rg
  params: {
    name: 'acraigw${env}sdc'
    location: location
    tags: tags
  }
}

// ── Service Bus ───────────────────────────────────────────────────────────────
module serviceBus '../../modules/serviceBus.bicep' = {
  name: 'serviceBus'
  scope: rg
  params: {
    name: 'sb-aigw-${env}-sdc'
    location: location
    tags: tags
    peSubnetId: networking.outputs.peSubnetId
  }
}

// ── Monitoring ────────────────────────────────────────────────────────────────
module monitoring '../../modules/monitoring.bicep' = {
  name: 'monitoring'
  scope: rg
  params: {
    lawName: 'law-aigw-${env}-sdc'
    appiName: 'appi-aigw-${env}-sdc'
    location: location
    tags: tags
  }
}

// ── ACA Environment ───────────────────────────────────────────────────────────
module containerEnv '../../modules/containerEnv.bicep' = {
  name: 'containerEnv'
  scope: rg
  params: {
    name: 'cae-aigw-${env}-sdc'
    location: location
    tags: tags
    infrastructureSubnetId: acaInfraSubnetId
    lawCustomerId: monitoring.outputs.lawCustomerId
    lawSharedKey: monitoring.outputs.lawSharedKey
    tlsCertBase64: tlsCertBase64
    tlsCertPassword: tlsCertPassword
  }
}

// ── Write PaaS connection strings to Key Vault ────────────────────────────────
// listKeys() and URL construction are done inside kvPaasSecrets.bicep
// so secrets never flow through main.bicep variables or ARM deployment outputs.
module kvPaasSecrets '../../modules/kvPaasSecrets.bicep' = {
  name: 'kvPaasSecrets'
  scope: rg
  dependsOn: [keyVault, redis, serviceBus]
  params: {
    kvName: kvName
    redisName: 'redis-aigw-${env}-sdc'
    serviceBusName: 'sb-aigw-${env}-sdc'
    postgresFqdn: postgres.outputs.postgresFqdn
    postgresAdminPassword: postgresAdminPassword
    appInsightsConn: monitoring.outputs.appiConnectionString
  }
}

// ── Outputs (non-secret) ──────────────────────────────────────────────────────
output acaStaticIp string = containerEnv.outputs.acaStaticIp
output acaDefaultDomain string = containerEnv.outputs.acaDefaultDomain
output acrLoginServer string = acr.outputs.acrLoginServer
output tlsCertId string = containerEnv.outputs.tlsCertId
