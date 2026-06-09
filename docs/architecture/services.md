# Services Architecture Overview

The AI Gateway is a distributed, microservices-based platform serving ~2000 SimCorp engineers. All services are containerized and orchestrated via Docker Compose for local development.

## Service Map

```
┌─────────────────────────────────────────────────────────────────┐
│                    Nginx Hub (Port 8080)                        │
│              Routes traffic by path to services                 │
└─────────────────────────────────────────────────────────────────┘
         │
         ├─ /admin → Admin Service (:8005)
         ├─ /auth → Auth Service (:8001)
         ├─ /cache → Cache Service (:8002)
         ├─ /litellm → LiteLLM (:8003)
         ├─ /observability → Observability (:8004)
         ├─ /identity → Identity Service (:8006)
         ├─ /agent-relay → Agent Relay (:8007)
         ├─ /librarian → Librarian (:8008)
         ├─ /memory → Memory Service (:8009)
         ├─ /league → League Service (:8010)
         ├─ /admin-portal → Admin Portal (:3001)
         ├─ /portal → Developer Portal (:3002)
         └─ /tools-app → IT Tools
```

## Core Infrastructure

### PostgreSQL (Port 5432)

Multi-tenant database. All services share one aigateway database.

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

**Migrations:** Alembic (services/admin/migrations/) applied once at startup via db-migrate service.

### Redis (Port 6379)

Cache and session store.

**Key Stores:**
- `session:{token}` — active session payloads (TTL: 8h admin / 7d dev)
- `user_sessions:{user_id}` — sorted set of active session tokens
- `oidc_state:{state}` — OIDC state validation (5m)
- `reset:{token_hash}` — password reset tokens (1h)
- `pwd_changed:{user_id}` — password change timestamp cache (for session invalidation)
- `user_node_changed:{user_id}`, `user_team_changed:{user_id}` — cache invalidation flags
- Provider-specific caches (embeddings, completions, etc.)

**Optional:** Redis Sentinel for HA (enable with `--profile sentinel`)

### Dex (Port 5556)

Local OIDC provider for development. Substitutes for Entra ID in non-production.

**Config:** `infra/dex/config.yaml`

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
- `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` — Dex/Entra credentials
- `OIDC_ISSUER` — OIDC provider URL
- `ENVIRONMENT` — development (synthetic admin) or production

---

### Cache Service (:8002)

**Role:** Semantic + exact cache proxy; sits between client and LiteLLM.

**Request Path:**
```
Client → Cache (:8002) → LiteLLM (:8003) → OpenAI/Anthropic
```

**Key Features:**
- Semantic caching: find similar prompts, reuse responses
- Exact match caching: identical requests
- Per-node policy enforcement: TTL, threshold, model restrictions
- Cost tracking: logs all cache hits/misses to observability

**Dependencies:**
- Redis (cache store)
- LiteLLM (:8003) for cache misses
- Observability (:8004) for cost recording

---

### LiteLLM (:8003)

**Role:** Model provider routing (OpenAI-compatible interface).

**Features:**
- Single endpoint for multi-provider access (OpenAI, Anthropic, Ollama, etc.)
- Model load balancing
- Built-in rate limiting, cost tracking
- Proxy for `/v1/chat/completions` and other endpoints

**Configuration:** `.env` file with provider keys (OPENAI_API_KEY, etc.)

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
- Embedding API (Ollama or OpenAI)
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
- Librarian (:8008) for embeddings

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

### Scanner Service (:8011)

**Role:** Security scanning (Garak, Nuclei, Nmap, ZAP).

**Features:**
- Scan job submission
- Worker pool (concurrent executions)
- Result aggregation
- Quota management per node/user

**Dependencies:**
- PostgreSQL (jobs, results, quotas)
- Redis (job queue)
- Docker socket (worker container lifecycle)

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

**API Base:** `http://localhost:8080/admin` (proxied via nginx)

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

**API Dependencies:**
- Admin (:8005) — org/user context
- Cache (:8002) — chat completions
- Librarian (:8008) — documents/RAG
- Memory (:8009) — conversation history
- Identity (:8006) — agent discovery
- Agent Relay (:8007) — real-time WebSocket
- League (:8010) — challenges, leaderboard

---

### IT Tools

**Role:** Developer toolbox (terminal, DB clients, etc.).

**Deployment:** Pre-built Docker image, no published port (accessed via nginx at `/tools-app/`)

---

## Request Path

Standard flow for a user request to generate code:

```
1. Browser: POST /cache/v1/chat/completions
   └─ Body: {model, messages, temperature, ...}

2. Nginx (port 8080) routes to Cache (:8002)

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

4. LiteLLM (:8003)
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

## Development Workflow

**Quick start:**
```bash
cp .env.example .env
docker compose -f infra/docker-compose.yml up --build
```

**Service Readiness:**
- Postgres: healthcheck when container starts
- Redis: healthcheck
- Auth, Admin, Cache: healthcheck when deps are ready
- Admin Portal, Developer Portal: healthcheck when backend services are healthy

**Access Points:**
- Admin Portal: http://localhost:8080/admin-portal/ or :3001 directly
- Developer Portal: http://localhost:8080/portal/ or :3002 directly
- API: http://localhost:8080/{path}/ or service:{port} directly within Docker network

## Deployment Topology

**Production Topology (Azure Container Apps):**
- Services run as Container Apps in an Azure Container Apps environment (VNet-integrated, internal ingress)
- PostgreSQL: Azure Database for PostgreSQL Flexible Server (private endpoint)
- Redis: Azure Cache for Redis Premium P1 with zone-redundant replication and RediSearch module
- Load Balancing: ACA built-in HTTP ingress with automatic rolling-revision traffic shifting
- Observability: Azure Monitor + Application Insights

**High Availability:**
- Critical-path services (auth, cache, litellm, admin) run with a minimum of 2 replicas
- All services are stateless — shared state lives in Redis and PostgreSQL only
- Redis Sentinel is available for non-Azure deployments (`docker compose --profile sentinel up`)
- All services expose `/health` (liveness) and `/ready` (readiness) probes
- Database migrations (Alembic) use backward-compatible patterns to allow rolling upgrades

See [High Availability Guide](../high-availability.md) for detailed configuration and rolling upgrade procedures.

**Local Development (Docker Compose):**
- Single-instance services with `restart: unless-stopped`
- Redis Sentinel profile available (`--profile sentinel`) for HA testing locally

**Authentication:**
- Entra ID (Azure AD) replaces Dex in production
- OIDC groups are source of truth for role assignments
