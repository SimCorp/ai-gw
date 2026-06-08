# AI Gateway — Azure Enterprise Deployment Design

**Date:** 2026-06-08
**Status:** Draft — awaiting review
**Scope:** Enterprise deployment of ai-gw to Azure using SC LZ PlatformAITooling Dev subscription
**Related:** [Original gateway design](2026-05-05-ai-gateway-design.md)

---

## Overview

Deploy the AI Gateway stack to Azure, replacing the local Docker Compose setup with a production-grade AKS-hosted deployment. This spec covers the first environment (Dev) in a phased rollout toward Production.

The original design spec already names the required Azure services. This doc defines **how to get there**: IaC, networking, container pipeline, Kubernetes workloads, secrets management, deployment pipeline, and monitoring wiring.

**Not in scope:** feature changes to the gateway services themselves; Production environment (a follow-on spec once Dev is stable); multi-region.

---

## Landing Zone Context

`SC LZ PlatformAITooling Dev` is a SimCorp Azure Landing Zone subscription for the Platform AI Tooling workload in the Dev environment. Landing Zones typically provide subscription-level guardrails — policies, networking foundations, RBAC defaults, and naming standards.

**These are blocking inputs required before Phase 1 begins.** Most need a conversation with the SC Platform team.

> **ALZ pattern note:** Enterprise Azure Landing Zones are a *vending* pattern — the platform team typically provides the subscription with networking, DNS, Log Analytics, and Azure Policy already in place and locked. The defaults below assume the LZ provides these foundations; we build application-layer resources on top. This is the opposite of a greenfield deployment.

| Question | **Likely LZ provides** | What we add | Verify with |
|---|---|---|---|
| Spoke VNet | **Yes** — LZ vends spoke VNet with assigned IPAM range | Subnets within the vended VNet | SC Platform team |
| Private DNS zones (`privatelink.*`) | **Yes** — centrally managed via DeployIfNotExists policy. Creating our own will conflict. | Nothing — reference the central zones | SC Platform team ⚠️ |
| Log Analytics Workspace | **Likely yes** — centralized per LZ tier | App Insights only (references existing workspace) | SC Platform team |
| Naming convention | **Yes** — LZ enforces via policy | Apply convention to all resources | SC Platform team |
| Azure Policy list | **Yes** — subscription has guardrails | Validate all resources against policy before `apply` | SC Platform team |
| Shared ACR | **Maybe** — depends on LZ tier | If not shared, we create one | SC Platform team |
| Allowed Azure regions | **Yes** — policy-enforced | Use the allowed region(s) only | SC Platform team / Azure Policy |
| Bicep vs Terraform | **Unclear** — ALZ ships Bicep; SimCorp may mandate it | IaC module decomposition is tool-agnostic (see below) | SC Platform team |
| GitHub Actions OIDC federated credential | **Not yet** — we register it | New Entra ID App Registration | Benjamin / Entra ID admin |
| Subscription ID | **Unknown** | Required for Terraform backend + provider | Benjamin |
| Target FQDN for Dev gateway | **Unknown** | Required for ingress + TLS | Benjamin |

---

## Target Architecture

### Azure Resources

| Resource | Azure Service | Dev SKU | Notes |
|---|---|---|---|
| Kubernetes cluster | Azure Kubernetes Service | Standard tier | System pool × 3, user pool × 2–5 (autoscale) |
| Database | Azure Database for PostgreSQL Flexible Server | Burstable B2ms | Two databases: `aigateway` + `litellm` |
| Cache | Azure Cache for Redis | Premium P1 | RediSearch module required for semantic cache |
| Container registry | Azure Container Registry | Standard | `acrpush` role for GitHub Actions SP |
| Secrets | Azure Key Vault | Standard | CSI driver mounts secrets as env vars |
| Message bus | Azure Service Bus | Standard namespace | One queue: `observability-events` |
| Observability | Azure Monitor + Application Insights | Workspace-based | One App Insights per environment |
| Networking | Azure Virtual Network | /22 address space | Four subnets (below) |
| Identity | Azure Entra ID (existing) | — | Existing tenant; new app registrations per service where needed |

### Networking Design

```
Hub VNet (managed by SC Platform team)
  └── Spoke VNet: dev-vnet-weu  10.x.0.0/22
        ├── aks-system-subnet    10.x.0.0/24   ← system node pool
        ├── aks-user-subnet      10.x.1.0/24   ← user node pool
        ├── aks-pods-subnet      10.x.2.0/23   ← Azure CNI Overlay pod CIDR
        └── pe-subnet            10.x.4.0/27   ← Private Endpoints for all PaaS
```

- **Pod networking:** Azure CNI Overlay — nodes and pods in separate CIDRs, no IP exhaustion risk
- **PaaS access:** All Redis, PostgreSQL, Key Vault, Service Bus accessed via **Private Endpoints** in `pe-subnet`. No public access enabled on any PaaS service.
- **Ingress:** NGINX Ingress Controller on AKS, backed by an Azure Load Balancer. Dev: public IP with TLS (Let's Encrypt via cert-manager). Prod: swap to Application Gateway + WAF.
- **DNS:** Private DNS zones (`privatelink.postgres.database.azure.com`, etc.) are **almost certainly centrally managed** by the LZ via a `DeployIfNotExists` policy. We must reference these zones rather than create our own — creating duplicate zones in the subscription will cause resolution failures or policy denials. Verify with the platform team before writing any `azurerm_private_dns_zone` resources.

### AKS Cluster Design

- **Kubernetes version:** 1.30 (latest stable)
- **Node pools:**
  - `system`: 3 × Standard_D4s_v5, `CriticalAddonsOnly=true:NoSchedule` taint
  - `user`: 2–5 × Standard_D8s_v5, autoscale enabled, spot instances optional for Dev cost savings
- **Identity:** System-assigned Managed Identity for the cluster; **Workload Identity** enabled for per-pod Key Vault access (replaces pod-identity v1)
- **Add-ons:** NGINX ingress (Helm), cert-manager (Helm), Azure Key Vault CSI Driver (add-on), Container Insights (add-on), Entra ID RBAC
- **Container Insights:** sends logs + metrics to the Log Analytics Workspace

---

## IaC Strategy

### Tool Choice — Pending Confirmation

Two realistic options; the module decomposition is identical for both:

| Option | Pros | Cons |
|---|---|---|
| **Terraform** (recommended) | Widest enterprise adoption, excellent `azurerm` provider, Azure Blob Storage state backend | Requires state management; may feel foreign to ALZ-native teams |
| **Bicep** | Microsoft-native, no state file, best alignment with ALZ-vended templates — likely what the platform team uses | Azure-only; less portable |

**Recommendation: Terraform** — but this is a coin-flip until Open Question #7 (Bicep mandate?) is answered by the platform team. If Bicep is mandated, the module structure below translates directly.

> ⚠️ **Do not proceed to implementation on Phase 1 until the IaC tool is confirmed.** The internal details (state backend, provider config) differ, but the module decomposition stays the same regardless.

### Module Decomposition (tool-agnostic)

```
infra/iac/
├── environments/
│   └── dev/
│       └── main.*            # provider config, module calls, variable values
└── modules/
    ├── networking/           # subnets within LZ-vended VNet; private endpoints; references to central DNS zones
    ├── aks/                  # cluster, node pools, workload identity, add-ons
    ├── postgres/             # Flexible Server, databases, private endpoint
    ├── redis/                # Premium P1, RediSearch, private endpoint
    ├── key-vault/            # vault, access policies, initial secrets
    ├── acr/                  # registry, role assignments (skip if LZ provides shared ACR)
    ├── service-bus/          # namespace, queue
    └── monitoring/           # App Insights (references LZ Log Analytics workspace if shared)
```

**Secrets written by IaC, not echoed as outputs.** The `key-vault` module accepts a `secrets` map and writes each as a Key Vault secret. Connection strings never appear in IaC output or CI logs.

### Key Vault Secrets Provisioned by Terraform

| Secret name | Value source | Consumer(s) |
|---|---|---|
| `postgres-url` | Terraform PostgreSQL resource | auth, admin, observability, identity, league, librarian, memory |
| `redis-url` | Terraform Redis resource | auth, cache |
| `service-bus-conn` | Terraform Service Bus resource | observability (producer), workflow-worker |
| `app-insights-conn` | Terraform App Insights resource | all services |
| `agent-relay-secret` | `random_password` resource | agent-relay, workflow-worker |
| `admin-internal-token` | `random_password` resource | workflow-worker, admin |
| `identity-key-secret` | `random_password` resource | identity |
| `identity-service-token` | `random_password` resource | identity |
| `librarian-service-token` | `random_password` resource | librarian |

---

## Container Pipeline

### Current State

CI builds four services (`auth`, `cache`, `admin-api`, `observability`) and pushes to GHCR. Eight services are missing from the matrix, and the registry is wrong for AKS.

### Required Changes

**Expand the CI matrix** to cover all 12 Python services:

```
auth, cache, admin-api, observability,
identity, agent-relay, librarian, memory,
league, scanner, workflow-worker, litellm
```

(Frontend apps `admin-portal` and `portal` are excluded — the existing CLAUDE.md comment explains why: pnpm monorepo Dockerfiles need a separate containerisation effort.)

**Add `acr-push` job** to `ci.yml`:

1. Authenticates to Azure via GitHub OIDC + Federated Credential (no stored secrets)
2. Tags images: `<acr>.azurecr.io/<name>:sha-<sha>` and `<acr>.azurecr.io/<name>:dev-latest`
3. Pushes to ACR using `docker buildx`
4. Runs only on `push` events to `master`, after all test jobs pass

The existing GHCR push job can remain in parallel — useful for open-source visibility and as a fallback.

### OIDC Federated Credential Setup

One Entra ID App Registration (`ai-gw-github-actions`) with a Federated Credential scoped to:
- `repo: <org>/ai-gw`
- `ref: refs/heads/master`

Role assignments:
- `AcrPush` on the ACR resource (for image push)
- `Azure Kubernetes Service Cluster User` + namespace `edit` on AKS (for deploy job)

---

## Kubernetes Workload Design

### Helm Chart Structure

```
infra/helm/
└── ai-gateway/
    ├── Chart.yaml
    ├── values.yaml           # defaults (image registry, replicas, resource limits)
    ├── values.dev.yaml       # dev overrides (smaller replicas, relaxed limits)
    └── templates/
        ├── _helpers.tpl      # name helpers, labels
        ├── configmap.yaml    # shared non-secret config (e.g. LOG_LEVEL, ENV)
        ├── ingress.yaml      # NGINX ingress rules for all services
        ├── auth/             # Deployment, Service, HPA, SecretProviderClass
        ├── cache/
        ├── litellm/
        ├── observability/
        ├── admin/
        ├── identity/
        ├── agent-relay/
        ├── librarian/
        ├── memory/
        ├── league/
        ├── scanner/
        ├── workflow-worker/
        ├── admin-portal/
        └── portal/
```

Every service template includes:
- `Deployment` with rolling update, `readinessProbe` (HTTP `/health`), `livenessProbe`
- `Service` (ClusterIP — internal only; ingress-exposed services also get an `Ingress` rule)
- `HorizontalPodAutoscaler`: min 1, max 3 (Dev); min 2, max 10 (Prod)
- Resource requests/limits sized for Dev (e.g. `requests: cpu: 100m, memory: 256Mi`)
- `ServiceAccount` annotated with Workload Identity client ID

### Secrets Management — Key Vault CSI Driver

All secrets originate from Key Vault via the CSI driver. No human or CI process writes `Secret` objects directly.

Each service has a `SecretProviderClass` that references the Key Vault and lists its secrets. The `secretObjects` stanza in the class causes the CSI driver to sync the values into a K8s `Secret` — this synced Secret exists in-cluster, but it is created and owned by the CSI driver (deleted automatically when no pods reference it). The pod consumes it via `envFrom`. This is the standard pattern for surfacing Key Vault secrets as environment variables on AKS with Workload Identity.

```yaml
# Example for auth service
apiVersion: secrets-store.csi.x-k8s.io/v1
kind: SecretProviderClass
metadata:
  name: auth-secrets
spec:
  provider: azure
  parameters:
    usePodIdentity: "false"
    clientID: "<auth-workload-identity-client-id>"
    keyvaultName: dev-kv-weu
    objects: |
      - objectName: postgres-url
        objectType: secret
      - objectName: app-insights-conn
        objectType: secret
  secretObjects:
    - secretName: auth-secrets
      type: Opaque
      data:
        - objectName: postgres-url
          key: DATABASE_URL
        - objectName: app-insights-conn
          key: APPLICATIONINSIGHTS_CONNECTION_STRING
```

### Ingress Routing

Mirrors the local nginx config exactly, preserving existing URL paths:

```
/auth/*           → auth:8001
/cache/*          → cache:8002
/litellm/*        → litellm:8003
/observability/*  → observability:8004
/admin/*          → admin:8005
/identity/*       → identity:8006
/agent-relay/*    → agent-relay:8007
/librarian/*      → librarian:8008
/memory/*         → memory:8009
/league/*         → league:8010
/admin-portal/*   → admin-portal:3001
/portal/*         → portal:3002
```

TLS: cert-manager `ClusterIssuer` with Let's Encrypt (HTTP-01 challenge). Target FQDN: `dev-aigw.simcorp.internal` or similar — **to be confirmed with the platform team** (see Open Questions).

---

## CI/CD Deployment Pipeline

### New Workflow: `deploy.yml`

Triggered by `workflow_run` on `ci.yml` completing successfully on `master`.

```
jobs:
  push-to-acr          # build + tag + push all 12 services to ACR
    needs: (ci.yml passed)

  deploy-dev           # helm upgrade --install on AKS dev namespace
    needs: push-to-acr
    steps:
      - azure/login (OIDC)
      - azure/aks-set-context
      - helm upgrade --install ai-gateway infra/helm/ai-gateway \
          -f values.dev.yaml \
          --set image.tag=sha-${{ github.sha }} \
          --namespace ai-gateway \
          --create-namespace \
          --wait

  smoke-test           # HTTP health checks against ingress
    needs: deploy-dev
    steps:
      - curl /auth/health, /cache/health, /admin/health, ... (all 12)
      - fail loudly if any 5xx
```

**Rollback:** `helm rollback ai-gateway` — instant, no re-deploy needed.

---

## Monitoring

- **Application Insights** (workspace-based, connected to the Log Analytics Workspace)
- Each service gets `APPLICATIONINSIGHTS_CONNECTION_STRING` via Key Vault CSI
- Python services: `azure-monitor-opentelemetry` auto-instrumentation via `configure_azure_monitor()` at startup
- The existing observability service's Postgres cost tables feed the admin portal dashboards (unchanged)

### Alerts (defined in Terraform `monitoring` module)

| Alert | Threshold | Action |
|---|---|---|
| Gateway p99 latency | > 500ms for 5 min | Teams webhook notification |
| Error rate | > 5% of requests over 5 min | Teams webhook notification |
| Redis eviction | Any evictions | Warning notification |
| PostgreSQL CPU | > 80% for 5 min | Warning notification |
| Pod restart loop | CrashLoopBackOff > 3 restarts | Alert |

---

## Implementation Phases

### Phase 1 — IaC Foundation

Provision all Azure resources with Terraform. No app deployed yet. All PaaS is private-endpoint-only.

Deliverables:
- `infra/terraform/` module structure
- `environments/dev/terraform.tfvars` with non-secret values
- Terraform plan reviewed by platform team before `apply`
- All secrets written to Key Vault by `terraform apply`
- Verification: `az aks get-credentials` works; `kubectl get nodes` returns healthy nodes

### Phase 2 — Container Pipeline

Expand CI matrix and add ACR push.

Deliverables:
- All 12 services in `ci.yml` matrix
- `acr-push` job with OIDC auth
- Entra ID App Registration + Federated Credential documented in ops runbook
- Verification: all 12 images appear in ACR after a `master` push

### Phase 3 — Helm Charts

Write all Helm templates, test locally.

Deliverables:
- `infra/helm/ai-gateway/` with all service templates
- `SecretProviderClass` per service
- `helm lint` passes; `helm template` renders without errors
- Dry-run against Dev AKS: `helm upgrade --dry-run`

### Phase 4 — Deployment Pipeline

Wire `deploy.yml` and validate end-to-end.

Deliverables:
- `deploy.yml` workflow
- First successful deploy to Dev AKS
- All `/health` endpoints return 200 through the ingress
- TLS certificate issued by cert-manager

### Phase 5 — Smoke Test and Handoff

End-to-end functional validation.

Deliverables:
- Register a team via admin portal
- Issue an API key
- Make a chat completion call through the gateway (pointing at a test/mock provider)
- Verify: cache hit on second identical call, observability event recorded, cost row in Postgres
- Ops runbook updated with AKS-specific runbook entries

---

## Open Questions

**Phase 1 planning is blocked until the starred (⭐) questions are answered.** The non-starred items can be deferred to their respective phases.

| # | Question | Default in this spec | Who resolves | Blocks |
|---|---|---|---|---|
| 1 ⭐ | Spoke VNet — LZ-vended or we create? | LZ provides it | SC Platform team | Phase 1 |
| 2 ⭐ | Are private DNS zones (`privatelink.*`) centrally managed by LZ policy? | Yes — must not create our own | SC Platform team | Phase 1 |
| 3 ⭐ | Log Analytics Workspace — shared or per-workload? | LZ provides shared one | SC Platform team | Phase 1 |
| 4 ⭐ | Resource naming convention? | `dev-<component>-weu` | SC Platform team | Phase 1 |
| 5 ⭐ | Allowed Azure regions? | `westeurope` | SC Platform team / Azure Policy | Phase 1 |
| 6 ⭐ | Azure Policy list for this subscription? | No public IPs; required tags | SC Platform team | Phase 1 |
| 7 ⭐ | IaC tool — Bicep mandated or Terraform OK? | Terraform (pending) | SC Platform team | Phase 1 |
| 8 ⭐ | Subscription ID? | Unknown | Benjamin | Phase 1 |
| 9 ⭐ | Shared ACR or per-workload? | Per-workload | SC Platform team | Phase 2 |
| 10 | Target FQDN for Dev gateway? | `dev-aigw.simcorp.internal` | Benjamin | Phase 4 |
| 11 | TLS strategy — Let's Encrypt or enterprise cert? | Let's Encrypt (cert-manager) | Benjamin | Phase 4 |
| 12 | GitHub Actions OIDC Federated Credential already registered? | Not yet | Benjamin / Entra ID admin | Phase 2 |
| 13 | AKS node VM size / spot instances for Dev cost savings? | Standard_D8s_v5, no spot | Benjamin | Phase 1 |

### Next step

Once questions 1–8 are answered, scope and write an implementation plan for **Phase 1 only** (IaC foundation). Each phase is a separate plan → implement cycle.
