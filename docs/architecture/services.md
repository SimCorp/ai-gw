# Services Architecture Overview

The AI Gateway is a distributed, microservices-based platform serving ~2000 SimCorp engineers. It
currently runs as a **single-host Docker Compose** deployment on one Linux VM (`vm-aigw-dev-sdc`,
`10.179.231.68`, Azure Sweden Central), behind a Caddy reverse proxy doing TLS. Reached at
`https://dev.aigw.scdom.net` over Zscaler ZPA (corp VPN). Each service runs as a container; services
discover each other by container name (e.g. `http://litellm:8003`).

> **Deferred V2 (ACA):** the Azure Container Apps deployment — Container Apps named
> `ca-<service>-dev-sdc`, managed PostgreSQL/Redis/Key Vault, private endpoints — is in-repo and
> ready for promotion but **not currently running**. See [`environments.md`](environments.md). The
> data-store sections below describe the V2 managed-PaaS shape; in the current single-host
> deployment those run as containers (postgres, redis) on the VM.

## Service Map

The developer-facing entry point is **https://dev.aigw.scdom.net**. Caddy terminates TLS and routes
inbound requests by path prefix; services call each other by container name on the Compose network.

```
┌─────────────────────────────────────────────────────────────────┐
│           Gateway: https://dev.aigw.scdom.net (Caddy :443)        │
│              routes by path prefix to each container              │
└─────────────────────────────────────────────────────────────────┘
         │
         ├─ /            → Developer Portal (portal:3002)
         ├─ /admin       → Admin Portal (admin-portal:3001)
         ├─ /v1/*        → Cache (cache:8002)  [OpenAI-compatible inference]
         ├─ /anthropic/* → Cache (cache:8002)  [Anthropic inference]
         ├─ /auth/*       → Admin Service (admin:8005)  [login / OIDC]
         ├─ /agent-relay/* → Agent Relay (agent-relay:8007)  [WebSocket]
         └─ /api/<svc>/*  → backend service APIs (prefix stripped by Caddy):
              admin:8005 · cache:8002 · litellm:8003 · identity:8006
              librarian:8008 · memory:8009 · league:8010 · graphify:8012 · observability:8004
```

Background workers run as containers with **no ingress**: `scanner` (security scanning),
`workflow-worker`, and `graphify-worker` (clones repos and runs `graphify extract`).

## Core Infrastructure

In the current single-host deployment, PostgreSQL and Redis run as containers on the VM with secrets
from a VM-local `.env`. The descriptions below cover both the running shape and the deferred V2
managed-PaaS target.

### PostgreSQL

Multi-tenant database. Application services share the `aigateway` database; LiteLLM uses a separate
`litellm` database. Current: `pgvector/pgvector:pg16` container on the VM. V2 target: Azure Database
for PostgreSQL Flexible Server.

**Key Tables:**
- `organization_nodes` — hierarchical org structure (path-based)
- `users` — user accounts (email, password hash, status)
- `role_assignments` — Entra group → role → node mappings
- `node_members` — direct team membership
- `policies` — cache/rate-limit/embedding settings per node
- `cost_records` — usage tracking for billing/budgets
- `audit_log` — activity records
- `api_keys` — service account credentials
- `user_invitations` — pending invites
- And service-specific tables (league, scanner, etc.)

**Migrations:** Alembic (services/admin/migrations/). In V2 (ACA) they run via the
`job-db-migrate-dev-sdc` ACA job.

### Redis

Cache and session store. Current: `redis/redis-stack` container on the VM. V2 target: Azure Cache
for Redis Premium P1.

**Key Stores:**
- `session:{token}` — active session payloads (TTL: 8h admin / 7d dev)
- `user_sessions:{user_id}` — sorted set of active session tokens
- `oidc_state:{state}` — OIDC state validation (5m)
- `reset:{token_hash}` — password reset tokens (1h)
- `pwd_changed:{user_id}` — password change timestamp cache (for session invalidation)
- `user_node_changed:{user_id}`, `user_team_changed:{user_id}` — cache invalidation flags
- Provider-specific caches (embeddings, completions, etc.)

### Secrets, events, and telemetry

Current single-host deployment:
- **Secrets** — VM-local `.env` (gitignored, mode 0600).
- **Events** — observability events are delivered async via the `observability` service.
- **Telemetry** — OpenTelemetry instrumentation is present; export to Application Insights is
  env-gated and activates in V2.

Deferred V2 (ACA):
- **Azure Key Vault** — all service secrets and connection strings.
- **Azure Service Bus** (queue `observability-events`) — async delivery of observability events.
- **Application Insights + Log Analytics** workspace `law-aca-dev-sdc` — metrics, traces, and container logs.

### Identity provider

OIDC groups are the source of truth for role assignments. Current single-host dev uses a local
**dex** OIDC provider; V2 uses **Entra ID** (Azure AD) with OIDC client config in Key Vault.

---

## AI Gateway Services

### Auth Service (:8001)

**Role:** User authentication, session management, password reset, OIDC integration.

**Request Path Component:** First entry point; validates bearer token before downstream services.

**Key Routes:**
- `POST /auth/login` — password authentication
- `POST /auth/register` — self-service signup
- `POST /auth/forgot-password`, `POST /auth/reset-password` — password reset flow
- `GET /auth/me` — current user details
- `GET /auth/oidc/login` — redirect to OIDC provider
- `GET /auth/oidc/callback` — OIDC token exchange & user creation
- `GET/POST/PATCH/DELETE /auth/invitations` — user invitations
- `POST/PATCH /auth/service-accounts` — API key management
- `GET /auth/sessions`, `DELETE /auth/sessions/{id}` — session management

**Dependencies:**
- PostgreSQL (users table)
- Redis (session storage, rate limiting, OIDC state)

**Environment Variables:**
- `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` — Entra ID credentials (from Key Vault)
- `OIDC_ISSUER` — Entra ID OIDC issuer URL
- `ENVIRONMENT` — development (synthetic admin) or production

---

### Cache Service (:8002)

**Role:** Semantic + exact cache proxy; sits between client and LiteLLM.

**Request Path:**
```
Client → cache:8002 → litellm:8003 → OpenAI/Anthropic
```

**Key Features:**
- Semantic caching: find similar prompts, reuse responses
- Exact match caching: identical requests
- Per-node policy enforcement: TTL, threshold, model restrictions
- Cost tracking: logs all cache hits/misses to observability

**Dependencies:**
- Redis (cache store)
- LiteLLM (`litellm:8003`) for cache misses
- Observability (`observability:8004`) for cost recording

---

### LiteLLM (:8003)

**Role:** Model provider routing (OpenAI-compatible interface).

**Features:**
- Single endpoint for multi-provider access (OpenAI, Anthropic, Google, GitHub Models, etc.)
- Model load balancing
- Built-in rate limiting, cost tracking
- Proxy for `/v1/chat/completions` and other endpoints (including embeddings used by cache/librarian)

**Configuration:** provider keys (`OPENAI_API_KEY`, etc.) injected from Key Vault; model routing in `services/litellm/config.yaml`. State persists in the `litellm` database on the Flexible Server.

---

### Admin Service (:8005)

**Role:** Organization management backend; shared by both portals.

**Key Routers:**
- `routers/nodes.py` — organization tree (CRUD, ancestry, children, members, policy, budget, permissions)
- `routers/unified_auth.py` — auth dependency, permission checks
- Legacy routers (areas.py, units.py, teams.py) — deprecated, not registered

**Dependencies:**
- PostgreSQL
- Redis (session validation)

**Health Check:** `GET /health`

---

### Observability Service (:8004)

**Role:** Async event ingestion for cost tracking and audit logging.

**Ingestion Points:**
- Cache service logs hits/misses
- LiteLLM logs token usage and costs
- Admin service logs audit events

**Schema:**
- `cost_records` — per-request: model, tokens, cost_usd, node_id, user_id
- `audit_log` — actions: login, API key created, permission granted, etc.

**Dependencies:**
- PostgreSQL
- Async task queue (background processing)

---

### Identity Service (:8006)

**Role:** Agent registry and DNS-style resolution; heartbeat-based availability.

**Features:**
- Agent registration with metadata (type, version, capabilities)
- Health check via TTL-based heartbeats
- Service discovery for agent-relay

**Dependencies:**
- PostgreSQL
- Redis (heartbeat tracking)

---

### Agent Relay (:8007)

**Role:** WebSocket relay bus for agentic workflows.

**Features:**
- Persistent WebSocket connections
- Message routing between agents
- Subscription-based pub/sub

**Dependencies:**
- Redis (message broker)

---

### Librarian (:8008)

**Role:** Knowledge ingestion, chunking, semantic search.

**Features:**
- Upload documents (PDF, Markdown, etc.)
- Automatic chunking and embedding generation
- Vector store (PostgreSQL pgvector)
- Semantic search API for RAG pipelines

**Dependencies:**
- PostgreSQL (pgvector for embeddings)
- Embedding API via the gateway (`litellm:8003`)
- Redis (job queue)

---

### Memory Service (:8009)

**Role:** Persistent agent memory, scoped per user/team.

**Features:**
- Store and retrieve conversation context
- Per-team isolation
- TTL support
- Integration with Librarian for semantic search

**Dependencies:**
- PostgreSQL
- Librarian (`librarian:8008`) for embeddings

---

### League Service (:8010)

**Role:** AI-League gamified challenge platform.

**Features:**
- Seasons (active/archived)
- Challenges (prompts, scoring rubrics)
- Submissions (from users/teams)
- Leaderboard (points, rankings)
- Store (cosmetics, achievements)

**Dependencies:**
- PostgreSQL
- Admin service for org context

---

### Graphify Service (:8012)

**Role:** Knowledge-graph service — registers GitHub repos, builds a queryable semantic
graph of each codebase, and exposes query APIs (and MCP tools) for navigating a repo by
concept. Splits into the `graphify` query API and the `graphify-worker` build runner.

**Features:**
- Repo registry + FIFO build queue (`graph_repos` / `graph_builds`)
- Build pipeline: shallow git clone/pull → `graphify extract` → node/edge counts + artefacts
- Query surface: `GET /query` plus MCP tools (`graph_query`, `graph_path`, `graph_explain`,
  `graph_stats`, `list_repos`) — pure local retrieval, no LLM at query time
- Gateway governance: build-time extraction routes through `cache:8002` with a `sk-*` key;
  direct provider keys are stripped from the build env

**Dependencies:**
- PostgreSQL (registry + build queue)
- `auth:8001` (sk-* validation) and `cache:8002` (build-time extraction LLM)
- Shared `graphify_out` volume for build artefacts

See [Graphify design spec](../superpowers/specs/2026-06-22-graphify-knowledge-graph-design.md).

---

### Scanner Service (`scanner`, no ingress)

**Role:** Security scanning (Garak, Nuclei, Nmap, ZAP). Runs as a background worker container
with no ingress; it pulls jobs from the queue rather than serving HTTP.

**Features:**
- Scan job submission
- Worker pool (concurrent executions)
- Result aggregation
- Quota management per node/user

**Dependencies:**
- PostgreSQL (jobs, results, quotas)
- Redis (job queue)

---

## Frontend Services

### Admin Portal (:3001)

**Role:** Admin panel for organization, users, policies, audit.

**Key Pages:**
- Organization tree (create/edit/delete nodes)
- User management (activate/suspend, roles, sessions)
- Cost reports (per-node, per-user)
- Audit log viewer
- Settings

**Technology:** Next.js 20 (Node.js), Server Components

**API Base:** `https://dev.aigw.scdom.net/admin` (served at `/admin` via Caddy)

---

### Developer Portal (:3002)

**Role:** Main interface for 2000 engineers.

**Key Pages:**
- Dashboard (spend, models, API keys)
- Playground (chat, completions)
- Agents (management, marketplace)
- Workflows (visual builder)
- API Keys & rate limits
- Models (available, performance metrics)
- Prompts (saved templates)
- MCP Servers (discovery, management)
- Plugins & Skills (marketplace)
- Usage & Spend (real-time)
- AI Transformation (adoption tracking, gamification)

**Technology:** Next.js 20 (Node.js), Shadcn UI

**API Dependencies (via Caddy at `https://dev.aigw.scdom.net`):**
- Inference (`/v1/*`, `/anthropic/*`) — chat completions, routed to cache
- Admin (`/api/admin/*`) — org/user context
- Librarian (`/api/librarian/*`) — documents/RAG
- Memory (`/api/memory/*`) — conversation history
- Identity (`/api/identity/*`) — agent discovery
- Agent Relay (`/agent-relay/*`) — real-time WebSocket
- League (`/api/league/*`) — challenges, leaderboard

---

### IT Tools

**Role:** Developer toolbox (terminal, DB clients, etc.).

**Deployment:** Pre-built container image. Not part of the current single-host Compose stack; a
`/tools-app/` ingress is only contemplated for the deferred V2 (ACA) deployment.

---

## Request Path

Standard flow for a user request to generate code:

```
1. Browser: POST https://dev.aigw.scdom.net/v1/chat/completions
   └─ Body: {model, messages, temperature, ...}

2. Caddy routes /v1/* to Cache (cache:8002)

3. Cache Service
   ├─ Validate Authorization header (Bearer token)
   ├─ Query Redis for session: session:{token}
   ├─ Check can_access(user, /org/path, "engineer")
   ├─ Retrieve user's node-scoped policy (cache_ttl, rate_limit, allowed_models)
   │
   ├─ Check semantic cache (Postgres/pgvector, HNSW) for similar prompt
   │  └─ Hit? Return cached response + log to observability
   │
   ├─ Check exact cache
   │  └─ Hit? Return cached response + log to observability
   │
   └─ Cache miss → Forward to LiteLLM

4. LiteLLM (litellm:8003)
   ├─ Route to provider (OpenAI, Anthropic, etc.)
   ├─ Handle rate limiting, retry logic
   └─ Return response

5. Cache Service (continued)
   ├─ Store response in cache (respecting TTL from policy)
   ├─ Log to Observability: {model, tokens, cost_usd, node_id, user_id}
   └─ Return to browser

6. Observability Service (background)
   ├─ Write cost_record to PostgreSQL
   ├─ Update aggregate spend in organization_nodes
   └─ Check budget alerts
```

## Data Flow: Session & Permissions

```
1. User logs in via /auth/login or /auth/oidc/callback

2. Auth Service
   ├─ Verify credentials (bcrypt or OIDC token)
   ├─ Load role_assignments for user's Entra groups
   ├─ Query organization_nodes for each assigned role → node_path
   ├─ Build session payload: {user_id, email, roles: [{role, node_path, node_id, node_name}]}
   └─ Store in Redis: session:{token} with TTL

3. Subsequent requests
   ├─ Client sends: Authorization: Bearer {token}
   ├─ Auth dependency (get_current_user) retrieves Redis payload
   ├─ Endpoint calls can_access(user, node.path, min_role)
   │  └─ Pure Python check: startswith() on paths, power comparison
   └─ If authorized, proceed; else 403 Forbidden
```

## Deploy and Access

**Deploy (current single-host):** `git push` to `master` → CI builds + pushes images to GHCR →
the VM pulls. Routine single-service update: `scripts/update-service.sh <svc>` (static base
untouched); full deploy: `scripts/deploy-vm.sh`. Compose always runs with both files
(`docker-compose.yml` + `docker-compose.host.yml`). Host stand-up is intentionally manual, not IaC.

**Deploy (deferred V2, ACA):** Bicep against the dev resource group, CI via `deploy.yml`
(archived). See [`environments.md`](environments.md).

**Service Readiness:** each service exposes `/health`, `/ready`, and `/liveliness` endpoints; in V2
(ACA) these are the liveness/readiness probes and ingress only routes once a revision reports ready.

**Access (over the corporate VPN, via Zscaler ZPA):**
- Developer Portal: https://dev.aigw.scdom.net/
- Admin Portal: https://dev.aigw.scdom.net/admin
- Inference API: https://dev.aigw.scdom.net/v1/ (internally, services call each other by container name)

## Deployment Topology

**Current (single-host):**
- **Compute:** Docker Compose on `vm-aigw-dev-sdc` (static private IP `10.179.231.68`, Sweden Central).
- **PostgreSQL:** `pgvector/pgvector:pg16` container (databases `aigateway` + `litellm`).
- **Redis:** `redis/redis-stack` container.
- **Secrets:** VM-local `.env` (gitignored, mode 0600).
- **Networking:** only Caddy is exposed (443/80); all services bind `127.0.0.1`; reached via ZPA.

**Deferred V2 (ACA):**
- **Compute:** Azure Container Apps in environment `cae-aigw-dev-sdc` (`internal: true`, static IP `10.179.231.6`, Sweden Central), resource group `rg-aigw-dev-sdc`.
- **PostgreSQL:** Azure Database for PostgreSQL Flexible Server (databases `aigateway` + `litellm`).
- **Redis:** Azure Cache for Redis Premium P1.
- **Secrets:** Azure Key Vault, injected per app via managed identity.
- **Event bus:** Azure Service Bus (queue `observability-events`).
- **Telemetry:** Application Insights + Log Analytics workspace `law-aca-dev-sdc`.
- **Networking:** all PaaS reached via private endpoints in `snet-pe-aigw-dev`; ingress is VNet-only behind the gateway FQDN.

**Authentication:**
- OIDC groups are the source of truth for role assignments.
- Current single-host dev uses a local **dex** OIDC provider; V2 uses **Entra ID** (Azure AD).
