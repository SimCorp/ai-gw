# AI Gateway — Multi-AZ HA Hardening Design (Spec 1)

**Date:** 2026-06-12
**Status:** Draft — pending user review
**Scope:** Make the single-region Azure deployment of the ai-gw resilient to an availability-zone failure, with one identical HA topology across Dev, Test, and (future) Prod.
**Related:** [Azure Enterprise Deployment](2026-06-08-azure-enterprise-deployment-design.md) · [Original gateway design](2026-05-05-ai-gateway-design.md)

This is the first of three planned specs from the resilience brainstorming:

1. **Spec 1 — Multi-AZ HA hardening (this document).** Infrastructure/config; closes the single-points-of-failure.
2. **Spec 2 — Zero-downtime delivery + connection resilience.** Health-gated blue-green CD, readiness/drain, leader election for in-process schedulers (unlocks `minReplicas: 2` for admin/observability/librarian), agent-relay reconnect/resume, durable scanner queue.
3. **Spec 3 — Native-Azure inference modernization.** Azure OpenAI / AI Foundry load-balancing; APIM evaluation (deferred).

---

## 1. Overview

**Goal:** survive the loss of one Azure availability zone in Sweden Central with no data loss and only brief, self-healing interruption (clients retry/reconnect), by putting the ACA environment, the request-path apps, and the stateful PaaS onto zone-redundant configurations — deployed as one parameterized topology shared by all environments.

**Approach:** mostly Bicep configuration. Make the Container Apps environment zone-redundant; give request-path apps ≥2 replicas so ACA spreads them across zones; move PostgreSQL to a tier that supports zone-redundant HA; enable zone redundancy on Redis; move job-I/O storage to ZRS. Lift hardcoded SKUs and replica counts into parameters so Dev/Test/Prod deploy the same topology and differ only in compute sizing.

**Target SLO:** ~99.99% for the request path (the ACA + zone-redundant PaaS composite). Bounded by the services that stay single-zone in Spec 1 — `admin`, `observability`, `librarian` (in-process schedulers) and `agent-relay` (in-memory connections) — all lifted to multi-zone in Spec 2 (see §6).

### Decisions locked during brainstorming

| Decision | Choice |
|---|---|
| Target | Production-grade topology applied to all environments; Dev=dev, Test=test; **single region** (Sweden Central) for now |
| Resilience tier | **Single-region multi-AZ** (no multi-region/DR in this spec) |
| Model hosting | Broker to external + Azure OpenAI / AI Foundry APIs (no self-hosted GPUs) → **stay on Container Apps** |
| Cost lean | **Balanced**: HA the request path + stateful data; tolerate single-instance for background/stateful-singleton services |
| Redis | **Enable zone redundancy in place on existing Premium**; track Azure Managed Redis migration as a separate later item |
| Environment parity | **Full parity** — HA enabled in all three envs; the only per-env lever is compute SKU size |
| Compute platform | Azure Container Apps (ACA), not AKS |

---

## 2. Verified platform facts (these drive the design)

| Fact | Source-confirmed behavior | Design consequence |
|---|---|---|
| ACA zone redundancy is **creation-time only** | "You can't enable zone redundancy on an existing Container Apps environment… create a new environment… then redeploy." | The existing `cae-aigw-dev-sdc` must be **recreated**; new static IP → re-point DNS; redeploy all apps. |
| ACA needs **≥2 min replicas** to spread across zones | "Set your minimum replica count to at least two to ensure distribution across multiple availability zones." | Request-path apps get `minReplicas: 2`. |
| ACA workload-profile env needs **/27 subnet or larger** | Workload-profile envs require `/27`+. `snet-aca-infra` is `/27` (32 IPs). | Adequate; no subnet change. |
| ACA zone redundancy is **free** | "You don't incur extra charges… when you enable zone redundancy." | Cost comes from replicas/PaaS, not the flag. |
| Postgres **Burstable cannot do HA** | "The Burstable tier doesn't support high availability. Only General Purpose and Memory Optimized." | Must upgrade `Standard_B2ms` → General Purpose. Main cost increase. |
| Postgres HA enable is an **online** op; tier change is an in-place scale (restart) | "Enabling or disabling high availability is an online operation." Tier change resizes compute. | No new server; one brief restart during the tier change. |
| Postgres ZoneRedundant gives **zero-data-loss, ~60–120s auto-failover, 99.99%** | Synchronous standby in another zone. | Meets the SLO for the DB tier. |
| Redis **Premium zone redundancy can be enabled in place** | "Updating an existing Standard or Premium cache to use zone redundancy is supported in-place" via Automatic Zonal Allocation; **not** supported only for VNet-injected caches. We use a Private Endpoint (not VNet injection). | No recreate; update via `2024-11-01`+ API. |
| Service Bus Premium is **zone-redundant automatically** | "Zone redundancy is automatically enabled when you create a namespace in a supported region"; the `zoneRedundant` property is **deprecated** and may read `false`. | **No change.** Earlier audit flagged this incorrectly. |
| Key Vault Standard is **zone-redundant automatically** in AZ regions | Regional zone redundancy is built in. | **No change.** |
| Azure Cache for Redis is **retiring** (Premium Sept 2028) | MS recommends Azure Managed Redis. | Zone-redundant Premium now; **track migration** (out of scope here). |

---

## 3. Target architecture

```
Sweden Central (3 availability zones)
  Zone-redundant ACA environment  cae-aigw-<env>-sdc  (zoneRedundant: true)
    multi-replica  minReplicas: 2  → replicas spread across zones automatically
      gateway · cache · auth · litellm · identity · memory · league · admin-portal · portal
      scanner (background, safe as competing consumers on the Redis queue)
    single-zone (bridged by Spec 2)  minReplicas: 1
      admin · observability · librarian (in-process schedulers — double-fire at 2 without leader election)
      agent-relay (in-memory connection state) · workflow-worker (singleton) · toolbox (jumpbox)
  PostgreSQL Flexible Server   General Purpose D2ds_v5, highAvailability: ZoneRedundant  (sync standby in 2nd zone)
  Azure Cache for Redis        Premium P1, automatic zonal allocation + replica (+ optional RDB persistence)
  Storage (job I/O)            Standard_ZRS
  Service Bus Premium          zone-redundant automatically (no change)
  Key Vault Standard           zone-redundant automatically (no change)
```

Behavior on a zone failure: ACA stops scheduling to the dead zone, reroutes traffic to healthy-zone replicas in ~30s; in-flight requests to the dead zone may drop and clients retry. Postgres auto-fails to its standby (60–120s, no data loss). Redis fails over to its replica in a healthy zone (~10–15s). Service Bus reroutes transparently. `agent-relay` connections in the dead zone are lost with no reconnect until Spec 2.

---

## 4. Component changes (current → target)

### 4.1 ACA environment — `modules/containerEnv.bicep`

Add zone redundancy to the environment properties:

```bicep
properties: {
  zoneRedundant: true            // NEW — creation-time only
  vnetConfiguration: {
    internal: true
    infrastructureSubnetId: infrastructureSubnetId
  }
  appLogsConfiguration: { ... }  // unchanged
  workloadProfiles: [ { name: 'Consumption', workloadProfileType: 'Consumption' } ]
}
```

Because this is immutable, the existing Dev environment is replaced (see §7 rollout). All `output`s (static IP, default domain) change; the private DNS A record (`aigw-dev.lab.cloud.scdom.net → <static IP>`) must be updated to the new IP.

### 4.2 PostgreSQL — `modules/postgres.bicep`

Parameterize the SKU and HA mode; default to General Purpose + ZoneRedundant:

```bicep
param skuName string = 'Standard_D2ds_v5'      // smallest General Purpose
param skuTier string = 'GeneralPurpose'
param haMode string = 'ZoneRedundant'          // 'SameZone' fallback only if a region lacks AZ capacity

sku: { name: skuName, tier: skuTier }
properties: {
  ...
  highAvailability: { mode: haMode }           // was: 'Disabled'
}
```

`azure.extensions` (`pgcrypto,vector`), both databases (`aigateway`, `litellm`), backup (7 days), and the private endpoint are unchanged. pgvector data is preserved across the tier change. **Billing note:** v5-tier HA bills primary + standby (2×).

**Implementer note (ordering):** HA cannot be enabled on Burstable, so on the *existing* Dev server the tier change to General Purpose must complete *before* HA is enabled — a single Bicep pass that sets both may be rejected. The plan should sequence it as two steps (resize to GP, then enable HA) or recreate the Dev server already on GP. New Test/Prod servers are created GP-with-HA in one pass.

### 4.3 Redis — `modules/redis.bicep`

Bump the API version and enable automatic zonal allocation with a replica (in-place update, no recreate):

```bicep
resource redisCache 'Microsoft.Cache/redis@2024-11-01' = {
  ...
  properties: {
    sku: { name: 'Premium', family: 'P', capacity: 1 }
    replicasPerPrimary: 1
    zonalAllocationPolicy: 'Automatic'     // NEW — spreads primary+replica across zones
    ...
    redisConfiguration: {
      'maxmemory-policy': 'allkeys-lru'
      // RDB persistence (optional, recommended) requires a storage account + connection string:
      // 'rdb-backup-enabled': 'true'
      // 'rdb-backup-frequency': '60'
      // 'rdb-storage-connection-string': <secure>
    }
  }
}
```

> **Implementer check:** confirm `zonalAllocationPolicy` / `replicasPerPrimary` property names against the live `2024-11-01`+ resource schema before applying. RDB persistence is split out as a separable sub-task (it pulls in a storage-account dependency); the zone-redundancy + replica is the HA win.

### 4.4 Storage — `modules/storage.bicep`

```bicep
param storageSku string = 'Standard_ZRS'   // was Standard_LRS
sku: { name: storageSku }
```

The account holds only ephemeral job-exchange files (`inputs.json`/`outputs.json`), so the existing Dev account can be deleted and redeployed as ZRS with no data concern (see §7).

### 4.5 Container Apps — `modules/containerApps.bicep`

Replace the hardcoded `scale: { minReplicas: 1, maxReplicas: 2 }` blocks with parameters. Two tiers:

```bicep
param minReplicasMulti int = 2    // services safe to run 2+ replicas (zone-spread)
param maxReplicasMulti int = 4
param minReplicasSingle int = 1   // services NOT multi-replica-safe (see §6)
```

- `minReplicasMulti` (2) — stateless or competing-consumer apps, safe to zone-spread: gateway, cache, auth, litellm, identity, memory, league, admin-portal, portal, and `scanner` (background, but safe as competing consumers on its Redis queue).
- `minReplicasSingle` (1) — **not** multi-replica-safe in Spec 1 (see §6): admin, observability, librarian (in-process schedulers that would double-fire), agent-relay (in-memory connections), workflow-worker (singleton), toolbox (jumpbox).

`cache`'s in-memory `_identity_cache` is a soft per-replica cache, so two replicas stay correctness-safe (each just warms its own). Container CPU/memory stay at the existing `stdResources`/`lgResources` (minor cost vs the PaaS SKUs). Readiness/liveness probes are deferred to Spec 2; ACA's default probes suffice for 2-replica routing in the meantime.

### 4.6 No change (documented)

- **Service Bus** (`modules/serviceBus.bicep`) — already zone-redundant; do not add a `zoneRedundant` property (deprecated). Add a one-line comment recording this.
- **Key Vault** (`modules/keyVault.bicep`) — already zone-redundant.
- **ACR** (`modules/acr.bicep`) — Premium; zone redundancy is low value while images are pulled from GHCR. Leave for the future ACR cutover; not in this spec.

---

## 5. Environment parity (parameterization)

The HA topology is identical across environments; only compute size differs. Lift the following into `main.bicep` params, surfaced in each `main.bicepparam`:

| Parameter | Dev | Test | Prod | Notes |
|---|---|---|---|---|
| `postgresSkuName` / `postgresSkuTier` | `Standard_D2ds_v5` / `GeneralPurpose` | same | `Standard_D4ds_v5` / `GeneralPurpose` | per-env compute lever |
| `postgresHaMode` | `ZoneRedundant` | `ZoneRedundant` | `ZoneRedundant` | parity: HA on everywhere |
| `redisCapacity` | `1` (P1) | `1` | `2` (P2) | per-env compute lever |
| `storageSku` | `Standard_ZRS` | `Standard_ZRS` | `Standard_ZRS` | |
| `minReplicasMulti` | `2` | `2` | `2` | parity: zone spread everywhere |

`infra/bicep/environments/test/` and `prod/` each get a `main.bicep` (identical to `dev/`) and a `main.bicepparam`. Test reuses the existing PlatformAITooling Test subscription; the Prod param file is provided ready-to-use even if the Prod subscription is provisioned later.

> Parity means **HA is never disabled per-env** — the cost lever is the SKU size, not the HA flag. Confirmed during brainstorming.

---

## 6. Services that stay single-zone in Spec 1 (Spec 1 → Spec 2 bridge)

Three classes of service are **not** safe at `minReplicas: 2` today, so they stay at 1 and gain zone protection only in Spec 2. Spec 1 documents the gap rather than papering over it; §1's SLO caveat names them.

**(a) In-process schedulers/timers — double-fire at 2 replicas.** None guards its scheduled work with a distributed lock or leader election, so a second replica re-runs every timer:
- **admin** — APScheduler cron (`weekly_digest`, `workday_sync`, `auto_confirm_asks`), `optimization_worker`, and the Copilot catalog sync loop. Double-firing means duplicate digests and a second hit to the Workday API — a correctness regression, not just cost. admin is also semi-request-path (auth, league, identity, librarian, memory, and workflow-worker call `ADMIN_URL`; it serves `/admin/*` and `/auth/*`), so keeping it single-zone bounds the request-path SLO.
- **observability** — its Service Bus *queue consumer* is multi-replica-safe (competing consumers), but its three timer loops (`budget_alert` 300s, `cost_anomaly` 600s, `session_cleanup` 3600s) would double-fire duplicate budget/anomaly webhooks.
- **librarian** — `_research_loop` would double-poll; idempotent `ON CONFLICT` upserts keep it correct, but it doubles research LLM spend.

**(b) In-memory connection state.** **agent-relay** keeps WebSocket connections, the agent registry, and pending invocations in process memory (`_connections`, `_registered_agents`, `_pending`, `_slug_to_token`) with no drain and no reconnect — two replicas would split the registry and misroute invocations.

**(c) Singletons.** **workflow-worker** (Postgres `work_queue` + claim/sweeper) tolerates restart but runs single-replica; **toolbox** is the jumpbox.

**Spec 2 closes (a) and (b):** add Redis/Postgres leader election (a `SET NX` lease or advisory lock) so only one replica runs the scheduled loops — then admin, observability, librarian move to `minReplicas: 2`; and move agent-relay's connection/session state to Redis with reconnect/resume. After Spec 2, only the deliberate singletons remain at 1.

(`identity` runs only an idempotent startup seed — no recurring timer — so it is safe at 2 and lives in the multi-replica group.)

---

## 7. Rollout procedure

Order matters because the ACA env recreate is the disruptive step.

1. **PaaS first (in-place, low risk):**
   - Postgres: deploy GP `D2ds_v5` + `ZoneRedundant` HA (in-place scale + HA enable; one brief restart). Verify HA `Healthy`.
   - Redis: deploy `zonalAllocationPolicy: Automatic` + replica (in-place update). Verify zonal allocation.
2. **Storage:** delete the existing `staigwruns<env>sdc` account (ephemeral data) and redeploy as `Standard_ZRS`. (No running job during the window.)
3. **ACA environment recreate (the disruptive step):**
   - Deploy the new zone-redundant environment (Bicep with `zoneRedundant: true`). For Dev, this replaces `cae-aigw-dev-sdc`; brief downtime is acceptable.
   - Redeploy all Container Apps + the gateway + jobs into the new environment.
   - Capture the new static IP; **update the private DNS A record** `aigw-<env>.lab.cloud.scdom.net → <new static IP>` (in `rg-spoke-platformaitooling-<env>-sdc-001`).
   - If the hub firewall pins the old ACA static IP, request the platform team update it.
4. **Container Apps:** confirm `minReplicas: 2` on request-path apps; verify replicas land in ≥2 zones.
5. **Test environment:** repeat via `environments/test/main.bicepparam`.

**Rollback:** PaaS changes (Postgres tier/HA, Redis zones) are reversible in place. The ACA env recreate is the only one-way step within a run; keep the prior env until the new one passes smoke tests, then delete.

---

## 8. Cost impact (rough monthly estimate, per environment — verify in the Azure pricing calculator)

| Item | Before | After | Delta |
|---|---|---|---|
| PostgreSQL | Burstable B2ms (~$70) | GP D2ds_v5 + ZR HA (~2× → ~$520) | **+~$450** |
| Redis | Premium P1 (~$410) | Premium P1 + AZ (replica already in Premium; + cross-AZ egress) | ~flat, small |
| Container Apps | min 1 | min 2 on request path (extra vCPU-seconds) | low tens |
| Storage | LRS (tiny) | ZRS (tiny) | negligible |

Dominant driver is Postgres GP+HA, roughly **+$450/env/month**, i.e. ~+$900/month across Dev+Test. Prod adds its own when provisioned. Zone redundancy itself (ACA, Service Bus, Key Vault) is free.

---

## 9. Verification (acceptance criteria)

- `az containerapp env show -n cae-aigw-<env>-sdc -g rg-aigw-<env>-sdc --query properties.zoneRedundant` → `true`.
- `az postgres flexible-server show … --query "highAvailability.{mode:mode,state:state}"` → `mode: ZoneRedundant`, `state: Healthy`; primary and standby in different zones.
- `az redis show … --query "{zones:zones,replicas:replicasPerPrimary}"` → replica present and zones populated (or zonal allocation = Automatic confirmed).
- Request-path apps report replicas across ≥2 zones (`az containerapp replica list`).
- Storage account `sku.name` = `Standard_ZRS`.
- `https://aigw-<env>.lab.cloud.scdom.net/healthz` returns 200 after the DNS re-point.
- A forced Postgres failover (`az postgres flexible-server restart --failover Forced`) completes; the gateway recovers within the app's retry window.

---

## 10. Out of scope (and why)

- **Zero-downtime deploys, readiness/drain, leader election for schedulers (to lift admin/observability/librarian to 2 replicas), agent-relay reconnect, durable scanner queue** → Spec 2.
- **Azure OpenAI / AI Foundry load-balancing, APIM** → Spec 3.
- **Azure Managed Redis migration** — tracked follow-up (Premium retires 2028); not needed for multi-AZ now.
- **Multi-region / DR / geo-replication** — explicitly excluded (single region chosen).
- **Backup-retention / geo-redundant-backup increases** — that's DR, not AZ resilience.
- **ACR zone redundancy + GHCR→ACR cutover** — separate effort; GHCR is the current image source.

---

## 11. Open questions

None blocking. One implementer check noted in §4.3 (confirm Redis zonal-allocation property names against the live schema).
