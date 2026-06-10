# Services Architecture Overview

The AI Gateway is a distributed, microservices-based platform serving ~2000 SimCorp engineers. It is
deployed to **Azure Container Apps** (ACA) in the SimCorp Landing Zone (resource group
`rg-aigw-dev-sdc`, Sweden Central). Each service runs as a Container App named `ca-<service>-dev-sdc`
in the ACA environment `cae-aigw-dev-sdc`. The environment is `internal: true` — VNet-only, reachable
from the corporate VPN, with a static internal IP `10.179.231.6`.

## Service Map

The developer-facing entry point is the gateway FQDN **https://aigw-dev.lab.cloud.scdom.net**. ACA
ingress routes inbound requests by path to each Container App; services call each other over ACA
internal DNS at `http://ca-<service>-dev-sdc`.

```
┌─────────────────────────────────────────────────────────────────┐
│        Gateway FQDN: https://aigw-dev.lab.cloud.scdom.net        │
│              ACA ingress routes by path to services             │
└─────────────────────────────────────────────────────────────────┘
         │
         ├─ /admin → Admin Service (ca-admin-dev-sdc:8005)
         ├─ /auth → Auth Service (ca-auth-dev-sdc:8001)
         ├─ /cache → Cache Service (ca-cache-dev-sdc:8002)
         ├─ /litellm → LiteLLM (ca-litellm-dev-sdc:8003)
         ├─ /observability → Observability (ca-observability-dev-sdc:8004)
         ├─ /identity → Identity Service (ca-identity-dev-sdc:8006)
         ├─ /agent-relay → Agent Relay (ca-agent-relay-dev-sdc:8007)
         ├─ /librarian → Librarian (ca-librarian-dev-sdc:8008)
         ├─ /memory → Memory Service (ca-memory-dev-sdc:8009)
         ├─ /league → League Service (ca-league-dev-sdc:8010)
         ├─ /admin-portal → Admin Portal (ca-admin-portal-dev-sdc:3001)
         ├─ /portal → Developer Portal (ca-portal-dev-sdc:3002)
         └─ /tools-app → IT Tools
```

Background workers run as Container Apps with **no ingress**: `ca-scanner-dev-sdc` (security
scanning) and `ca-workflow-worker-dev-sdc`.

## Core Infrastructure

All PaaS dependencies run as managed Azure services reached over **private endpoints** in
`snet-pe-aigw-dev`. Their connection strings and secrets are stored in **Azure Key Vault** and
injected into each Container App via the app's managed identity.

### PostgreSQL — Azure Database for PostgreSQL Flexible Server

Multi-tenant database. Application services share the `aigateway` database; LiteLLM uses a separate
`litellm` database on the same Flexible Server.

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

**Migrations:** Alembic (services/admin/migrations/) applied via the `job-db-migrate-dev-sdc` ACA job.

### Redis — Azure Cache for Redis Premium P1

Cache and session store.

**Key Stores:**
- `session:{token}` — active session payloads (TTL: 8h admin / 7d dev)
- `user_sessions:{user_id}` — sorted set of active session tokens
- `oidc_state:{state}` — OIDC state validation (5m)
- `reset:{token_hash}` — password reset tokens (1h)
- `pwd_changed:{user_id}` — password change timestamp cache (for session invalidation)
- `user_node_changed:{user_id}`, `user_team_changed:{user_id}` — cache invalidation flags
- Provider-specific caches (embeddings, completions, etc.)

### Additional PaaS

- **Azure Key Vault** — all service secrets and connection strings.
- **Azure Service Bus** (queue `observability-events`) — async delivery of observability events.
- **Application Insights + Log Analytics** workspace `law-aca-dev-sdc` — metrics, traces, and container logs.

### Identity provider — Entra ID

Authentication uses **Entra ID** (Azure AD). OIDC groups are the source of truth for role
assignments. OIDC client config is stored in Key Vault.

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
Client → ca-cache-dev-sdc:8002 → ca-litellm-dev-sdc:8003 → OpenAI/Anthropic
```

**Key Features:**
- Semantic caching: find similar prompts, reuse responses
- Exact match caching: identical requests
- Per-node policy enforcement: TTL, threshold, model restrictions
- Cost tracking: logs all cache hits/misses to observability

**Dependencies:**
- Redis (cache store)
- LiteLLM (`ca-litellm-dev-sdc:8003`) for cache misses
- Observability (`ca-observability-dev-sdc:8004`) for cost recording

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
- Embedding API via the gateway (`ca-litellm-dev-sdc:8003`)
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
- Librarian (`ca-librarian-dev-sdc:8008`) for embeddings

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

### Scanner Service (`ca-scanner-dev-sdc`, no ingress)

**Role:** Security scanning (Garak, Nuclei, Nmap, ZAP). Runs as a background worker Container App
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

**API Base:** `https://aigw-dev.lab.cloud.scdom.net/admin` (via ACA ingress)

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

**API Dependencies (via ACA ingress at the gateway FQDN):**
- Admin (`/admin`) — org/user context
- Cache (`/cache`) — chat completions
- Librarian (`/librarian`) — documents/RAG
- Memory (`/memory`) — conversation history
- Identity (`/identity`) — agent discovery
- Agent Relay (`/agent-relay`) — real-time WebSocket
- League (`/league`) — challenges, leaderboard

---

### IT Tools

**Role:** Developer toolbox (terminal, DB clients, etc.).

**Deployment:** Pre-built container image, no ingress of its own (accessed via ACA ingress at `/tools-app/`)

---

## Request Path

Standard flow for a user request to generate code:

```
1. Browser: POST https://aigw-dev.lab.cloud.scdom.net/cache/v1/chat/completions
   └─ Body: {model, messages, temperature, ...}

2. ACA ingress routes to Cache (ca-cache-dev-sdc:8002)

3. Cache Service
   ├─ Validate Authorization header (Bearer token)
   ├─ Query Redis for session: session:{token}
   ├─ Check can_access(user, /org/path, "developer")
   ├─ Retrieve user's node-scoped policy (cache_ttl, rate_limit, allowed_models)
   │
   ├─ Check semantic cache (Redis) for similar prompt
   │  └─ Hit? Return cached response + log to observability
   │
   ├─ Check exact cache
   │  └─ Hit? Return cached response + log to observability
   │
   └─ Cache miss → Forward to LiteLLM

4. LiteLLM (ca-litellm-dev-sdc:8003)
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

**Deploy:** Bicep against the dev resource group (CI runs this via `deploy.yml`):
```bash
az deployment group create \
  --resource-group rg-aigw-dev-sdc \
  --template-file infra/bicep/environments/dev/main.bicep \
  --parameters infra/bicep/environments/dev/main.bicepparam \
  --parameters imageTag=sha-<git-sha>
```
Each deploy creates a fresh, atomic revision per Container App. Database migrations run as the
`job-db-migrate-dev-sdc` ACA job. See the operations runbook for rollback and revision management.

**Service Readiness:** ACA uses each service's `/health`, `/ready`, and `/liveliness` endpoints as
its liveness/readiness probes; ingress only routes to a revision once it reports ready.

**Access (over the corporate VPN):**
- Admin Portal: https://aigw-dev.lab.cloud.scdom.net/admin-portal/
- Developer Portal: https://aigw-dev.lab.cloud.scdom.net/portal/
- API: https://aigw-dev.lab.cloud.scdom.net/{path}/ (internally, services call `http://ca-<service>-dev-sdc`)

## Deployment Topology

- **Compute:** Azure Container Apps in environment `cae-aigw-dev-sdc` (`internal: true`, static IP `10.179.231.6`, Sweden Central), resource group `rg-aigw-dev-sdc`.
- **PostgreSQL:** Azure Database for PostgreSQL Flexible Server (databases `aigateway` + `litellm`).
- **Redis:** Azure Cache for Redis Premium P1.
- **Secrets:** Azure Key Vault, injected per app via managed identity.
- **Event bus:** Azure Service Bus (queue `observability-events`).
- **Telemetry:** Application Insights + Log Analytics workspace `law-aca-dev-sdc`.
- **Networking:** all PaaS reached via private endpoints in `snet-pe-aigw-dev`; ingress is VNet-only behind the gateway FQDN.

**Authentication:**
- Entra ID (Azure AD) is the identity provider.
- OIDC groups are source of truth for role assignments.
