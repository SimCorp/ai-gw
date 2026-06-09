# Phase 1 — IaC Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provision all Azure infrastructure for the AI Gateway Dev environment via Bicep — resource group, networking, Key Vault, PostgreSQL, Redis, ACR, Service Bus, Log Analytics, App Insights, and ACA environment. No application code deployed yet.

**Architecture:** Subscription-scope `main.bicep` creates `rg-aigw-dev-sdc` and orchestrates eight focused modules. The networking module deploys cross-RG (into the LZ-managed VNet). All PaaS services are private-endpoint-only. The ACA environment is internal (VNet-only) with custom domain `aigw-dev.lab.cloud.scdom.net` and wildcard TLS cert `*.lab.cloud.scdom.net`.

**Tech Stack:** Bicep (≥ 0.28), Azure CLI (≥ 2.60), `az deployment sub create`, `az bicep build` for validation.

---

## Resource naming

| Resource | Name | Notes |
|---|---|---|
| Resource group | `rg-aigw-dev-sdc` | Created by main.bicep |
| Key Vault | `kv-aigw-dev-sdc` | |
| PostgreSQL | `psql-aigw-dev-sdc` | |
| Redis | `redis-aigw-dev-sdc` | |
| ACR | `acraigwdevsdc` | Alphanumeric only |
| Service Bus | `sb-aigw-dev-sdc` | |
| Log Analytics | `law-aigw-dev-sdc` | In our RG (LZ workspace inaccessible) |
| App Insights | `appi-aigw-dev-sdc` | |
| ACA environment | `cae-aigw-dev-sdc` | |
| PE subnet | `snet-pe-aigw-dev` | Added to LZ VNet |

## File structure

```
infra/bicep/
├── environments/
│   └── dev/
│       ├── main.bicep           # subscription scope — creates RG, calls all modules
│       └── main.bicepparam      # non-secret dev params (committed to git)
└── modules/
    ├── networking.bicep         # PE subnet in LZ VNet (cross-RG)
    ├── keyVault.bicep           # vault + 5 inter-service secrets
    ├── postgres.bicep           # Flexible Server + two databases + PE
    ├── redis.bicep              # Premium P1 + PE
    ├── acr.bicep                # Standard registry
    ├── serviceBus.bicep         # Standard namespace + queue
    ├── monitoring.bicep         # Log Analytics workspace + App Insights
    ├── containerEnv.bicep       # ACA managed environment + TLS cert
    └── kvPaasSecrets.bicep      # writes PaaS connection strings to KV (post-deploy)
```

## Known risks / open questions

**ACA workload profiles mode**: This plan creates the ACA environment with a `Consumption` workload profile (`workloadProfiles: [{name: 'Consumption', ...}]`). This produces a _Workload Profiles_ environment type, which is correct given the two delegated subnets (`snet-aca-infra` + `snet-aca-workload`) the LZ platform team pre-configured. If the deployment fails with a subnet delegation error, try removing the `workloadProfiles` block entirely to create a Consumption-only environment instead — though this would waste the delegated subnets.

**ACR public endpoint vs. internal ACA**: Standard ACR has no private endpoint support. ACA pulls images over `acraigwdevsdc.azurecr.io` (public). The LZ hub firewall must allow outbound `10.179.231.0/25 → *.azurecr.io:443`. If images fail to pull in Phase 3, request this rule from the SC Platform team. Premium ACR + PE is the long-term fix.

**`any(tlsCertBase64)` type escape**: The certificate `value` property in `Microsoft.App/managedEnvironments/certificates` is typed as a byte array in the REST API. Using `any()` is the documented workaround in Bicep. If `az bicep build` complains, try removing `any()` — the linter sometimes accepts a plain string here.

---

## Task 1: Bootstrap — verify tools and access

**Files:** none

- [ ] **Step 1: Check az CLI and bicep versions**

```bash
az version --query '"azure-cli"' -o tsv   # need ≥ 2.60
az bicep version                           # need ≥ 0.28; install: az bicep install
```

Expected: version numbers printed, no errors.

- [ ] **Step 2: Confirm active subscription is Dev**

```bash
az account show --query "{name:name, id:id}" -o json
```

Expected output:
```json
{"id": "8fc66d8e-c80e-454e-9248-b67af047c2c2", "name": "PlatformAITooling Dev"}
```

If wrong: `az account set --subscription 8fc66d8e-c80e-454e-9248-b67af047c2c2`

- [ ] **Step 3: Verify access to the LZ VNet resource group**

```bash
az network vnet show \
  --name vnet-spoke-platformaitooling-dev-sdc-001 \
  --resource-group rg-spoke-platformaitooling-dev-sdc-001 \
  --query "addressSpace.addressPrefixes" -o tsv
```

Expected: `10.179.231.0/25`

If this fails with a permission error, you need Network Contributor on `rg-spoke-platformaitooling-dev-sdc-001`. Request access from the SC Platform team before proceeding.

- [ ] **Step 4: Confirm your user objectId (needed for Key Vault access policy)**

```bash
az ad signed-in-user show --query "id" -o tsv
```

Expected: `45674099-3cd8-404c-a6ad-871027c8a585`

Record this — it goes into `main.bicepparam` as `deployingPrincipalId`.

- [ ] **Step 5: Locate your TLS cert PFX file**

You need the `*.lab.cloud.scdom.net` cert as a `.pfx` file with its password. These are passed as secure parameters at deploy time — never committed to git.

Confirm the file exists:
```bash
ls -la ~/path/to/wildcard.pfx
```

---

## Task 2: Scaffold the infra/bicep directory

**Files:** Create all empty module files so they can be cross-referenced immediately.

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p infra/bicep/environments/dev
mkdir -p infra/bicep/modules
```

- [ ] **Step 2: Create placeholder files**

```bash
for f in networking keyVault postgres redis acr serviceBus monitoring containerEnv kvPaasSecrets; do
  touch infra/bicep/modules/${f}.bicep
done
touch infra/bicep/environments/dev/main.bicep
touch infra/bicep/environments/dev/main.bicepparam
```

- [ ] **Step 3: Add minimal valid content to each module so `az bicep build` won't error**

Paste this into each `modules/*.bicep` file (replace the empty file):

```bicep
// placeholder — will be filled in subsequent tasks
```

Add this to `environments/dev/main.bicep`:

```bicep
targetScope = 'subscription'
```

- [ ] **Step 4: Verify bicep can parse the files**

```bash
az bicep build --file infra/bicep/environments/dev/main.bicep
```

Expected: no output (success). Fix any syntax errors before continuing.

- [ ] **Step 5: Commit scaffold**

```bash
git add infra/bicep/
git commit -m "chore: scaffold infra/bicep/ directory structure"
```

---

## Task 3: networking.bicep — PE subnet in LZ VNet

**Files:**
- Write: `infra/bicep/modules/networking.bicep`

This module runs in `rg-spoke-platformaitooling-dev-sdc-001` (the LZ VNet RG), not in our app RG. It adds one subnet to the existing VNet. No DNS zone groups — the LZ's DeployIfNotExists policy automatically creates DNS records for private endpoints.

- [ ] **Step 1: Write the module**

```bicep
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
```

- [ ] **Step 2: Validate**

```bash
az bicep build --file infra/bicep/modules/networking.bicep
```

Expected: no output (success).

- [ ] **Step 3: Commit**

```bash
git add infra/bicep/modules/networking.bicep
git commit -m "feat(bicep): networking module — PE subnet in LZ VNet"
```

---

## Task 4: keyVault.bicep — vault and secrets

**Files:**
- Write: `infra/bicep/modules/keyVault.bicep`

All nine inter-service shared secrets are computed deterministically from the resource group ID using `uniqueString()`. The deploying principal gets an access policy to set/get secrets and import certificates. PaaS connection strings are written in later tasks as outputs flow in.

- [ ] **Step 1: Write the module**

```bicep
// infra/bicep/modules/keyVault.bicep

param name string
param location string
param deployingPrincipalId string
@secure()
param agentRelaySecret string
@secure()
param adminInternalToken string
@secure()
param identityKeySecret string
@secure()
param identityServiceToken string
@secure()
param librarianServiceToken string
param tags object = {}

resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: false
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    enablePurgeProtection: false  // allow purge in Dev for easy cleanup
    accessPolicies: [
      {
        tenantId: subscription().tenantId
        objectId: deployingPrincipalId
        permissions: {
          secrets: ['get', 'list', 'set', 'delete']
          certificates: ['get', 'list', 'import', 'delete']
        }
      }
    ]
  }
}

// Inter-service shared secrets
resource secretAgentRelay 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'agent-relay-secret'
  properties: { value: agentRelaySecret }
}

resource secretAdminToken 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'admin-internal-token'
  properties: { value: adminInternalToken }
}

resource secretIdentityKey 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'identity-key-secret'
  properties: { value: identityKeySecret }
}

resource secretIdentityToken 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'identity-service-token'
  properties: { value: identityServiceToken }
}

resource secretLibrarianToken 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'librarian-service-token'
  properties: { value: librarianServiceToken }
}

output kvName string = kv.name
output kvUri string = kv.properties.vaultUri
output kvId string = kv.id
```

> Note: `postgres-url`, `redis-url`, `service-bus-conn`, and `app-insights-conn` are written by their respective modules after those resources are created — they're passed back to `main.bicep` as outputs and then written here via an additional secrets module. See Task 11 for how this is wired.

- [ ] **Step 2: Validate**

```bash
az bicep build --file infra/bicep/modules/keyVault.bicep
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add infra/bicep/modules/keyVault.bicep
git commit -m "feat(bicep): keyVault module — vault and inter-service secrets"
```

---

## Task 5: postgres.bicep — Flexible Server and private endpoint

**Files:**
- Write: `infra/bicep/modules/postgres.bicep`

- [ ] **Step 1: Write the module**

```bicep
// infra/bicep/modules/postgres.bicep

param name string
param location string
param peSubnetId string
@secure()
param administratorPassword string
param administratorLogin string = 'aigwadmin'
param tags object = {}

resource postgresServer 'Microsoft.DBforPostgreSQL/flexibleServers@2023-12-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: 'Standard_B2ms'
    tier: 'Burstable'
  }
  properties: {
    administratorLogin: administratorLogin
    administratorLoginPassword: administratorPassword
    version: '16'
    storage: {
      storageSizeGB: 32
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    network: {
      publicNetworkAccess: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    authConfig: {
      activeDirectoryAuth: 'Disabled'
      passwordAuth: 'Enabled'
    }
  }
}

resource dbAigateway 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-12-01' = {
  parent: postgresServer
  name: 'aigateway'
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

resource dbLitellm 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-12-01' = {
  parent: postgresServer
  name: 'litellm'
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

resource privateEndpoint 'Microsoft.Network/privateEndpoints@2023-09-01' = {
  name: 'pe-postgres-aigw-dev-sdc'
  location: location
  properties: {
    subnet: {
      id: peSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: 'pe-postgres-conn'
        properties: {
          privateLinkServiceId: postgresServer.id
          groupIds: ['postgresqlServer']
        }
      }
    ]
  }
}

output postgresFqdn string = postgresServer.properties.fullyQualifiedDomainName
```

- [ ] **Step 2: Validate**

```bash
az bicep build --file infra/bicep/modules/postgres.bicep
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add infra/bicep/modules/postgres.bicep
git commit -m "feat(bicep): postgres module — Flexible Server, two databases, PE"
```

---

## Task 6: redis.bicep — Premium cache and private endpoint

**Files:**
- Write: `infra/bicep/modules/redis.bicep`

- [ ] **Step 1: Write the module**

```bicep
// infra/bicep/modules/redis.bicep

param name string
param location string
param peSubnetId string
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
      // Enable active-geo-replication data persistence (RDB) for semantic cache durability
      'rdb-backup-enabled': 'false'
      // maxmemory-policy: allkeys-lru — evict LRU keys when full
      'maxmemory-policy': 'allkeys-lru'
    }
  }
}

resource privateEndpoint 'Microsoft.Network/privateEndpoints@2023-09-01' = {
  name: 'pe-redis-aigw-dev-sdc'
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
// Connection string assembled in main.bicep using listKeys()
output redisId string = redisCache.id
```

> The Redis connection string requires calling `listKeys()` which cannot be done inside the module output — it must be called in `main.bicep` after the module completes. See Task 11.

- [ ] **Step 2: Validate**

```bash
az bicep build --file infra/bicep/modules/redis.bicep
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add infra/bicep/modules/redis.bicep
git commit -m "feat(bicep): redis module — Premium P1, PE"
```

---

## Task 7: acr.bicep — container registry

**Files:**
- Write: `infra/bicep/modules/acr.bicep`

- [ ] **Step 1: Write the module**

```bicep
// infra/bicep/modules/acr.bicep
// ACR names must be globally unique and alphanumeric only (no dashes)

param name string
param location string
param tags object = {}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: 'Standard'
  }
  properties: {
    adminUserEnabled: false  // use managed identity / OIDC, never admin creds
    publicNetworkAccess: 'Enabled'  // standard tier does not support PE; images pulled over public endpoint by ACA
    zoneRedundancy: 'Disabled'
  }
}

output acrLoginServer string = acr.properties.loginServer
output acrId string = acr.id
```

> ACR Standard tier does not support private endpoints. ACA pulls images over the public ACR endpoint authenticated via the ACA environment's managed identity. Premium tier (with PE support) is a Phase 2+ upgrade path if needed.

- [ ] **Step 2: Validate**

```bash
az bicep build --file infra/bicep/modules/acr.bicep
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add infra/bicep/modules/acr.bicep
git commit -m "feat(bicep): acr module — Standard registry"
```

---

## Task 8: serviceBus.bicep — namespace and observability queue

**Files:**
- Write: `infra/bicep/modules/serviceBus.bicep`

- [ ] **Step 1: Write the module**

```bicep
// infra/bicep/modules/serviceBus.bicep

param name string
param location string
param peSubnetId string
param tags object = {}

resource sbNamespace 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: 'Standard'
    tier: 'Standard'
  }
  properties: {}
}

resource observabilityQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: sbNamespace
  name: 'observability-events'
  properties: {
    maxSizeInMegabytes: 1024
    lockDuration: 'PT1M'
    maxDeliveryCount: 10
    requiresSession: false
  }
}

resource privateEndpoint 'Microsoft.Network/privateEndpoints@2023-09-01' = {
  name: 'pe-sb-aigw-dev-sdc'
  location: location
  properties: {
    subnet: {
      id: peSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: 'pe-sb-conn'
        properties: {
          privateLinkServiceId: sbNamespace.id
          groupIds: ['namespace']
        }
      }
    ]
  }
}

output sbId string = sbNamespace.id
output sbName string = sbNamespace.name
```

- [ ] **Step 2: Validate**

```bash
az bicep build --file infra/bicep/modules/serviceBus.bicep
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add infra/bicep/modules/serviceBus.bicep
git commit -m "feat(bicep): serviceBus module — Standard namespace, observability queue, PE"
```

---

## Task 9: monitoring.bicep — Log Analytics workspace and App Insights

**Files:**
- Write: `infra/bicep/modules/monitoring.bicep`

The LZ-provided Log Analytics workspace is in a management subscription not directly accessible. We create our own workspace in `rg-aigw-dev-sdc`. If the platform team later provides a workspace ID, switch the App Insights `workspaceResourceId` parameter to point at theirs.

- [ ] **Step 1: Write the module**

```bicep
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
output lawSharedKey string = listKeys(law.id, '2023-09-01').primarySharedKey
```

- [ ] **Step 2: Validate**

```bash
az bicep build --file infra/bicep/modules/monitoring.bicep
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add infra/bicep/modules/monitoring.bicep
git commit -m "feat(bicep): monitoring module — Log Analytics workspace + App Insights"
```

---

## Task 10: containerEnv.bicep — ACA managed environment

**Files:**
- Write: `infra/bicep/modules/containerEnv.bicep`

Creates the ACA environment in the LZ-provided infra subnet (`snet-aca-infra`). Internal-only (VNet-scoped). The wildcard TLS cert is uploaded to the environment so Container Apps can reference it in Phase 3.

- [ ] **Step 1: Write the module**

```bicep
// infra/bicep/modules/containerEnv.bicep

param name string
param location string
param infrastructureSubnetId string
param lawCustomerId string
@secure()
param lawSharedKey string
@secure()
param tlsCertBase64 string        // base64-encoded PFX content
@secure()
param tlsCertPassword string      // PFX export password
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
        // Consumption profile — no dedicated nodes
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}

// Upload wildcard TLS cert so Phase 3 Container Apps can reference it
resource tlsCert 'Microsoft.App/managedEnvironments/certificates@2024-03-01' = {
  parent: acaEnv
  name: 'tls-wildcard-lab'
  properties: {
    value: any(tlsCertBase64)   // base64 PFX
    password: tlsCertPassword
  }
}

output acaEnvId string = acaEnv.id
output acaEnvName string = acaEnv.name
output acaStaticIp string = acaEnv.properties.staticIp
output acaDefaultDomain string = acaEnv.properties.defaultDomain
output tlsCertId string = tlsCert.id
```

- [ ] **Step 2: Validate**

```bash
az bicep build --file infra/bicep/modules/containerEnv.bicep
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add infra/bicep/modules/containerEnv.bicep
git commit -m "feat(bicep): containerEnv module — internal ACA environment + TLS cert"
```

---

## Task 11: main.bicep and main.bicepparam — wire all modules

**Files:**
- Write: `infra/bicep/environments/dev/main.bicep`
- Write: `infra/bicep/environments/dev/main.bicepparam`

The main orchestration. Creates the resource group at subscription scope, then calls each module in the right scope and order. PaaS connection strings are retrieved via `listKeys()` and written to Key Vault as a second pass.

- [ ] **Step 1: Write main.bicep**

```bicep
// infra/bicep/environments/dev/main.bicep
targetScope = 'subscription'

param location string = 'swedencentral'
param env string = 'dev'
param vnetResourceGroup string
param vnetName string
param acaInfraSubnetId string  // full resource ID of snet-aca-infra
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
  dependsOn: [networking]
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
  dependsOn: [networking]
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
  dependsOn: [networking]
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
  dependsOn: [monitoring]
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
  dependsOn: [keyVault, postgres, redis, serviceBus, monitoring]
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
```

- [ ] **Step 2: Write kvPaasSecrets.bicep**

This module resolves PaaS keys via `listKeys()` on `existing` resource references and constructs all connection strings internally. No secret ever surfaces as a module output.

```bicep
// infra/bicep/modules/kvPaasSecrets.bicep

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

var redisKey = listKeys(redisRef.id, '2023-08-01').primaryKey
// Python redis-py URL format: rediss://:password@host:6380/0
var redisUrl = 'rediss://:${redisKey}@${redisName}.redis.cache.windows.net:6380/0'

var sbConnStr = listKeys(
  resourceId('Microsoft.ServiceBus/namespaces/authorizationRules', serviceBusName, 'RootManageSharedAccessKey'),
  '2022-10-01-preview'
).primaryConnectionString

var postgresUrl = 'postgresql://${postgresAdminLogin}:${postgresAdminPassword}@${postgresFqdn}:5432/aigateway?sslmode=require'

resource secretPostgres 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'postgres-url'
  properties: { value: postgresUrl }
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
```

Create the file:

```bash
# Write the content above to infra/bicep/modules/kvPaasSecrets.bicep
# (replace the placeholder created in Task 2)
```

- [ ] **Step 3: Write main.bicepparam**

```bicep
// infra/bicep/environments/dev/main.bicepparam
// Committed to git — contains NO secrets.
using './main.bicep'

param location = 'swedencentral'
param env = 'dev'
param vnetResourceGroup = 'rg-spoke-platformaitooling-dev-sdc-001'
param vnetName = 'vnet-spoke-platformaitooling-dev-sdc-001'
param acaInfraSubnetId = '/subscriptions/8fc66d8e-c80e-454e-9248-b67af047c2c2/resourceGroups/rg-spoke-platformaitooling-dev-sdc-001/providers/Microsoft.Network/virtualNetworks/vnet-spoke-platformaitooling-dev-sdc-001/subnets/snet-aca-infra'
param deployingPrincipalId = '45674099-3cd8-404c-a6ad-871027c8a585'

// postgresAdminPassword, tlsCertBase64, tlsCertPassword are passed at deploy time
// via --parameters on the az CLI command — never committed to this file.
```

- [ ] **Step 4: Validate all files**

```bash
az bicep build --file infra/bicep/environments/dev/main.bicep
```

Expected: no output. Fix any type or reference errors before continuing.

- [ ] **Step 5: Commit**

```bash
git add infra/bicep/
git commit -m "feat(bicep): main orchestration — wires all modules, subscription scope"
```

---

## Task 12: Validate with what-if

**Files:** none

- [ ] **Step 1: Prepare secure parameter values in shell (not committed)**

```bash
export POSTGRES_ADMIN_PASSWORD="<choose a strong password>"
export TLS_CERT_BASE64=$(base64 -w 0 /path/to/wildcard.lab.cloud.scdom.net.pfx)
export TLS_CERT_PASSWORD="<pfx export password>"
```

- [ ] **Step 2: Run what-if to preview all changes**

```bash
az deployment sub what-if \
  --location swedencentral \
  --template-file infra/bicep/environments/dev/main.bicep \
  --parameters infra/bicep/environments/dev/main.bicepparam \
  --parameters postgresAdminPassword="$POSTGRES_ADMIN_PASSWORD" \
  --parameters tlsCertBase64="$TLS_CERT_BASE64" \
  --parameters tlsCertPassword="$TLS_CERT_PASSWORD"
```

Expected: a diff table showing resources to be created. Review each entry and confirm nothing unexpected appears (e.g. resources being deleted).

Common issues and fixes:
- `"The subscription is not registered to use namespace 'Microsoft.App'"` → run `az provider register --namespace Microsoft.App`
- `"InvalidTemplateDeployment"` on listKeys → check module `dependsOn` ordering
- `"SubnetIsFull"` → verify the /26 PE subnet CIDR `10.179.231.64/26` doesn't overlap with existing subnets

- [ ] **Step 3: Fix any issues, re-run what-if until clean**

When the what-if shows only expected creates with no unexpected modifications or deletions, proceed.

---

## Task 13: Deploy to Dev

**Files:** none

- [ ] **Step 1: Run the deployment**

```bash
az deployment sub create \
  --location swedencentral \
  --name "aigw-phase1-$(date +%Y%m%d%H%M)" \
  --template-file infra/bicep/environments/dev/main.bicep \
  --parameters infra/bicep/environments/dev/main.bicepparam \
  --parameters postgresAdminPassword="$POSTGRES_ADMIN_PASSWORD" \
  --parameters tlsCertBase64="$TLS_CERT_BASE64" \
  --parameters tlsCertPassword="$TLS_CERT_PASSWORD"
```

This takes approximately 15–25 minutes (PostgreSQL Flexible Server is the longest — ~10 min).

Expected: `"provisioningState": "Succeeded"` at completion.

- [ ] **Step 2: Capture key outputs**

```bash
az deployment sub show \
  --name "aigw-phase1-<timestamp>" \
  --query "properties.outputs" -o json
```

Record the following for the DNS and firewall steps:
- `acaStaticIp` — the private IP of the ACA environment's internal load balancer
- `acrLoginServer` — the ACR login server (e.g. `acraigwdevsdc.azurecr.io`)
- `tlsCertId` — the resource ID of the uploaded cert (used in Phase 3 Container App definitions)

Store these in `infra/bicep/environments/dev/main.bicepparam` as comments for reference (not as params — they're outputs, not inputs).

---

## Task 14: Post-deploy verification

**Files:** none — az CLI verification only

- [ ] **Step 1: Verify the resource group and all resources exist**

```bash
az resource list --resource-group rg-aigw-dev-sdc -o table
```

Expected: 10+ resources including the ACA environment, Key Vault, PostgreSQL, Redis, ACR, Service Bus, App Insights, Log Analytics workspace, private endpoints.

- [ ] **Step 2: Verify ACA environment is healthy**

```bash
az containerapp env show \
  --name cae-aigw-dev-sdc \
  --resource-group rg-aigw-dev-sdc \
  --query "{status:properties.provisioningState, ip:properties.staticIp, domain:properties.defaultDomain}" \
  -o json
```

Expected:
```json
{"status": "Succeeded", "ip": "10.179.231.x", "domain": "cae-aigw-dev-sdc.<region>.azurecontainerapps.io"}
```

- [ ] **Step 3: Verify Key Vault secrets were written**

```bash
az keyvault secret list --vault-name kv-aigw-dev-sdc --query "[].name" -o tsv
```

Expected (9 secrets):
```
agent-relay-secret
admin-internal-token
identity-key-secret
identity-service-token
librarian-service-token
postgres-url
redis-url
service-bus-conn
app-insights-conn
```

- [ ] **Step 4: Verify private endpoints are connected**

```bash
az network private-endpoint list --resource-group rg-aigw-dev-sdc \
  --query "[].{name:name, state:privateLinkServiceConnections[0].privateLinkServiceConnectionState.status}" \
  -o table
```

Expected: all four PEs show `Approved` state. If `Pending`, the LZ DeployIfNotExists policy auto-approves within a few minutes — re-check.

- [ ] **Step 5: Verify TLS cert is uploaded to ACA environment**

```bash
az containerapp env certificate list \
  --name cae-aigw-dev-sdc \
  --resource-group rg-aigw-dev-sdc \
  -o table
```

Expected: one certificate `tls-wildcard-lab` with status `Succeeded`.

- [ ] **Step 6: Record the ACA static IP and request DNS + firewall changes**

From the output captured in Task 13, record the static IP and trigger two external actions:

1. **DNS admin** — create A record: `aigw-dev.lab.cloud.scdom.net → <acaStaticIp>`
2. **SC Platform team** — open hub Azure Firewall rule: `corp VPN CIDR → <acaStaticIp>:443`

These are external actions that don't block Phase 2 (container pipeline). Phase 3 (Container Apps) requires the DNS record to be in place for the custom domain verification.

- [ ] **Step 7: Commit the static IP as a reference comment in main.bicepparam**

```bash
# Add as a comment at the bottom of main.bicepparam:
# ACA static IP (post-deploy): 10.179.231.x
# ACR login server: acraigwdevsdc.azurecr.io
# TLS cert ID: /subscriptions/.../certificates/tls-wildcard-lab
# DNS A record needed: aigw-dev.lab.cloud.scdom.net → 10.179.231.x
git add infra/bicep/environments/dev/main.bicepparam
git commit -m "docs(bicep): record post-deploy outputs as reference comments"
```

---

## Phase 1 complete — verification checklist

- [ ] `rg-aigw-dev-sdc` exists with all 10+ resources in `Succeeded` state
- [ ] ACA environment `cae-aigw-dev-sdc` is healthy with a static IP
- [ ] All 9 Key Vault secrets are present
- [ ] All 4 private endpoints show `Approved`
- [ ] TLS cert `tls-wildcard-lab` uploaded to ACA environment
- [ ] Static IP recorded; DNS and firewall requests sent to DNS admin and platform team

**Next:** Phase 2 — expand CI matrix to all 12 services and add ACR push job.
