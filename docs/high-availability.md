# AI Gateway — High Availability Guide

**Audience:** Platform engineers and architects  
**System:** Enterprise AI Gateway serving ~2,000 SimCorp engineers  
**Last updated:** 2026-06-09

---

## 1. Overview

The AI Gateway is designed for high availability across all critical components. This guide covers:

- Redis Sentinel (HA cache, session store, rate limits)
- Service replica strategy for stateless gateway services
- Rolling upgrades with zero / near-zero downtime
- Database HA (PostgreSQL)
- Minimum-outage practices for each layer

---

## 2. Redis High Availability (Sentinel)

### Why Sentinel?

The semantic cache, session store, rate-limit counters, and circuit-breaker state all live in Redis. Redis availability is therefore on the **critical path** for every AI request. Without HA Redis:

- A Redis restart causes a brief outage for all cache-dependent paths
- Sessions are lost (users must re-authenticate)
- Rate-limit counters reset (burst risk)

Redis Sentinel provides automatic failover with no application restart: when the primary goes down, Sentinel elects a replica as the new primary within seconds.

### Architecture: 1 primary + 1 replica + 3 sentinels

```
redis-master (read/write)
    └── redis-replica (read-only, hot standby)

redis-sentinel-1 ┐
redis-sentinel-2 ├── quorum = 2 (majority of 3)
redis-sentinel-3 ┘
```

**Failover timeline:**
1. `redis-master` becomes unreachable
2. Sentinels detect failure after `down-after-milliseconds` (5 s)
3. Quorum (≥2 of 3 sentinels) agrees — failover begins
4. `redis-replica` is promoted to primary in < 10 s (`failover-timeout`)
5. All services reconnect via Sentinel and resume normal operation

### Enabling Sentinel (Docker Compose)

The sentinel topology is available as a Docker Compose profile:

```bash
# Start everything with Sentinel HA Redis
docker compose -f infra/docker-compose.yml --profile sentinel up -d

# Services must point to Sentinel instead of a direct Redis URL.
# Set in .env or per-service environment:
REDIS_SENTINEL_HOSTS=redis-sentinel-1:26379,redis-sentinel-2:26379,redis-sentinel-3:26379
REDIS_SENTINEL_MASTER=mymaster

# REDIS_URL is ignored when REDIS_SENTINEL_HOSTS is set.
```

**All** gateway services use the same `make_redis()` factory (`app/redis_utils.py`) which automatically switches to Sentinel mode when `REDIS_SENTINEL_HOSTS` is present. Services covered:

| Service | Redis usage |
|---------|-------------|
| auth | Sessions, OIDC state, rate-limit counters |
| cache | Semantic cache entries, circuit-breaker state |
| admin | Admin portal sessions |
| observability | Event queue |
| identity | Agent heartbeats |
| librarian | Embedding cache |
| agent-relay | Agent registration keys |
| league | Rate limiting |
| scanner | Job queue |
| workflow-worker | Run lifecycle events, scoped API keys |

### Sentinel in Production (Azure)

In Azure environments the gateway uses **Azure Cache for Redis (Premium tier)** with zone-redundant replication — no Sentinel configuration is required. The Premium tier provides:

- Automatic failover within the region (< 60 s RPO/RTO SLA)
- RediSearch module (required for semantic cache vector operations)
- Private Endpoint (no public access)

See `docs/superpowers/specs/2026-06-08-azure-enterprise-deployment-design.md` §4 for the Azure resource specification.

---

## 3. Service Replica Strategy

All AI Gateway services are **stateless** — shared state lives exclusively in Redis and PostgreSQL. Any replica can handle any request. This means horizontal scaling requires no additional coordination.

### Critical-path services (min 2 replicas in production)

| Service | Port | Notes |
|---------|------|-------|
| auth | 8001 | Every request validates through here |
| cache | 8002 | Semantic cache is on the hot request path |
| litellm | 8003 | Provider proxy — stateless, scale freely |
| observability | 8004 | Fire-and-forget, but losing it causes data gaps |
| admin | 8005 | Used for org context on every cache policy lookup |

### Supporting services (min 1, scale on demand)

| Service | Min replicas | Notes |
|---------|-------------|-------|
| identity | 1 | Agent registry reads; low write rate |
| agent-relay | 1 | **Single-instance** — WebSocket state is in-process (see §3.1) |
| librarian | 1 | Background research loop is idempotent |
| memory | 1 | Stateless reads/writes to Postgres |
| league | 1 | Low traffic |
| scanner | 1 | Job queue in Postgres — multiple workers are safe |
| workflow-worker | 1+ | Multiple workers claim disjoint jobs via `FOR UPDATE SKIP LOCKED` |

### 3.1 Agent Relay — single-instance caveat

`agent-relay` maintains WebSocket connection state **in-process** (`_connections`, `_registered_agents`). Running multiple replicas would cause `POST /invoke/{slug}` to fail if it lands on the wrong instance.

**Mitigation options for multi-replica relay:**
1. **Sticky sessions** — configure the load balancer to route by `X-Agent-Slug` header or a consistent hash so all requests for a given agent always reach the same replica.
2. **Distributed state** — move the `_slug_to_token` map and pending futures to Redis pub/sub (not yet implemented; tracked as a follow-on issue).

For a single-datacenter deployment with one relay instance, the current design is sufficient. The relay reconnects in < 5 s if it crashes, and `restart: unless-stopped` ensures automatic recovery.

---

## 4. Rolling Upgrades

### Principle

Because all gateway services are stateless (state in Redis/Postgres), rolling upgrades are safe: a new pod/container can serve requests while old pods are still running. The load balancer routes requests to whichever instance is healthy.

### Azure Container Apps

Azure Container Apps performs rolling upgrades automatically whenever a new image tag is deployed:

1. New revision is created from the updated container image.
2. ACA gradually routes traffic to the new revision using **traffic splitting**.
3. Old revision drains in-flight requests before being decommissioned.

**Zero-downtime upgrade procedure:**

```bash
# Deploy new image tag — ACA handles traffic shifting automatically
az containerapp update \
  --name ca-cache-dev-sdc \
  --resource-group rg-aigw-dev-sdc \
  --image <acr>.azurecr.io/cache:sha-<new-sha>
```

The `deploy.yml` CI/CD workflow automates this step after every successful `master` push (see `docs/superpowers/specs/2026-06-08-azure-enterprise-deployment-design.md` §7).

**Rollback:**

```bash
# Roll back to a specific previous revision
az containerapp revision activate \
  --name ca-cache-dev-sdc \
  --resource-group rg-aigw-dev-sdc \
  --revision <previous-revision-name>

az containerapp ingress traffic set \
  --name ca-cache-dev-sdc \
  --resource-group rg-aigw-dev-sdc \
  --revision-weight <previous-revision-name>=100
```

### Docker Compose (development / self-hosted)

Docker Compose does not support true rolling upgrades. The recommended procedure for a dev environment is:

```bash
# 1. Pull / build the new image
docker compose -f infra/docker-compose.yml build cache

# 2. Restart one service at a time — the other services continue serving requests
docker compose -f infra/docker-compose.yml up -d --no-deps cache

# 3. Watch logs to confirm healthy startup
docker compose -f infra/docker-compose.yml logs -f cache
```

Because `restart: unless-stopped` is set, a container crash causes an automatic restart with < 5 s downtime.

### Database Migrations (Alembic)

Database schema migrations are the most disruptive part of an upgrade. The gateway uses **backward-compatible migrations**:

1. New columns are added as `NULLABLE` or with a default value.
2. The old code continues to work while the new code deploys.
3. Once all replicas run the new code, a follow-on migration can make columns `NOT NULL`.

The `db-migrate` job runs `alembic upgrade head` before any service containers start. It will block until migrations succeed.

**Important:** If a migration needs to backfill large tables, coordinate with on-call to run it during low-traffic hours, or use a background migration pattern.

---

## 5. Health and Readiness Probes

All gateway services expose two endpoints used by container orchestrators and load balancers:

| Endpoint | Purpose | Behaviour on failure |
|----------|---------|---------------------|
| `GET /health` | **Liveness** — process is running | Orchestrator restarts container |
| `GET /ready` | **Readiness** — deps (Redis, Postgres) reachable | Load balancer removes instance from rotation |

The readiness probe prevents traffic from being routed to a new instance until it has confirmed Redis and Postgres connectivity. This ensures that rolling upgrades do not expose degraded capacity windows.

---

## 6. Circuit Breakers

The semantic cache implements a **Redis-backed circuit breaker** for the embedding API:

- After 5 consecutive embedding failures, the circuit opens and all semantic cache operations are bypassed for 120 s.
- The circuit state is written to Redis (`embedding:circuit_open`) so **all replicas share the same breaker state**.
- When the circuit is open, exact-match caching and provider pass-through continue normally — only semantic matching is disabled.

This prevents a failing embedding provider from cascading into full cache unavailability.

---

## 7. Summary Checklist

Use this checklist when deploying or reviewing an HA configuration:

- [ ] Redis Sentinel enabled (`--profile sentinel`) or managed Azure Redis (Premium) in use
- [ ] `REDIS_SENTINEL_HOSTS` set for all services when using Sentinel
- [ ] Critical-path services (auth, cache, litellm, admin) running ≥ 2 replicas
- [ ] Load balancer health checks point to `/ready` (not `/health`)
- [ ] Alembic migrations confirmed backward-compatible before deployment
- [ ] `restart: unless-stopped` (Compose) or ACA restart policies configured
- [ ] Rollback procedure tested and documented for the current release
- [ ] Circuit breaker thresholds reviewed for embedding provider SLA
