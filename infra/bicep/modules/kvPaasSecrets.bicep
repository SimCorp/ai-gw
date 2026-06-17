// infra/bicep/modules/kvPaasSecrets.bicep
// Resolves PaaS keys via listKeys() on existing resources.
// All URL construction is here — no secrets flow through main.bicep outputs.

param kvName string
param redisName string
param serviceBusName string
param postgresFqdn string
param postgresAdminLogin string = 'aigwadmin'
@secure()
param postgresAdminPassword string
@secure()
param appInsightsConn string

resource kv 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: kvName
}

resource redisRef 'Microsoft.Cache/redis@2023-08-01' existing = {
  name: redisName
}

resource sbRef 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' existing = {
  name: serviceBusName
}

resource sbAuthRule 'Microsoft.ServiceBus/namespaces/authorizationRules@2022-10-01-preview' existing = {
  parent: sbRef
  name: 'RootManageSharedAccessKey'
}

var redisKey = redisRef.listKeys('2023-08-01').primaryKey
// Python redis-py URL format used by services/cache
var redisUrl = 'rediss://:${redisKey}@${redisName}.redis.cache.windows.net:6380/0'

var sbConnStr = sbAuthRule.listKeys('2022-10-01-preview').primaryConnectionString

// SQLAlchemy+asyncpg format for most services; port omitted (default 5432)
var postgresUrl = 'postgresql+asyncpg://${postgresAdminLogin}:${postgresAdminPassword}@${postgresFqdn}/aigateway?sslmode=require'
// Raw asyncpg format for memory service (asyncpg.create_pool rejects the +asyncpg prefix)
var postgresUrlRaw = 'postgresql://${postgresAdminLogin}:${postgresAdminPassword}@${postgresFqdn}/aigateway?sslmode=require'
// Separate database for litellm spend logs. LiteLLM uses Prisma, which parses a
// plain libpq URL — NOT SQLAlchemy's 'postgresql+asyncpg://' scheme (Prisma's
// engine fails to start on the '+asyncpg' suffix). Keep this driver-less.
var postgresUrlLitellm = 'postgresql://${postgresAdminLogin}:${postgresAdminPassword}@${postgresFqdn}/litellm?sslmode=require'

resource secretPostgres 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'postgres-url'
  properties: { value: postgresUrl }
}

resource secretPostgresRaw 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'postgres-url-raw'
  properties: { value: postgresUrlRaw }
}

resource secretPostgresLitellm 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'postgres-url-litellm'
  properties: { value: postgresUrlLitellm }
}

resource secretRedis 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'redis-url'
  properties: { value: redisUrl }
}

resource secretSb 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'service-bus-conn'
  properties: { value: sbConnStr }
}

resource secretAppi 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'app-insights-conn'
  properties: { value: appInsightsConn }
}
