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
// Storage File Data SMB Share Contributor — read/write the aigw-runs file share.
var storageFileShareContributorRoleId = '0c867c2a-1d8c-454a-a3db-ab2ea1bdc8bb'
// Contributor — granted scoped to the two runner Jobs (NOT the resource group) so
// the worker/scanner MI can start ACA Job executions (Microsoft.App/jobs/start/action).
// There is no narrow built-in "jobs operator" role; a custom role limited to
// jobs/start/action + read would tighten this further. Tracked as a follow-up.
var contributorRoleId = 'b24988ac-6180-42a0-ab88-20f7382dd24c'

// ── Existing resources (for role assignment scopes) ───────────────────────────
resource acrRef 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrName
}

resource kvRef 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: kvName
}

// Storage account is provisioned as a foundation resource (modules/storage.bicep,
// wired in environments/dev/main.bicep). Deterministic name lets us bind here
// without a shared param. Referenced existing for its access key + id.
resource runsStorage 'Microsoft.Storage/storageAccounts@2023-01-01' existing = {
  name: 'staigwruns${env}sdc'
}

// ACA managed environment — referenced existing so the env-storage mount can use
// it as parent. Name matches containerEnv.bicep (cae-aigw-${env}-sdc).
resource acaEnv 'Microsoft.App/managedEnvironments@2024-03-01' existing = {
  name: 'cae-aigw-${env}-sdc'
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

// Dedicated ZERO-PRIVILEGE identity for spawned job executions (agent images from
// the agents table + third-party scanner images) and the jumpbox. It has NO Key
// Vault / RG role assignments, so a compromised agent/scanner image cannot read
// secrets or act on Azure. The aigw-runs share is mounted via the env storage
// (storage account key), not this identity, so job containers need no Azure role.
resource jobsIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-aca-jobs-${env}-sdc'
  location: location
  tags: tags
}
var jobsUamiId = jobsIdentity.id

// ── Spawn-runtime role assignments (Component 2) ──────────────────────────────
// (i) SMB Share Contributor on the runs storage account — worker/scanner MI
//     reads/writes the aigw-runs file share mounted at /run in job executions.
resource storageShareContributorAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(runsStorage.id, appIdentity.id, storageFileShareContributorRoleId)
  scope: runsStorage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageFileShareContributorRoleId)
    principalId: appIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// (ii) Contributor scoped to the two runner Jobs ONLY — lets the worker/scanner
//      app MI start + read those job executions without resource-group-wide power.
//      (A custom role limited to Microsoft.App/jobs/start/action + read could
//      narrow it further; job-scoped Contributor already bounds the blast radius.)
resource agentJobStartAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(agentRunnerJob.id, appIdentity.id, contributorRoleId)
  scope: agentRunnerJob
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', contributorRoleId)
    principalId: appIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}
resource scannerJobStartAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(scannerRunnerJob.id, appIdentity.id, contributorRoleId)
  scope: scannerRunnerJob
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', contributorRoleId)
    principalId: appIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ── ACA env storage mount — binds the aigw-runs Azure Files share into the env
//    so Jobs can declare an AzureFile volume referencing it (storageName: aigw-runs).
resource runsEnvStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: acaEnv
  name: 'aigw-runs'
  properties: {
    azureFile: {
      accountName: runsStorage.name
      accountKey: runsStorage.listKeys().keys[0].value
      shareName: 'aigw-runs'
      accessMode: 'ReadWrite'
    }
  }
}

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

// ── agent-runner Job (Component 2) ────────────────────────────────────────────
// Pre-declared manual job. workflow-worker starts one execution per agent run via
// the management API, supplying a per-execution template override (real image +
// run env). The declared image here is a PLACEHOLDER. The aigw-runs share is
// mounted at /run for inputs.json / outputs.json exchange.
resource agentRunnerJob 'Microsoft.App/jobs@2024-03-01' = {
  name: 'job-agent-runner-${env}-sdc'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${jobsUamiId}': {} }
  }
  properties: {
    environmentId: acaEnvId
    workloadProfileName: 'Consumption'
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 3600
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: ghcrRegistries
      secrets: ghcrSecret
    }
    template: {
      containers: [
        {
          name: 'agent-runner'
          // Placeholder — overridden per execution by the worker.
          image: '${ghcrBase}/workflow-worker:${imageTag}'
          resources: stdResources
          volumeMounts: [
            { volumeName: 'aigw-runs', mountPath: '/run' }
          ]
        }
      ]
      volumes: [
        { name: 'aigw-runs', storageType: 'AzureFile', storageName: 'aigw-runs' }
      ]
    }
  }
  dependsOn: [acrPullAssignment, kvSecretsUserAssignment, runsEnvStorage]
}

// ── scanner-runner Job (Component 2) ──────────────────────────────────────────
// Same mechanism for the scanner service (nmap/nuclei/ZAP/garak). Declared image
// is a PLACEHOLDER; the scanner overrides image + env per execution.
resource scannerRunnerJob 'Microsoft.App/jobs@2024-03-01' = {
  name: 'job-scanner-runner-${env}-sdc'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${jobsUamiId}': {} }
  }
  properties: {
    environmentId: acaEnvId
    workloadProfileName: 'Consumption'
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 3600
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: ghcrRegistries
      secrets: ghcrSecret
    }
    template: {
      containers: [
        {
          name: 'scanner-runner'
          // Placeholder — overridden per execution by the scanner.
          image: '${ghcrBase}/scanner:${imageTag}'
          resources: stdResources
          volumeMounts: [
            { volumeName: 'aigw-runs', mountPath: '/run' }
          ]
        }
      ]
      volumes: [
        { name: 'aigw-runs', storageType: 'AzureFile', storageName: 'aigw-runs' }
      ]
    }
  }
  dependsOn: [acrPullAssignment, kvSecretsUserAssignment, runsEnvStorage]
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
        // TODO(Workstream H.2): once the Entra app-registration creates the
        // 'oidc-client-secret' Key Vault secret, add it here and switch the
        // OIDC_CLIENT_SECRET env below from '' to secretRef: 'oidc-client-secret'.
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
            // Empty until Entra app-registration (H.2) — admin-portal OIDC login is
            // disabled until then; switch to secretRef: 'oidc-client-secret' once it exists.
            { name: 'OIDC_CLIENT_SECRET', value: '' }
            // Entra ID OIDC issuer for SimCorp tenant (admin-portal SSO login)
            #disable-next-line no-hardcoded-env-urls
            { name: 'OIDC_ISSUER', value: 'https://login.microsoftonline.com/aa81b43f-3969-4fd4-80c9-84c411508d82/v2.0' }
            { name: 'CORS_ORIGINS', value: '["https://aigw-dev.lab.cloud.scdom.net"]' }
            { name: 'AUTH_URL', value: authUrl }
            { name: 'CACHE_URL', value: cacheUrl }
            { name: 'LITELLM_URL', value: litellmUrl }
            { name: 'OBSERVABILITY_URL', value: observabilityUrl }
            { name: 'LEAGUE_URL', value: leagueUrl }
            { name: 'LIBRARIAN_URL', value: librarianUrl }
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
            { name: 'CORS_ORIGINS', value: 'https://aigw-dev.lab.cloud.scdom.net' }
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
            { name: 'CORS_ORIGINS', value: '["https://aigw-dev.lab.cloud.scdom.net"]' }
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
            // ACA-Jobs spawn runtime (Component 2)
            { name: 'SCANNER_CONTAINER_RUNTIME', value: 'aca_job' }
            { name: 'SCANNER_RUNNER_JOB_NAME', value: 'job-scanner-runner-${env}-sdc' }
            { name: 'AZURE_RESOURCE_GROUP', value: resourceGroup().name }
            { name: 'AZURE_SUBSCRIPTION_ID', value: subscription().subscriptionId }
            { name: 'AIGW_RUNS_SHARE', value: 'aigw-runs' }
            { name: 'AIGW_RUNS_STORAGE_ACCOUNT', value: 'staigwruns${env}sdc' }
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
            // ACA-Jobs spawn runtime (Component 2)
            { name: 'AGENT_CONTAINER_RUNTIME', value: 'aca_job' }
            { name: 'AGENT_RUNNER_JOB_NAME', value: 'job-agent-runner-${env}-sdc' }
            { name: 'AZURE_RESOURCE_GROUP', value: resourceGroup().name }
            { name: 'AZURE_SUBSCRIPTION_ID', value: subscription().subscriptionId }
            { name: 'AIGW_RUNS_SHARE', value: 'aigw-runs' }
            { name: 'AIGW_RUNS_STORAGE_ACCOUNT', value: 'staigwruns${env}sdc' }
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

// ── admin-portal (Next.js) ──────────────────────────────────────────────────
// NEXT_PUBLIC_* are baked at image build time (Dockerfile.admin + ci.yml
// build-args), so the runtime needs no app config / KV secrets. VNet-internal.
resource caAdminPortal 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-admin-portal-${env}-sdc'
  location: location
  tags: tags
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${uamiId}': {} } }
  properties: {
    managedEnvironmentId: acaEnvId
    workloadProfileName: 'Consumption'
    configuration: {
      ingress: { external: false, targetPort: 3001, transport: 'Http' }
      registries: ghcrRegistries
      secrets: ghcrSecret
    }
    template: {
      containers: [
        {
          name: 'admin-portal'
          image: '${ghcrBase}/admin-portal:${imageTag}'
          resources: stdResources
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 2 }
    }
  }
  dependsOn: [acrPullAssignment, kvSecretsUserAssignment]
}

// ── portal (Next.js) ────────────────────────────────────────────────────────
resource caPortal 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-portal-${env}-sdc'
  location: location
  tags: tags
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${uamiId}': {} } }
  properties: {
    managedEnvironmentId: acaEnvId
    workloadProfileName: 'Consumption'
    configuration: {
      ingress: { external: false, targetPort: 3002, transport: 'Http' }
      registries: ghcrRegistries
      secrets: ghcrSecret
    }
    template: {
      containers: [
        {
          name: 'portal'
          image: '${ghcrBase}/portal:${imageTag}'
          resources: stdResources
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 2 }
    }
  }
  dependsOn: [acrPullAssignment, kvSecretsUserAssignment]
}

// ── toolbox (VNet jumpbox, Component 3) ───────────────────────────────────────
// Minimal VNet-internal Container App with no ingress. Provides control-plane
// reachability to the internal:true gateway for tests + deploy.yml E2E via
// `az containerapp exec`. Uses the public mcr azure-cli image (az+curl+python),
// so no GHCR registry/secret block is needed. Kept alive with sleep infinity.
resource caToolbox 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-toolbox-${env}-sdc'
  location: location
  tags: tags
  // Zero-privilege identity: the jumpbox runs E2E over HTTP (no Azure calls) and
  // must not be a standing RG/Key-Vault foothold.
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${jobsUamiId}': {} } }
  properties: {
    managedEnvironmentId: acaEnvId
    workloadProfileName: 'Consumption'
    configuration: {}
    template: {
      containers: [
        {
          name: 'toolbox'
          image: 'mcr.microsoft.com/azure-cli:latest'
          command: ['sleep', 'infinity']
          resources: stdResources
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
}
