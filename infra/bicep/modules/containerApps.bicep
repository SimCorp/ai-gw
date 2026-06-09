// infra/bicep/modules/containerApps.bicep
// Defines all 12 Container Apps + 1 db-migrate Job.
// Apps use a shared UAMI with AcrPull on ACR and Key Vault Secrets User on KV.
// Images pulled from GHCR (private PAT auth) while ACR PE DNS is pending platform team.
// To switch back to ACR: remove ghcrPat/ghcrUsername params, restore acrLoginServer,
// replace ghcrBase references, and remove registries blocks from each app.

param env string
param acaEnvId string
param kvUri string
param kvName string
param acrName string
@secure()
param ghcrPat string
param ghcrUsername string
param imageTag string = 'latest'
param location string
param tags object = {}

// ── Role definition IDs ───────────────────────────────────────────────────────
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'
var kvSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'

// ── Existing resources (for role assignment scopes) ───────────────────────────
resource acrRef 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrName
}

resource kvRef 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: kvName
}

// ── Shared User-Assigned Managed Identity ─────────────────────────────────────
resource appIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-aca-apps-${env}-sdc'
  location: location
  tags: tags
}

resource acrPullAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acrRef.id, appIdentity.id, acrPullRoleId)
  scope: acrRef
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: appIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource kvSecretsUserAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kvRef.id, appIdentity.id, kvSecretsUserRoleId)
  scope: kvRef
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', kvSecretsUserRoleId)
    principalId: appIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

var uamiId = appIdentity.id

// ── GHCR registry pull credentials ───────────────────────────────────────────
var ghcrBase = 'ghcr.io/simcorp/ai-gw'
var ghcrSecret = [{ name: 'ghcr-pat', value: ghcrPat }]
var ghcrRegistries = [{ server: 'ghcr.io', username: ghcrUsername, passwordSecretRef: 'ghcr-pat' }]

// ── Inter-service base URLs (short ACA env DNS — works within same environment)
var authUrl = 'http://ca-auth-${env}-sdc'
var cacheUrl = 'http://ca-cache-${env}-sdc'
var litellmUrl = 'http://ca-litellm-${env}-sdc'
var observabilityUrl = 'http://ca-observability-${env}-sdc'
var adminUrl = 'http://ca-admin-${env}-sdc'
var agentRelayUrl = 'http://ca-agent-relay-${env}-sdc'
var librarianUrl = 'http://ca-librarian-${env}-sdc'
var leagueUrl = 'http://ca-league-${env}-sdc'

// ── Common container resources ─────────────────────────────────────────────────
var stdResources = {
  cpu: json('0.5')
  memory: '1Gi'
}
var lgResources = {
  cpu: json('1.0')
  memory: '2Gi'
}

// ── db-migrate Job ────────────────────────────────────────────────────────────
// Trigger manually once after first deployment: az containerapp job start ...
resource dbMigrateJob 'Microsoft.App/jobs@2024-03-01' = {
  name: 'job-db-migrate-${env}-sdc'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${uamiId}': {} }
  }
  properties: {
    environmentId: acaEnvId
    workloadProfileName: 'Consumption'
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 300
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: ghcrRegistries
      secrets: concat(ghcrSecret, [
        { name: 'postgres-url', keyVaultUrl: '${kvUri}secrets/postgres-url', identity: uamiId }
      ])
    }
    template: {
      containers: [
        {
          name: 'db-migrate'
          image: '${ghcrBase}/admin-api:${imageTag}'
          command: ['alembic', '-c', '/app/alembic.ini', 'upgrade', 'head']
          env: [
            { name: 'DATABASE_URL', secretRef: 'postgres-url' }
          ]
          resources: stdResources
        }
      ]
    }
  }
  dependsOn: [acrPullAssignment, kvSecretsUserAssignment]
}

// ── auth ──────────────────────────────────────────────────────────────────────
resource caAuth 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-auth-${env}-sdc'
  location: location
  tags: tags
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${uamiId}': {} } }
  properties: {
    managedEnvironmentId: acaEnvId
    workloadProfileName: 'Consumption'
    configuration: {
      ingress: { external: false, targetPort: 8001, transport: 'Http' }
      registries: ghcrRegistries
      secrets: concat(ghcrSecret, [
        { name: 'postgres-url', keyVaultUrl: '${kvUri}secrets/postgres-url', identity: uamiId }
        { name: 'redis-url', keyVaultUrl: '${kvUri}secrets/redis-url', identity: uamiId }
      ])
    }
    template: {
      containers: [
        {
          name: 'auth'
          image: '${ghcrBase}/auth:${imageTag}'
          env: [
            { name: 'DATABASE_URL', secretRef: 'postgres-url' }
            { name: 'REDIS_URL', secretRef: 'redis-url' }
            // Entra JWKS — intentionally hardcoded for SimCorp tenant (not a multi-cloud deployment)
            #disable-next-line no-hardcoded-env-urls
            { name: 'JWKS_URI', value: 'https://login.microsoftonline.com/aa81b43f-3969-4fd4-80c9-84c411508d82/discovery/v2.0/keys' }
            { name: 'ENTRA_TENANT_ID', value: 'aa81b43f-3969-4fd4-80c9-84c411508d82' }
            { name: 'ENTRA_CLIENT_ID', value: 'placeholder-pending-app-registration' }
            { name: 'ADMIN_URL', value: adminUrl }
            { name: 'ENVIRONMENT', value: env }
          ]
          resources: stdResources
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 2 }
    }
  }
  dependsOn: [acrPullAssignment, kvSecretsUserAssignment]
}

// ── cache ─────────────────────────────────────────────────────────────────────
resource caCache 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-cache-${env}-sdc'
  location: location
  tags: tags
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${uamiId}': {} } }
  properties: {
    managedEnvironmentId: acaEnvId
    workloadProfileName: 'Consumption'
    configuration: {
      ingress: { external: false, targetPort: 8002, transport: 'Http' }
      registries: ghcrRegistries
      secrets: concat(ghcrSecret, [
        { name: 'redis-url', keyVaultUrl: '${kvUri}secrets/redis-url', identity: uamiId }
        { name: 'litellm-master-key', keyVaultUrl: '${kvUri}secrets/litellm-master-key', identity: uamiId }
        { name: 'internal-api-key', keyVaultUrl: '${kvUri}secrets/internal-api-key', identity: uamiId }
      ])
    }
    template: {
      containers: [
        {
          name: 'cache'
          image: '${ghcrBase}/cache:${imageTag}'
          env: [
            { name: 'REDIS_URL', secretRef: 'redis-url' }
            { name: 'LITELLM_MASTER_KEY', secretRef: 'litellm-master-key' }
            { name: 'LITELLM_URL', value: litellmUrl }
            { name: 'AUTH_URL', value: authUrl }
            { name: 'OBSERVABILITY_URL', value: observabilityUrl }
            { name: 'INTERNAL_API_KEY', secretRef: 'internal-api-key' }
            { name: 'EMBEDDING_API_KEY', secretRef: 'litellm-master-key' }
            { name: 'EMBEDDING_BASE_URL', value: '${litellmUrl}/v1' }
            { name: 'EMBEDDING_MODEL', value: 'text-embedding-3-small' }
            { name: 'ENVIRONMENT', value: env }
          ]
          resources: stdResources
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 2 }
    }
  }
  dependsOn: [acrPullAssignment, kvSecretsUserAssignment]
}

// ── litellm ───────────────────────────────────────────────────────────────────
resource caLitellm 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-litellm-${env}-sdc'
  location: location
  tags: tags
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${uamiId}': {} } }
  properties: {
    managedEnvironmentId: acaEnvId
    workloadProfileName: 'Consumption'
    configuration: {
      ingress: { external: false, targetPort: 8003, transport: 'Http' }
      registries: ghcrRegistries
      secrets: concat(ghcrSecret, [
        { name: 'litellm-master-key', keyVaultUrl: '${kvUri}secrets/litellm-master-key', identity: uamiId }
        { name: 'postgres-url-litellm', keyVaultUrl: '${kvUri}secrets/postgres-url-litellm', identity: uamiId }
      ])
    }
    template: {
      containers: [
        {
          name: 'litellm'
          image: '${ghcrBase}/litellm:${imageTag}'
          env: [
            { name: 'LITELLM_MASTER_KEY', secretRef: 'litellm-master-key' }
            { name: 'DATABASE_URL', secretRef: 'postgres-url-litellm' }
            // Provider API keys: add to KV and reference here when available
            { name: 'ANTHROPIC_API_KEY', value: '' }
            { name: 'GEMINI_API_KEY', value: '' }
            { name: 'GITHUB_MODELS_API_KEY', value: '' }
            { name: 'AZURE_API_BASE', value: '' }
            { name: 'AZURE_API_KEY', value: '' }
            { name: 'AZURE_API_VERSION', value: '' }
          ]
          resources: lgResources
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 2 }
    }
  }
  dependsOn: [acrPullAssignment, kvSecretsUserAssignment]
}

// ── observability ─────────────────────────────────────────────────────────────
resource caObservability 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-observability-${env}-sdc'
  location: location
  tags: tags
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${uamiId}': {} } }
  properties: {
    managedEnvironmentId: acaEnvId
    workloadProfileName: 'Consumption'
    configuration: {
      ingress: { external: false, targetPort: 8004, transport: 'Http' }
      registries: ghcrRegistries
      secrets: concat(ghcrSecret, [
        { name: 'postgres-url', keyVaultUrl: '${kvUri}secrets/postgres-url', identity: uamiId }
        { name: 'redis-url', keyVaultUrl: '${kvUri}secrets/redis-url', identity: uamiId }
        { name: 'service-bus-conn', keyVaultUrl: '${kvUri}secrets/service-bus-conn', identity: uamiId }
        { name: 'app-insights-conn', keyVaultUrl: '${kvUri}secrets/app-insights-conn', identity: uamiId }
        { name: 'internal-api-key', keyVaultUrl: '${kvUri}secrets/internal-api-key', identity: uamiId }
      ])
    }
    template: {
      containers: [
        {
          name: 'observability'
          image: '${ghcrBase}/observability:${imageTag}'
          env: [
            { name: 'DATABASE_URL', secretRef: 'postgres-url' }
            { name: 'REDIS_URL', secretRef: 'redis-url' }
            { name: 'AZURE_SERVICE_BUS_CONNECTION_STRING', secretRef: 'service-bus-conn' }
            { name: 'APPINSIGHTS_CONNECTION_STRING', secretRef: 'app-insights-conn' }
            { name: 'INTERNAL_API_KEY', secretRef: 'internal-api-key' }
            { name: 'BUS_PROVIDER', value: 'servicebus' }
            { name: 'ENVIRONMENT', value: env }
          ]
          resources: stdResources
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 2 }
    }
  }
  dependsOn: [acrPullAssignment, kvSecretsUserAssignment]
}

// ── admin ─────────────────────────────────────────────────────────────────────
resource caAdmin 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-admin-${env}-sdc'
  location: location
  tags: tags
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${uamiId}': {} } }
  properties: {
    managedEnvironmentId: acaEnvId
    workloadProfileName: 'Consumption'
    configuration: {
      ingress: { external: false, targetPort: 8005, transport: 'Http' }
      registries: ghcrRegistries
      secrets: concat(ghcrSecret, [
        { name: 'postgres-url', keyVaultUrl: '${kvUri}secrets/postgres-url', identity: uamiId }
        { name: 'redis-url', keyVaultUrl: '${kvUri}secrets/redis-url', identity: uamiId }
        { name: 'admin-secret-key', keyVaultUrl: '${kvUri}secrets/admin-secret-key', identity: uamiId }
        { name: 'admin-internal-token', keyVaultUrl: '${kvUri}secrets/admin-internal-token', identity: uamiId }
        { name: 'litellm-master-key', keyVaultUrl: '${kvUri}secrets/litellm-master-key', identity: uamiId }
        { name: 'identity-key-secret', keyVaultUrl: '${kvUri}secrets/identity-key-secret', identity: uamiId }
        { name: 'librarian-service-token', keyVaultUrl: '${kvUri}secrets/librarian-service-token', identity: uamiId }
      ])
    }
    template: {
      containers: [
        {
          name: 'admin'
          image: '${ghcrBase}/admin-api:${imageTag}'
          env: [
            { name: 'DATABASE_URL', secretRef: 'postgres-url' }
            { name: 'REDIS_URL', secretRef: 'redis-url' }
            { name: 'SECRET_KEY', secretRef: 'admin-secret-key' }
            { name: 'ADMIN_TOKEN', secretRef: 'admin-internal-token' }
            { name: 'LITELLM_MASTER_KEY', secretRef: 'litellm-master-key' }
            { name: 'IDENTITY_KEY_SECRET', secretRef: 'identity-key-secret' }
            { name: 'LIBRARIAN_SERVICE_TOKEN', secretRef: 'librarian-service-token' }
            { name: 'DEV_BYPASS_AUTH', value: 'true' }
            { name: 'AUTH_URL', value: authUrl }
            { name: 'CACHE_URL', value: cacheUrl }
            { name: 'LITELLM_URL', value: litellmUrl }
            { name: 'OBSERVABILITY_URL', value: observabilityUrl }
            { name: 'LEAGUE_URL', value: leagueUrl }
            { name: 'LIBRARIAN_URL', value: librarianUrl }
            // Must be 'development' (not 'dev') to satisfy the DEV_BYPASS_AUTH startup guard
            { name: 'ENVIRONMENT', value: 'development' }
          ]
          resources: stdResources
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 2 }
    }
  }
  dependsOn: [acrPullAssignment, kvSecretsUserAssignment]
}

// ── identity ──────────────────────────────────────────────────────────────────
resource caIdentity 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-identity-${env}-sdc'
  location: location
  tags: tags
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${uamiId}': {} } }
  properties: {
    managedEnvironmentId: acaEnvId
    workloadProfileName: 'Consumption'
    configuration: {
      ingress: { external: false, targetPort: 8006, transport: 'Http' }
      registries: ghcrRegistries
      secrets: concat(ghcrSecret, [
        { name: 'postgres-url', keyVaultUrl: '${kvUri}secrets/postgres-url', identity: uamiId }
        { name: 'redis-url', keyVaultUrl: '${kvUri}secrets/redis-url', identity: uamiId }
        { name: 'identity-service-token', keyVaultUrl: '${kvUri}secrets/identity-service-token', identity: uamiId }
      ])
    }
    template: {
      containers: [
        {
          name: 'identity'
          image: '${ghcrBase}/identity:${imageTag}'
          env: [
            { name: 'DATABASE_URL', secretRef: 'postgres-url' }
            { name: 'REDIS_URL', secretRef: 'redis-url' }
            { name: 'IDENTITY_SERVICE_TOKEN', secretRef: 'identity-service-token' }
            { name: 'ADMIN_URL', value: adminUrl }
            { name: 'ENVIRONMENT', value: env }
          ]
          resources: stdResources
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 2 }
    }
  }
  dependsOn: [acrPullAssignment, kvSecretsUserAssignment]
}

// ── agent-relay ───────────────────────────────────────────────────────────────
resource caAgentRelay 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-agent-relay-${env}-sdc'
  location: location
  tags: tags
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${uamiId}': {} } }
  properties: {
    managedEnvironmentId: acaEnvId
    workloadProfileName: 'Consumption'
    configuration: {
      ingress: { external: false, targetPort: 8007, transport: 'Http' }
      registries: ghcrRegistries
      secrets: concat(ghcrSecret, [
        { name: 'redis-url', keyVaultUrl: '${kvUri}secrets/redis-url', identity: uamiId }
        { name: 'agent-relay-secret', keyVaultUrl: '${kvUri}secrets/agent-relay-secret', identity: uamiId }
      ])
    }
    template: {
      containers: [
        {
          name: 'agent-relay'
          image: '${ghcrBase}/agent-relay:${imageTag}'
          env: [
            { name: 'REDIS_URL', secretRef: 'redis-url' }
            { name: 'RELAY_SECRET', secretRef: 'agent-relay-secret' }
            { name: 'ENVIRONMENT', value: env }
          ]
          resources: stdResources
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 2 }
    }
  }
  dependsOn: [acrPullAssignment, kvSecretsUserAssignment]
}

// ── librarian ─────────────────────────────────────────────────────────────────
resource caLibrarian 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-librarian-${env}-sdc'
  location: location
  tags: tags
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${uamiId}': {} } }
  properties: {
    managedEnvironmentId: acaEnvId
    workloadProfileName: 'Consumption'
    configuration: {
      ingress: { external: false, targetPort: 8008, transport: 'Http' }
      registries: ghcrRegistries
      secrets: concat(ghcrSecret, [
        { name: 'postgres-url', keyVaultUrl: '${kvUri}secrets/postgres-url', identity: uamiId }
        { name: 'redis-url', keyVaultUrl: '${kvUri}secrets/redis-url', identity: uamiId }
        { name: 'litellm-master-key', keyVaultUrl: '${kvUri}secrets/litellm-master-key', identity: uamiId }
        { name: 'librarian-service-token', keyVaultUrl: '${kvUri}secrets/librarian-service-token', identity: uamiId }
      ])
    }
    template: {
      containers: [
        {
          name: 'librarian'
          image: '${ghcrBase}/librarian:${imageTag}'
          env: [
            { name: 'DATABASE_URL', secretRef: 'postgres-url' }
            { name: 'REDIS_URL', secretRef: 'redis-url' }
            { name: 'EMBEDDING_API_KEY', secretRef: 'litellm-master-key' }
            { name: 'LIBRARIAN_SERVICE_TOKEN', secretRef: 'librarian-service-token' }
            { name: 'AUTH_URL', value: authUrl }
            { name: 'CACHE_URL', value: cacheUrl }
            { name: 'EMBEDDING_BASE_URL', value: '${litellmUrl}/v1' }
            { name: 'EMBEDDING_MODEL', value: 'text-embedding-3-small' }
            { name: 'ENVIRONMENT', value: env }
          ]
          resources: stdResources
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 2 }
    }
  }
  dependsOn: [acrPullAssignment, kvSecretsUserAssignment]
}

// ── memory ────────────────────────────────────────────────────────────────────
resource caMemory 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-memory-${env}-sdc'
  location: location
  tags: tags
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${uamiId}': {} } }
  properties: {
    managedEnvironmentId: acaEnvId
    workloadProfileName: 'Consumption'
    configuration: {
      ingress: { external: false, targetPort: 8009, transport: 'Http' }
      registries: ghcrRegistries
      secrets: concat(ghcrSecret, [
        // memory uses raw asyncpg (no SQLAlchemy), requires postgresql:// scheme
        { name: 'postgres-url-raw', keyVaultUrl: '${kvUri}secrets/postgres-url-raw', identity: uamiId }
        { name: 'litellm-master-key', keyVaultUrl: '${kvUri}secrets/litellm-master-key', identity: uamiId }
      ])
    }
    template: {
      containers: [
        {
          name: 'memory'
          image: '${ghcrBase}/memory:${imageTag}'
          env: [
            { name: 'DATABASE_URL', secretRef: 'postgres-url-raw' }
            { name: 'AUTH_URL', value: authUrl }
            { name: 'ADMIN_URL', value: adminUrl }
            { name: 'EMBEDDING_API_KEY', secretRef: 'litellm-master-key' }
            { name: 'EMBEDDING_BASE_URL', value: '${litellmUrl}/v1' }
            { name: 'EMBEDDING_MODEL', value: 'text-embedding-3-small' }
            { name: 'ENVIRONMENT', value: env }
          ]
          resources: stdResources
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 2 }
    }
  }
  dependsOn: [acrPullAssignment, kvSecretsUserAssignment]
}

// ── league ────────────────────────────────────────────────────────────────────
resource caLeague 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-league-${env}-sdc'
  location: location
  tags: tags
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${uamiId}': {} } }
  properties: {
    managedEnvironmentId: acaEnvId
    workloadProfileName: 'Consumption'
    configuration: {
      ingress: { external: false, targetPort: 8010, transport: 'Http' }
      registries: ghcrRegistries
      secrets: concat(ghcrSecret, [
        { name: 'postgres-url', keyVaultUrl: '${kvUri}secrets/postgres-url', identity: uamiId }
        { name: 'redis-url', keyVaultUrl: '${kvUri}secrets/redis-url', identity: uamiId }
        { name: 'litellm-master-key', keyVaultUrl: '${kvUri}secrets/litellm-master-key', identity: uamiId }
        { name: 'admin-internal-token', keyVaultUrl: '${kvUri}secrets/admin-internal-token', identity: uamiId }
      ])
    }
    template: {
      containers: [
        {
          name: 'league'
          image: '${ghcrBase}/league:${imageTag}'
          env: [
            { name: 'DATABASE_URL', secretRef: 'postgres-url' }
            { name: 'REDIS_URL', secretRef: 'redis-url' }
            { name: 'LITELLM_MASTER_KEY', secretRef: 'litellm-master-key' }
            { name: 'ADMIN_TOKEN', secretRef: 'admin-internal-token' }
            { name: 'LITELLM_URL', value: litellmUrl }
            { name: 'ENVIRONMENT', value: env }
          ]
          resources: stdResources
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 2 }
    }
  }
  dependsOn: [acrPullAssignment, kvSecretsUserAssignment]
}

// ── scanner ───────────────────────────────────────────────────────────────────
resource caScanner 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-scanner-${env}-sdc'
  location: location
  tags: tags
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${uamiId}': {} } }
  properties: {
    managedEnvironmentId: acaEnvId
    workloadProfileName: 'Consumption'
    configuration: {
      ingress: { external: false, targetPort: 8011, transport: 'Http' }
      registries: ghcrRegistries
      secrets: concat(ghcrSecret, [
        { name: 'postgres-url', keyVaultUrl: '${kvUri}secrets/postgres-url', identity: uamiId }
        { name: 'redis-url', keyVaultUrl: '${kvUri}secrets/redis-url', identity: uamiId }
        { name: 'internal-api-key', keyVaultUrl: '${kvUri}secrets/internal-api-key', identity: uamiId }
        { name: 'scanner-worker-secret', keyVaultUrl: '${kvUri}secrets/scanner-worker-secret', identity: uamiId }
      ])
    }
    template: {
      containers: [
        {
          name: 'scanner'
          image: '${ghcrBase}/scanner:${imageTag}'
          env: [
            { name: 'DATABASE_URL', secretRef: 'postgres-url' }
            { name: 'REDIS_URL', secretRef: 'redis-url' }
            { name: 'AUTH_URL', value: authUrl }
            { name: 'INTERNAL_API_KEY', secretRef: 'internal-api-key' }
            { name: 'SCANNER_WORKER_SECRET', secretRef: 'scanner-worker-secret' }
            { name: 'ENVIRONMENT', value: env }
          ]
          resources: stdResources
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 2 }
    }
  }
  dependsOn: [acrPullAssignment, kvSecretsUserAssignment]
}

// ── workflow-worker ───────────────────────────────────────────────────────────
// Background worker — no ingress.
resource caWorkflowWorker 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-workflow-worker-${env}-sdc'
  location: location
  tags: tags
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${uamiId}': {} } }
  properties: {
    managedEnvironmentId: acaEnvId
    workloadProfileName: 'Consumption'
    configuration: {
      registries: ghcrRegistries
      secrets: concat(ghcrSecret, [
        { name: 'postgres-url', keyVaultUrl: '${kvUri}secrets/postgres-url', identity: uamiId }
        { name: 'redis-url', keyVaultUrl: '${kvUri}secrets/redis-url', identity: uamiId }
        { name: 'agent-relay-secret', keyVaultUrl: '${kvUri}secrets/agent-relay-secret', identity: uamiId }
        { name: 'admin-internal-token', keyVaultUrl: '${kvUri}secrets/admin-internal-token', identity: uamiId }
      ])
    }
    template: {
      containers: [
        {
          name: 'workflow-worker'
          image: '${ghcrBase}/workflow-worker:${imageTag}'
          env: [
            { name: 'DATABASE_URL', secretRef: 'postgres-url' }
            { name: 'REDIS_URL', secretRef: 'redis-url' }
            { name: 'AGENT_RELAY_SECRET', secretRef: 'agent-relay-secret' }
            { name: 'ADMIN_INTERNAL_TOKEN', secretRef: 'admin-internal-token' }
            { name: 'AGENT_RELAY_URL', value: agentRelayUrl }
            { name: 'ADMIN_URL', value: adminUrl }
            { name: 'ENVIRONMENT', value: env }
          ]
          resources: stdResources
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
  dependsOn: [acrPullAssignment, kvSecretsUserAssignment]
}
