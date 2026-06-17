# AI Gateway — Azure Enterprise Deployment Design

**Date:** 2026-06-08
**Status:** Approved
**Scope:** Enterprise deployment of ai-gw to Azure using SC LZ PlatformAITooling Dev and Test subscriptions
**Related:** [Original gateway design](2026-05-05-ai-gateway-design.md)

---

## 1. Overview

Deploy the AI Gateway stack to Azure, replacing the local Docker Compose setup with a production-grade deployment in the SimCorp Landing Zone. Two environments are in scope: **Dev** (first) and **Test** (same Bicep, different subscription). Production is a follow-on once Test is stable.

The original design spec names the required Azure services. This doc defines **how to get there**: IaC, networking, container workloads, secrets management, deployment pipeline, and monitoring wiring.

### Environments

| Environment | Subscription | Subscription ID | Region | Purpose |
|---|---|---|---|---|
| Dev | SC LZ PlatformAITooling Dev | `8fc66d8e-c80e-454e-9248-b67af047c2c2` | Sweden Central | Active development, inner-loop testing |
| Test | SC LZ PlatformAITooling Test | `7ecf4a3e-d200-47ea-aadd-441607e6c642` | Sweden Central | Integration testing, pre-production validation |

**Tenant ID:** `aa81b43f-3969-4fd4-80c9-84c411508d82`

Both environments use identical Bicep modules; the `main.bicepparam` file is the only thing that differs between them. Phase 1 targets Dev; Test is wired up in Phase 4 once the deploy pipeline is proven.

**Not in scope:** feature changes to the gateway services themselves; Production environment; multi-region.

---

## 2. Landing Zone Context

> **ALZ pattern note:** Enterprise Landing Zones are a *vending* pattern — the platform team provides subscription networking, DNS, Log Analytics, and Azure Policy. We build application-layer resources on top.

### What the LZ provides (confirmed via Azure CLI)

| Resource | What exists | Notes |
|---|---|---|
| Spoke VNet (Dev) | `vnet-spoke-platformaitooling-dev-sdc-001` — `10.179.231.0/25` | VNet-peered to hub; 128 IPs total |
| Spoke VNet (Test) | Exists at `10.179.230.128/25` | No subnets yet — all subnets created by our Bicep |
| Log Analytics Workspace (Dev) | `law-aca-dev-sdc` | LZ-provided; App Insights references this |
| Private DNS — centrally managed | `privatelink.*` zones via LZ DeployIfNotExists policy | **Do not create these zones** |
| Private DNS — own zone | `platformaitooling.local` (linked to Dev VNet) | Use for internal service discovery if needed |
| Naming convention | `<type>-<descriptor>-<env>-sdc[-001]` | e.g. `law-aca-dev-sdc`, `vnet-spoke-platformaitooling-dev-sdc-001` |
| Azure Policy | AMBA (Azure Monitor Baseline Alerts) in both subscriptions | No blocking compute/networking policies found |
| Resource group (Dev) | `rg-spoke-platformaitooling-dev-sdc-001` | Spoke networking lives here; app resources get their own RG |

### Dev VNet — confirmed subnet layout

```
vnet-spoke-platformaitooling-dev-sdc-001   10.179.231.0/25   (128 IPs)
  ├── snet-aca-infra      10.179.231.0/27    32 IPs — ACA environment infrastructure  [delegated, exists]
  ├── snet-aca-workload   10.179.231.32/27   32 IPs — ACA workload profiles           [delegated, exists]
  └── [free]              10.179.231.64/26   64 IPs — available for Private Endpoints [we create this]
```

Both existing subnets are delegated to `Microsoft.App/environments`. ACA must use them as-is. The free /26 becomes our Private Endpoint subnet.

---

## 3. Compute Platform — Azure Container Apps

**Decision: Azure Container Apps on the existing LZ networking.**

The LZ is purpose-built for ACA. Both subnets are pre-delegated; we create the ACA environment into them. This eliminates Helm, the Key Vault CSI driver, and NGINX — replaced by Bicep Container App definitions and ACA's native Key Vault secret references.

AKS would require the platform team to re-vend a larger (/22+) VNet. ACA lets us start now.

---

## 4. Target Architecture

### Azure Resources

| Resource | Azure Service | Dev SKU | Notes |
|---|---|---|---|
| Container compute | Azure Container Apps environment | Consumption | Created by Bicep into `snet-aca-infra` / `snet-aca-workload` |
| Database | Azure Database for PostgreSQL Flexible Server | Burstable B2ms | Two databases: `aigateway` + `litellm` |
| Cache | Azure Cache for Redis | Premium P1 | RediSearch module required for semantic cache |
| Container registry | Azure Container Registry | Standard | `acrpush` role for GitHub Actions |
| Secrets | Azure Key Vault | Standard | ACA native secret refs; TLS cert stored here |
| Message bus | Azure Service Bus | Standard namespace | One queue: `observability-events` |
| Observability | Azure Monitor + Application Insights | Workspace-based | References `law-aca-dev-sdc` |
| Identity | Azure Entra ID (existing tenant) | — | Managed Identity per Container App |

### Networking

```
Hub VNet (SC Platform team, Sweden Central)
  └── Spoke VNet: vnet-spoke-platformaitooling-dev-sdc-001   10.179.231.0/25
        ├── snet-aca-infra      10.179.231.0/27    ACA env infrastructure       [delegated, LZ-provided]
        ├── snet-aca-workload   10.179.231.32/27   ACA workloads                [delegated, LZ-provided]
        └── snet-pe-aigw-dev    10.179.231.64/26   Private Endpoints — all PaaS [created by Bicep]
```

**PaaS access:** Redis, PostgreSQL, Key Vault, Service Bus all accessed via Private Endpoints in `snet-pe-aigw-dev`. No public access on any PaaS service.

**Private DNS zones (`privatelink.*`):** centrally managed by the LZ — reference only, never create.

### Access from Corp VPN

The ACA environment is created with `internal: true` — all ingress is VNet-only. Engineers reach it over the corp VPN → hub → peered spoke VNet.

**One firewall rule needed** (hub Azure Firewall or equivalent):
- Source: corp VPN client address range
- Destination: ACA environment static IP (assigned at env creation, recorded in `main.bicepparam`)
- Port: **443** (TCP)

No other ports need to be opened.

### TLS and Custom Domain

| Item | Value |
|---|---|
| Dev FQDN | `aigw-dev.lab.cloud.scdom.net` |
| Certificate | Wildcard `*.lab.cloud.scdom.net` (+ apex `lab.cloud.scdom.net`) |
| Cert storage | Imported to Key Vault as PFX; ACA environment references it |
| DNS record | A record: `aigw-dev.lab.cloud.scdom.net → <ACA static IP>` (DNS admin to create in `lab.cloud.scdom.net` zone) |

When Bicep deploys the ACA environment:
1. Environment gets a static private IP from `snet-aca-infra`
2. Static IP is output and recorded (no secrets — it's just an IP)
3. Cert PFX is imported to Key Vault; ACA environment is configured with the custom domain + cert

### Container Apps Service Layout

Each gateway service is one Container App. Naming follows `ca-<service>-dev-sdc`.

| App | Internal port | Ingress | Min replicas |
|---|---|---|---|
| `ca-auth-dev-sdc` | 8001 | Internal | 1 |
| `ca-cache-dev-sdc` | 8002 | Internal | 1 |
| `ca-litellm-dev-sdc` | 8003 | Internal | 1 |
| `ca-observability-dev-sdc` | 8004 | Internal | 1 |
| `ca-admin-api-dev-sdc` | 8005 | Internal | 1 |
| `ca-identity-dev-sdc` | 8006 | Internal | 1 |
| `ca-agent-relay-dev-sdc` | 8007 | External (VNet-scoped) | 1 |
| `ca-librarian-dev-sdc` | 8008 | Internal | 1 |
| `ca-memory-dev-sdc` | 8009 | Internal | 1 |
| `ca-league-dev-sdc` | 8010 | Internal | 1 |
| `ca-scanner-dev-sdc` | — | None (background worker) | 1 |
| `ca-workflow-worker-dev-sdc` | — | None (background worker) | 0 (scale-to-zero) |
| `ca-admin-portal-dev-sdc` | 3001 | External (VNet-scoped) | 1 |
| `ca-portal-dev-sdc` | 3002 | External (VNet-scoped) | 1 |

The `auth` service is the AI request-path entry point and is exposed via the ACA environment's custom domain (`aigw-dev.lab.cloud.scdom.net`). Since the environment is `internal: true`, "external" ingress means VNet-reachable only — no public IP is assigned.

### Secrets Management — ACA Native Key Vault References

ACA supports direct Key Vault secret references without the CSI driver. Each Container App declares its secrets as KV references; ACA resolves them at deploy time using the app's Managed Identity.

```bicep
// Excerpt — auth Container App secrets block
secrets: [
  {
    name: 'database-url'
    keyVaultUrl: 'https://kv-aigw-dev-sdc.vault.azure.net/secrets/postgres-url'
    identity: authManagedIdentity.id
  }
  {
    name: 'app-insights-conn'
    keyVaultUrl: 'https://kv-aigw-dev-sdc.vault.azure.net/secrets/app-insights-conn'
    identity: authManagedIdentity.id
  }
]
env: [
  { name: 'DATABASE_URL', secretRef: 'database-url' }
  { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', secretRef: 'app-insights-conn' }
]
```

Each service gets its own Managed Identity with Key Vault `get`+`list` scoped to its secrets only.

---

## 5. IaC Strategy

### Tool — Bicep

**Deployment mode:** `az deployment group create` (resource group scope). CI/CD calls `az deployment` via an OIDC-authenticated service principal. No state backend required — ARM tracks deployment state; re-runs are idempotent.

### Resource Group Layout

| Resource group | Contains | Subscription |
|---|---|---|
| `rg-spoke-platformaitooling-dev-sdc-001` | Spoke VNet, subnets (LZ-managed — we do not touch this RG) | Dev |
| `rg-aigw-dev-sdc` | All app resources: ACA env, PaaS, KV, ACR, Service Bus, App Insights | Dev |
| `rg-aigw-test-sdc` | Identical layout for Test | Test |

### Module Structure

```
infra/bicep/
├── environments/
│   ├── dev/
│   │   ├── main.bicep           # orchestration — calls all modules
│   │   └── main.bicepparam      # dev parameter values (committed; no secrets)
│   └── test/
│       ├── main.bicep           # identical to dev/
│       └── main.bicepparam      # test parameter values
└── modules/
    ├── networking.bicep         # snet-pe-aigw-dev + private endpoints; references LZ DNS zones
    ├── containerEnv.bicep       # ACA environment (internal, VNet-integrated) + custom domain + cert
    ├── containerApps.bicep      # all 14 Container App definitions + managed identities
    ├── postgres.bicep           # Flexible Server, databases, private endpoint
    ├── redis.bicep              # Premium P1, RediSearch, private endpoint
    ├── keyVault.bicep           # vault, access policies, secrets + TLS cert import
    ├── acr.bicep                # registry, role assignments
    ├── serviceBus.bicep         # namespace, queue
    └── monitoring.bicep         # App Insights referencing law-aca-dev-sdc
```

### Key Vault Secrets Provisioned by Bicep

**Secrets written by IaC, not echoed as outputs.** The `keyVault` module accepts a `secrets` map and writes each as a Key Vault secret. Connection strings never appear in IaC output or CI logs.

| Secret name | Value source | Consumer(s) |
|---|---|---|
| `postgres-url` | PostgreSQL `listConnectionStrings()` | auth, admin, observability, identity, league, librarian, memory |
| `redis-url` | Redis `listKeys()` | auth, cache |
| `service-bus-conn` | Service Bus `listKeys()` | observability (producer), workflow-worker |
| `app-insights-conn` | App Insights `connectionString` output | all services |
| `agent-relay-secret` | `uniqueString()` seeded from resource group ID | agent-relay, workflow-worker |
| `admin-internal-token` | `uniqueString()` seeded from resource group ID | workflow-worker, admin |
| `identity-key-secret` | `uniqueString()` seeded from resource group ID | identity |
| `identity-service-token` | `uniqueString()` seeded from resource group ID | identity |
| `librarian-service-token` | `uniqueString()` seeded from resource group ID | librarian |
| `tls-cert` | PFX passed as `@secure()` parameter | ACA environment custom domain |

> `uniqueString()` produces deterministic values per deployment, desirable for idempotent re-runs. If stronger randomness is needed, generate secrets in a pre-deploy CI step and pass as `@secure()` parameters.

---

## 6. Container Pipeline

### Current State

CI builds four services (`auth`, `cache`, `admin-api`, `observability`) and pushes to GHCR. Eight services are missing and the registry is wrong for Azure.

### Required Changes

**Expand the CI matrix** to cover all 12 Python services:

```
auth, cache, admin-api, observability,
identity, agent-relay, librarian, memory,
league, scanner, workflow-worker, litellm
```

(Frontend apps `admin-portal` and `portal` are excluded — pnpm monorepo Dockerfiles need a separate containerisation effort.)

**Add `acr-push` job** to `ci.yml`:

1. Authenticates to Azure via GitHub OIDC + Federated Credential (no stored secrets)
2. Tags images: `<acr>.azurecr.io/<name>:sha-<sha>` and `<acr>.azurecr.io/<name>:dev-latest`
3. Pushes to ACR using `docker buildx`
4. Runs only on `push` to `master` after all test jobs pass

### OIDC Federated Credential Setup

One Entra ID App Registration (`ai-gw-github-actions`) with a Federated Credential:
- `repo: <org>/ai-gw`
- `ref: refs/heads/master`

Role assignments:
- `AcrPush` on the ACR resource
- `Contributor` on `rg-aigw-dev-sdc` (for `az deployment group create`)

---

## 7. CI/CD Deployment Pipeline

### New Workflow: `deploy.yml`

Triggered by `workflow_run` on `ci.yml` completing successfully on `master`.

```
jobs:
  push-to-acr          # build + tag + push all 12 services to ACR
    needs: (ci.yml passed)

  deploy-dev           # az deployment group create
    needs: push-to-acr
    steps:
      - azure/login (OIDC)
      - az deployment group create \
          --resource-group rg-aigw-dev-sdc \
          --template-file infra/bicep/environments/dev/main.bicep \
          --parameters infra/bicep/environments/dev/main.bicepparam \
          --parameters imageTag=sha-${{ github.sha }}

  smoke-test           # HTTP health checks
    needs: deploy-dev
    steps:
      - run from a self-hosted runner or ACA Job with VNet access
      - curl https://aigw-dev.lab.cloud.scdom.net/auth/health
      - curl https://aigw-dev.lab.cloud.scdom.net/cache/health
      - ... (all active services)
      - fail loudly if any 5xx
```

**Rollback:** Re-run the deploy job with the previous `imageTag` — ACA updates are atomic per revision.

> Note: the smoke-test job must run from a VNet-connected runner (self-hosted in the LZ, or an ACA Job) because the environment is `internal: true`.

---

## 8. Monitoring

- **Application Insights** (workspace-based, references `law-aca-dev-sdc`)
- Each service receives `APPLICATIONINSIGHTS_CONNECTION_STRING` via ACA secret ref
- Python services: `azure-monitor-opentelemetry` auto-instrumentation via `configure_azure_monitor()` at startup
- Existing observability service Postgres cost tables feed the admin portal dashboards (unchanged)

### Alerts (defined in `monitoring.bicep`)

| Alert | Threshold | Action |
|---|---|---|
| Gateway p99 latency | > 500ms for 5 min | Teams webhook notification |
| Error rate | > 5% of requests over 5 min | Teams webhook notification |
| Redis eviction | Any evictions | Warning notification |
| PostgreSQL CPU | > 80% for 5 min | Warning notification |
| Container App restart | > 3 restarts in 5 min | Alert |

---

## 9. Implementation Phases

### Phase 1 — IaC Foundation

Provision all Azure resources via Bicep. No app deployed yet. All PaaS is private-endpoint-only.

Deliverables:
- `infra/bicep/` module structure
- `rg-aigw-dev-sdc` resource group created
- PE subnet (`snet-pe-aigw-dev`) added to the LZ VNet
- ACA environment created (`internal: true`, VNet-integrated, custom domain `aigw-dev.lab.cloud.scdom.net`)
- PostgreSQL, Redis, Key Vault, Service Bus, ACR, App Insights all deployed and PE-connected
- All secrets written to Key Vault including TLS cert
- Verification: ACA environment healthy; `az containerapp env show` returns `Succeeded`; PostgreSQL and Redis reachable from within VNet

### Phase 2 — Container Pipeline

Expand CI matrix and add ACR push.

Deliverables:
- All 12 services in `ci.yml` matrix
- `acr-push` job with OIDC auth
- Entra ID App Registration + Federated Credential registered
- Verification: all 12 images appear in ACR after a `master` push

### Phase 3 — Container App Definitions

Write all Container App Bicep definitions, wire Key Vault secret refs.

Deliverables:
- `infra/bicep/modules/containerApps.bicep` — all 14 apps defined
- Managed Identity per app with scoped Key Vault access
- First deploy: all Container Apps running, `/health` endpoints return 200
- `https://aigw-dev.lab.cloud.scdom.net/auth/health` returns 200 with valid TLS

### Phase 4 — Deployment Pipeline + Test Environment

Wire `deploy.yml` and replicate IaC to Test subscription.

Deliverables:
- `deploy.yml` workflow — automated deploy triggered by `master` push
- `environments/test/main.bicepparam`
- Test environment provisioned in `PlatformAITooling Test` subscription

### Phase 5 — Smoke Test and Handoff

End-to-end functional validation.

Deliverables:
- Register a team via admin portal
- Issue an API key
- Make a chat completion call through the gateway
- Verify: cache hit on second identical call, observability event recorded, cost row in Postgres
- Ops runbook with ACA-specific entries (revision management, log streaming, scale rules)

---

## 10. Open Questions

All Phase 1 blockers are resolved. Items below are either confirmed, deferred to their phase, or require one external action.

| # | Question | Status |
|---|---|---|
| 1 | Spoke VNet — LZ-vended or we create? | **Resolved: LZ provides it** |
| 2 | Private DNS zones centrally managed? | **Resolved: yes — must not create our own** |
| 3 | Log Analytics Workspace? | **Resolved: `law-aca-dev-sdc`** |
| 4 | Resource naming convention? | **Resolved: `<type>-<descriptor>-<env>-sdc[-001]`** |
| 5 | Allowed region? | **Resolved: Sweden Central** |
| 6 | Azure Policy blockers? | **Resolved: AMBA only, no blocking policies** |
| 7 | IaC tool? | **Resolved: Bicep** |
| 8 | Subscription IDs? | **Resolved: see §1** |
| 9 | Compute platform: ACA or AKS? | **Resolved: ACA** |
| 10 | External ingress acceptable for Dev? | **Resolved: VNet-only (internal: true) is fine** |
| 11 | FQDN and TLS cert? | **Resolved: `aigw-dev.lab.cloud.scdom.net`, wildcard `*.lab.cloud.scdom.net`** |
| 12 | Shared ACR or per-workload? | Per-workload (`acr-aigw-dev-sdc`) — confirm with Platform team if shared ACR exists |
| 13 | GitHub Actions OIDC Federated Credential registered? | Not yet — needed for Phase 2 |
| 14 | Self-hosted runner or ACA Job for smoke tests? | Needed for Phase 4 — VNet-connected runner required |
| 15 | DNS A record for `aigw-dev.lab.cloud.scdom.net`? | DNS admin to create after Phase 1 (ACA static IP known post-deploy) |
| 16 | Hub firewall rule for VPN → ACA:443? | Platform team to open after Phase 1 (static IP known post-deploy) |

### Next step

Spec is approved. Write the Phase 1 implementation plan (IaC foundation).
