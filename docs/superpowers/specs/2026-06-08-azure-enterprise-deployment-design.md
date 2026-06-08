# AI Gateway — Azure Enterprise Deployment Design

**Date:** 2026-06-08
**Status:** Draft — DECISION REQUIRED (see §3)
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

### What the LZ provides (confirmed via Azure CLI)

| Resource | What exists | Notes |
|---|---|---|
| Spoke VNet (Dev) | `vnet-spoke-platformaitooling-dev-sdc-001` — `10.179.231.0/25` | VNet-peered to hub; total 128 usable IPs |
| Spoke VNet (Test) | Exists at `10.179.230.128/25` | No subnets yet — infrastructure subnet needed |
| ACA Environment (Dev) | `ca-env-dev-sdc` — Consumption profile, `internal: true` | Already provisioned; VNet-only endpoint |
| Log Analytics Workspace | `law-aca-dev-sdc` | LZ-provided; connect App Insights here |
| Private DNS (centrally managed) | `privatelink.*` zones managed by LZ DeployIfNotExists policy | **Do not create these zones** |
| Private DNS (own zone) | `platformaitooling.local` already exists | Internal service discovery DNS |
| Naming convention | `<type>-<descriptor>-<env>-sdc[-001]` | Examples: `law-aca-dev-sdc`, `ca-env-dev-sdc`, `vnet-spoke-platformaitooling-dev-sdc-001` |
| Azure Policy | AMBA (Azure Monitor Baseline Alerts) deployed in both subscriptions | No blocking compute/networking policies found |

> **ALZ pattern note:** Enterprise Landing Zones are a *vending* pattern — the platform team provides subscription networking, DNS, Log Analytics, and Azure Policy. We build application-layer resources on top. This is the opposite of a greenfield deployment.

### Dev VNet subnet layout (current)

```
vnet-spoke-platformaitooling-dev-sdc-001   10.179.231.0/25   (128 IPs total)
  ├── [ACA infrastructure subnet]   10.179.231.0/26    delegated → Microsoft.App/environments
  └── [free / available]            10.179.231.64/26   64 IPs — available for Private Endpoints
```

**Key constraint:** Both existing subnets are delegated to `Microsoft.App/environments`. AKS cannot use delegated subnets. Application Gateway v2 requires a /24 (256 IPs) — impossible in a /25 VNet.

---

## 3. ⚠️ DECISION REQUIRED: Compute Platform

**Azure CLI inspection revealed the Dev LZ is purpose-built for Azure Container Apps, not AKS.** This changes the architecture significantly. Two paths forward:

---

### Path A — Azure Container Apps (Recommended)

**Use the LZ as designed.** The ACA environment `ca-env-dev-sdc` is already provisioned. All gateway services become Container Apps inside this environment.

| Aspect | Under ACA |
|---|---|
| Cluster management | None — Consumption profile, fully managed |
| Workload definition | One Bicep `containerApp` resource per service (replaces Helm) |
| Secrets | ACA native secret refs to Key Vault (replaces CSI driver + SecretProviderClass) |
| Service-to-service routing | ACA internal ingress (no NGINX, no ingress controller) |
| Scaling | Built-in KEDA-based scale rules per app |
| Networking | Fits current VNet; PE subnet in the free /26 |
| Dev readiness | Start deploying within days — LZ networking already done |

**One open question under Path A:**

The ACA environment is `internal: true` — it has no public endpoint. All ingress is VNet-only. For engineers to reach the Dev gateway they need to be on the VNet (VPN or ExpressRoute). 

> **Question for Benjamin:** Is VNet-only access acceptable for Dev? (Engineers on corp VPN can reach internal LZ services — is that the case here, or do you need a public endpoint for Dev?)

If VNet-only is not acceptable, options are:
- **Azure Front Door + Private Link origin** — possible, adds complexity and Front Door cost
- **Azure API Management (internal mode)** fronted by Front Door — heavier but LZ-aligned
- Ask platform team to set ACA env to `external: true` if their LZ version supports it

---

### Path B — Azure Kubernetes Service (Requires platform team)

Keep the original AKS design but the current VNet cannot support it. AKS requires:
- Non-delegated subnets for node pools
- A much larger CIDR (at minimum /22 for node + pod CIDRs under Azure CNI Overlay)
- A separate /27 for Private Endpoints

This would require the SC Platform team to either re-vend a larger VNet for this subscription or carve out a new AKS-specific spoke VNet. **Expect weeks of platform team coordination before Phase 1 can start.**

---

**The rest of this spec is written for Path A (ACA).** If you choose Path B, the AKS architecture sections from the previous draft remain valid but the networking section must be replaced pending platform team input.

---

## 4. Target Architecture (Path A — Azure Container Apps)

### Azure Resources

| Resource | Azure Service | Dev SKU | Notes |
|---|---|---|---|
| Container compute | Azure Container Apps (existing `ca-env-dev-sdc`) | Consumption | One Container App per service |
| Database | Azure Database for PostgreSQL Flexible Server | Burstable B2ms | Two databases: `aigateway` + `litellm` |
| Cache | Azure Cache for Redis | Premium P1 | RediSearch module required for semantic cache |
| Container registry | Azure Container Registry | Standard | `acrpush` role for GitHub Actions |
| Secrets | Azure Key Vault | Standard | ACA native secret refs — no CSI driver needed |
| Message bus | Azure Service Bus | Standard namespace | One queue: `observability-events` |
| Observability | Azure Monitor + Application Insights | Workspace-based | References `law-aca-dev-sdc` |
| Networking | Existing LZ VNet + free /26 for PEs | — | No new VNet resources |
| Identity | Azure Entra ID (existing tenant) | — | Managed Identity per Container App |

### Networking

```
Hub VNet (SC Platform team, Sweden Central)
  └── Spoke VNet: vnet-spoke-platformaitooling-dev-sdc-001   10.179.231.0/25
        ├── [ACA infra subnet]   10.179.231.0/26    delegated → Microsoft.App/environments  [existing]
        └── snet-pe-aigw-dev-sdc 10.179.231.64/26   Private Endpoints for all PaaS          [new - Bicep]
```

- **PaaS access:** Redis, PostgreSQL, Key Vault, Service Bus all accessed via Private Endpoints in `snet-pe-aigw-dev-sdc`. No public access on any PaaS service.
- **Private DNS zones (`privatelink.*`):** centrally managed by the LZ — reference only, do not create.
- **Internal DNS:** `platformaitooling.local` zone already exists — register gateway service names here if needed.
- **Ingress (Dev):** ACA environment is `internal: true` — VNet-only. Engineers reach it via corp VPN to the hub. *(See Path A note above if public access is required.)*

### Container Apps Service Layout

Each gateway service becomes one Container App with these properties:

| App name | Internal ingress port | External ingress? | Min replicas |
|---|---|---|---|
| `ca-auth-dev-sdc` | 8001 | No (internal only) | 1 |
| `ca-cache-dev-sdc` | 8002 | No | 1 |
| `ca-litellm-dev-sdc` | 8003 | No | 1 |
| `ca-observability-dev-sdc` | 8004 | No | 1 |
| `ca-admin-api-dev-sdc` | 8005 | No | 1 |
| `ca-identity-dev-sdc` | 8006 | No | 1 |
| `ca-agent-relay-dev-sdc` | 8007 | Yes (VNet-internal; WebSocket) | 1 |
| `ca-librarian-dev-sdc` | 8008 | No | 1 |
| `ca-memory-dev-sdc` | 8009 | No | 1 |
| `ca-league-dev-sdc` | 8010 | No | 1 |
| `ca-scanner-dev-sdc` | — | No (background worker) | 1 |
| `ca-workflow-worker-dev-sdc` | — | No (background worker) | 0 (scale-to-zero) |
| `ca-admin-portal-dev-sdc` | 3001 | Yes (VNet-internal) | 1 |
| `ca-portal-dev-sdc` | 3002 | Yes (VNet-internal) | 1 |

The `auth` service is the request-path gateway entry point. With `internal: true` ACA env, its "external" ingress is still VNet-scoped — no public IP is assigned.

### Secrets Management — ACA Native Key Vault References

ACA supports direct Key Vault secret references without the CSI driver. Each Container App declares its secrets as KV references; ACA resolves them at deploy time using the app's Managed Identity.

```bicep
// Example in containerApp.bicep for auth service
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

Each service gets its own Managed Identity with Key Vault `get`+`list` on its secrets only (least privilege).

---

## 5. IaC Strategy

### Tool Choice — Bicep

Bicep is the chosen IaC tool for this deployment.

| | Why Bicep fits here |
|---|---|
| ALZ alignment | The SC Landing Zone ships Bicep modules; we compose with the same toolchain the platform team uses |
| No state file | Bicep deploys via ARM; no state backend to provision or secure |
| Native Azure | First-class Azure resource support; no provider version lag |

**Deployment mode:** `az deployment group create` (resource group scope). CI/CD calls `az deployment` via the OIDC-authenticated service principal.

### Module Structure

```
infra/bicep/
├── environments/
│   ├── dev/
│   │   ├── main.bicep           # orchestration module
│   │   └── main.bicepparam      # dev parameter values (committed; no secrets)
│   └── test/
│       ├── main.bicep           # identical to dev/
│       └── main.bicepparam      # test parameter values
└── modules/
    ├── networking.bicep         # PE subnet; private endpoints; references to LZ DNS zones
    ├── containerApps.bicep      # all Container App definitions + managed identities
    ├── postgres.bicep           # Flexible Server, databases, private endpoint
    ├── redis.bicep              # Premium P1, RediSearch, private endpoint
    ├── keyVault.bicep           # vault, access policies, secrets
    ├── acr.bicep                # registry, role assignments
    ├── serviceBus.bicep         # namespace, queue
    └── monitoring.bicep         # App Insights referencing law-aca-dev-sdc
```

**Secrets written by IaC, not echoed as outputs.** The `key-vault` module accepts a `secrets` map and writes each as a Key Vault secret. Connection strings never appear in IaC output or CI logs.

### Key Vault Secrets Provisioned by Bicep

| Secret name | Value source | Consumer(s) |
|---|---|---|
| `postgres-url` | PostgreSQL resource `listConnectionStrings()` | auth, admin, observability, identity, league, librarian, memory |
| `redis-url` | Redis resource `listKeys()` | auth, cache |
| `service-bus-conn` | Service Bus resource `listKeys()` | observability (producer), workflow-worker |
| `app-insights-conn` | App Insights resource `connectionString` output | all services |
| `agent-relay-secret` | `uniqueString()` seeded from resource group ID | agent-relay, workflow-worker |
| `admin-internal-token` | `uniqueString()` seeded from resource group ID | workflow-worker, admin |
| `identity-key-secret` | `uniqueString()` seeded from resource group ID | identity |
| `identity-service-token` | `uniqueString()` seeded from resource group ID | identity |
| `librarian-service-token` | `uniqueString()` seeded from resource group ID | librarian |

> Note: `uniqueString()` produces deterministic values per deployment, which is desirable for idempotent re-runs. If stronger randomness is needed, generate secrets outside Bicep (e.g. in a pre-deploy CI step) and pass them as `@secure()` parameters.

---

## 6. Container Pipeline

### Current State

CI builds four services (`auth`, `cache`, `admin-api`, `observability`) and pushes to GHCR. Eight services are missing from the matrix, and the registry is wrong for Azure.

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
4. Runs only on `push` events to `master`, after all test jobs pass

### OIDC Federated Credential Setup

One Entra ID App Registration (`ai-gw-github-actions`) with a Federated Credential scoped to:
- `repo: <org>/ai-gw`
- `ref: refs/heads/master`

Role assignments:
- `AcrPush` on the ACR resource (for image push)
- `Contributor` on the `rg-aigw-dev-sdc` resource group (for `az deployment group create`)

---

## 7. CI/CD Deployment Pipeline

### New Workflow: `deploy.yml`

Triggered by `workflow_run` on `ci.yml` completing successfully on `master`.

```
jobs:
  push-to-acr          # build + tag + push all 12 services to ACR
    needs: (ci.yml passed)

  deploy-dev           # az deployment group create (Bicep containerApps module)
    needs: push-to-acr
    steps:
      - azure/login (OIDC)
      - az deployment group create \
          --resource-group rg-aigw-dev-sdc \
          --template-file infra/bicep/modules/containerApps.bicep \
          --parameters infra/bicep/environments/dev/main.bicepparam \
          --parameters imageTag=sha-${{ github.sha }}

  smoke-test           # HTTP health checks via internal DNS or VNet runner
    needs: deploy-dev
    steps:
      - curl /auth/health, /cache/health, /admin/health, ... (all active services)
      - fail loudly if any 5xx
```

> Note: smoke tests require the GitHub Actions runner to be VNet-connected (self-hosted runner in the LZ, or Azure Container Apps Job with VNet integration) because the ACA environment is `internal: true`.

**Rollback:** Re-run the deploy job with the previous `imageTag` value — ACA updates are atomic per revision.

---

## 8. Monitoring

- **Application Insights** (workspace-based, connected to `law-aca-dev-sdc`)
- Each service gets `APPLICATIONINSIGHTS_CONNECTION_STRING` via ACA secret ref
- Python services: `azure-monitor-opentelemetry` auto-instrumentation via `configure_azure_monitor()` at startup
- The existing observability service's Postgres cost tables feed the admin portal dashboards (unchanged)

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
- `environments/dev/main.bicepparam` with non-secret values
- `az deployment group what-if` reviewed before `create`
- All secrets written to Key Vault by the Bicep deployment
- Verification: ACA environment accessible; PostgreSQL and Redis reachable from within VNet

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
- Managed Identity per app with scoped KV access
- `az deployment group what-if` passes clean
- First deploy: all Container Apps running and `/health` endpoints return 200

### Phase 4 — Deployment Pipeline + Test Environment

Wire `deploy.yml` and replicate IaC to Test subscription.

Deliverables:
- `deploy.yml` workflow
- `environments/test/main.bicepparam`
- First successful automated deploy to Dev triggered by `master` push
- Test environment provisioned in `PlatformAITooling Test` subscription

### Phase 5 — Smoke Test and Handoff

End-to-end functional validation.

Deliverables:
- Register a team via admin portal
- Issue an API key
- Make a chat completion call through the gateway (pointing at a test/mock provider)
- Verify: cache hit on second identical call, observability event recorded, cost row in Postgres
- Ops runbook with ACA-specific entries (revision management, log streaming, scaling)

---

## 10. Open Questions

| # | Question | Status | Who resolves |
|---|---|---|---|
| 1 | Spoke VNet — LZ-vended or we create? | **Resolved: LZ provides it** | — |
| 2 | Private DNS zones centrally managed? | **Resolved: Yes — must not create our own** | — |
| 3 | Log Analytics Workspace — shared? | **Resolved: `law-aca-dev-sdc` provided by LZ** | — |
| 4 | Resource naming convention? | **Resolved: `<type>-<descriptor>-<env>-sdc[-001]`** | — |
| 5 | Allowed Azure regions? | **Resolved: Sweden Central (`swedencentral`)** | — |
| 6 | Azure Policy blockers? | **Likely clear — AMBA only, no blocking policies found** | Verify with Platform team |
| 7 | IaC tool? | **Resolved: Bicep** | — |
| 8 | Subscription IDs? | **Resolved: see §1** | — |
| 9 | **Compute platform: ACA or AKS?** | **⭐ REQUIRED — see §3** | Benjamin |
| 10 | **External ingress for Dev?** (ACA env is `internal: true`) | **⭐ REQUIRED — see §3 Path A note** | Benjamin |
| 11 | Shared ACR or per-workload? | Per-workload assumed; confirm with Platform team | SC Platform team |
| 12 | GitHub Actions OIDC Federated Credential registered? | Not yet | Benjamin / Entra ID admin |
| 13 | Self-hosted runner or Azure Container Apps Job for smoke tests? | Needed for VNet-internal smoke tests | Benjamin |

### Next step

Answer questions 9 and 10, then scope and write an implementation plan for **Phase 1 only** (IaC foundation). Each phase is a separate plan → implement cycle.
