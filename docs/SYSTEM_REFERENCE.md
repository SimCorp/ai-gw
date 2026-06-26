# AI Gateway — System Reference

> Enterprise AI gateway for SimCorp's ~2000 developers.
> Stack: FastAPI + Next.js services running on a single Linux VM via Docker Compose,
> behind a Caddy reverse proxy doing TLS. Backed by PostgreSQL and Redis.
> Current deployment: VM `vm-aigw-dev-sdc` (10.179.231.68, Azure Sweden Central),
> reached at `https://dev.aigw.scdom.net` over ZPA (corporate VPN).
> Azure Container Apps (ACA) is the deferred V2/prod target — see §17.
> Last updated: 2026-06-20

---

## 1. Architecture Overview

### 1.1 Request Path

```
Developer / Agent
      │
      ▼  Bearer <jwt> | Bearer <api-key>
  Auth Service :8001
      │  → validates identity, resolves team + project, checks rate limit
      │  → checks key-level, team-level, and org-level budgets
      ▼
  Cache Service :8002
      │  → exact SHA-256 hash match → return cached response
      │  → embedding cosine-similarity match → return cached response
      │  → miss → forward to LiteLLM
      ▼
  LiteLLM Proxy :8003
      │  → selects provider, injects master key
      ▼
  Provider (Anthropic / OpenAI / Azure OpenAI / Azure AI Foundry)
      │
  (response returns up through Cache → caller)
      │
  Observability :8004   (async, fire-and-forget)
      │  → event: team_id, model, tokens, cost, latency, cache status
      │  → Postgres worker writes cost_records; sessions; developer_activity_log
      │  → Redis budget counters incremented per team / key / org
      ▼
  Response returned to caller
```

The Anthropic-native path bypasses the cache layer's exact/semantic store but still
validates the gateway key and records an observability event:

```
Developer (Anthropic SDK)
      │  x-api-key: sk-...
      ▼
  Cache Service :8002  /anthropic/{path}
      │  → validates gateway key via Auth
      │  → forwards to LiteLLM /anthropic/{path} with master key
      ▼
  LiteLLM :8003 → Anthropic
```

### 1.2 Services and Ports

Each service runs as a Docker Compose container on the VM. Other services reach it over
the Compose network by container name at `http://<service>` on its container port. Only
Caddy is exposed externally (ports 80/443); the gateway is reachable from the corporate
VPN (ZPA) at the dev FQDN `https://dev.aigw.scdom.net` (VM `10.179.231.68`). In the V2/ACA
target each service instead runs as an Azure Container App named `ca-<service>-dev-sdc`
(see §17).

| Service | Compose name | Container Port | Health Endpoint | Purpose |
|---|---|---|---|---|
| auth | `auth` | 8001 | `GET /ready` | JWT / API key validation, rate limiting, budget enforcement |
| cache | `cache` | 8002 | `GET /ready` | Exact + semantic caching, guardrail enforcement, proxy to LiteLLM |
| litellm | `litellm` | 8003 | `GET /health/liveliness` | Provider routing, OpenAI-compatible API |
| observability | `observability` | 8004 | `GET /health` | Async event ingestion, cost recording, budget counters |
| admin | `admin` | 8005 | `GET /health` | Team management, API keys, policies, guardrails, budgets, workflows, MCP registry |
| identity | `identity` | 8006 | `GET /ready` | Agent identity tokens (RS256 JWTs, JWKS endpoint) |
| agent-relay | `agent-relay` | 8007 | `GET /health` | WebSocket relay for laptop-hosted agents (v1.0) |
| librarian | `librarian` | 8008 | `GET /ready` | AI Librarian: shared research knowledge base with semantic search |
| memory | `memory` | 8009 | `GET /ready` | Persistent agent memory scoped to user/team |
| league | `league` | 8010 | `GET /health` | AI-League gamified challenge platform |
| graphify | `graphify` | 8012 | `GET /health` | Knowledge-graph service — repo registry, code-graph builds, MCP query tools |
| admin-portal | `admin-portal` | 3001 | — | Admin Next.js UI |
| portal | `portal` | 3002 | — | Developer portal Next.js UI |
| scanner | `scanner` | none | — | Guardrail/security scanning worker (no ingress) |
| graphify-worker | `graphify-worker` | none | — | Graphify build runner (no ingress) |
| workflow-worker | `workflow-worker` | none | — | Async DAG executor (no ingress) |

### 1.3 Infrastructure Dependencies

In the current single-host deployment the infrastructure dependencies (PostgreSQL, Redis)
run as Compose containers (or co-located services) on the VM, and each service receives its
configuration and credentials as environment variables supplied by Docker Compose. The
managed-PaaS specifics described below — Azure Cache for Redis, Azure Database for
PostgreSQL, Service Bus, and Key Vault secret references — describe the deferred V2/ACA
target (see §17); on the single host the same configuration values are provided directly as
environment variables to the Compose services rather than resolved from Key Vault.

**Azure Cache for Redis (Premium P1)** — used for (the semantic cache itself now
lives in PostgreSQL/pgvector, see §3.3; Redis retains the exact cache and counters):
- Rate limit counters: `ratelimit:{team_id}:{model}` (60-second fixed window)
- Budget counters: `budget:team:{team_id}:{month}`, `budget:key:{key_id}:{month}`, `budget:org:{month}`
- Budget limits: `budget_limit:team:{team_id}`, `budget_limit:key:{key_id}`, `budget_limit:org`
- Policy cache: `policy:{team_id}` (hash) with fields `ttl_seconds`, `similarity_threshold`, `opt_out`, `embedding_model`, `rate_limit_rpm`, `allowed_models`
- Guardrail cache: `guardrails:{team_id}` and `guardrails:global` (JSON arrays, TTL 300 s)
- Auto-Drive stats: `autoroute:stats:{model}:{metric}:m{epoch_minute}` (TTL 360 s)
- Semantic cache circuit breaker: `embedding:circuit_open` (TTL 120 s)
- Identity signing key: RSA private key encrypted with `IDENTITY_KEY_SECRET`
- Developer sessions: `dev_session:{token}` (JSON)
- Scoped run keys: `run_key:{run_id}` plaintext key for workflow-worker injection

**Azure Database for PostgreSQL Flexible Server** — databases: `aigateway` (application
schema) and `litellm`. Schema managed by Alembic
(`services/admin/migrations`). Key tables: `teams`, `projects`, `api_keys`,
`policies`, `cost_records`, `guardrails`, `guardrail_hits`, `mcp_servers`, `mcp_tools`,
`agents`, `workflows`, `workflow_versions`, `workflow_runs`, `run_nodes`, `work_queue`,
`sessions`, `developer_activity_log`, `model_pricing`, `model_registry`, `audit_log`,
`areas`, `org_settings`.

**Azure Service Bus** — queue `observability-events` carries async observability events
from the gateway to the worker that writes `cost_records` and increments budget counters.

**Azure Key Vault** *(V2/ACA target)* — single source of runtime configuration and secrets,
surfaced to each Container App as native secret references resolved via managed identity. On
the single host, the same configuration is supplied as environment variables to the Compose
services.

**Application Insights + Log Analytics (`law-aca-dev-sdc`)** *(V2/ACA target)* — telemetry,
traces, and container logs for the Container Apps environment. On the single host, container
logs are available via `docker compose logs`.

**Schema migrations:** Alembic (`alembic upgrade head`) runs against Postgres before
application services start; application services do not run DDL. In the V2/ACA target this
runs as the `job-db-migrate-dev-sdc` Container Apps job.

### 1.4 New Services (2026 additions)

These services were added alongside the core v1 stack (auth/cache/litellm/obs/admin):

| Service | Port | Status | Description |
|---|---|---|---|
| identity | 8006 | Running | Issues RS256 signed agent identity tokens; exposes `/identity/jwks` |
| agent-relay | 8007 | Running (v1.0 only) | WebSocket relay so laptop-hosted agents can be targeted by the workflow worker |
| librarian | 8008 | Running | AI Librarian semantic search over shared research documents; exposes MCP endpoint |
| workflow-worker | none | Running (no HTTP port) | Async DAG executor; claims jobs from `work_queue` and runs agent steps |

---

## 2. Auth Service (port 8001)

### 2.1 Purpose

The Auth service is the gateway's single identity checkpoint. Every request that
reaches the Cache service (:8002) must first be validated here. Auth:

1. Accepts either an Azure Entra ID JWT or a gateway API key (`sk-...`).
2. Resolves the caller to `{team_id, project_id, key_id, scope}`.
3. Checks per-team rate limits (Redis fixed-window counter).
4. Checks key-level, team-level, and org-level monthly budget limits.
5. Returns the resolved identity, or 429 on rate/budget exhaustion.

Auth is **not** on the hot path for end-users directly — the Cache service calls it
on every request via an internal `POST /validate`. Auth also caches successful
identity resolutions in the Cache service's in-process store (45-second TTL) so
brief auth outages do not block agents.

### 2.2 Authentication Methods

**JWT (Azure Entra ID)**

- Bearer token in `Authorization` header.
- Any token that does *not* start with `sk-` is treated as a JWT.
- Validated against JWKS fetched from `JWKS_URI` (the Entra ID tenant JWKS endpoint).
- Claims must include `sub` (maps to `team_id` from the database) and optionally `project_id`.
- The tenant is SimCorp's Entra ID (`aa81b43f-3969-4fd4-80c9-84c411508d82`).

**API Keys**

- Bearer token starting with `sk-` in `Authorization` header.
- SHA-256 hashed and looked up in the `api_keys` table.
- Key row contains `team_id`, optional `project_id`, optional `scope`.
- Revoked keys (`revoked_at IS NOT NULL`) are rejected.
- Optional `scope` field: `workflow-run` restricts the key to `/v1/chat/completions` only.

### 2.3 Endpoints

#### `POST /validate`

Internal endpoint called by the Cache service on every inbound request.

**Request body:**
```json
{
  "token": "Bearer sk-abc123...",
  "model": "claude-sonnet-4-6"
}
```

The `token` field may include or omit the `Bearer ` prefix; the service strips it.
The `model` field is used only for rate-limit key namespacing.

**Response 200:**
```json
{
  "team_id": "3f8a2c1d-...",
  "project_id": "7b9e4f2a-...",
  "key_id": "c1d2e3f4-...",
  "scope": null
}
```

`project_id`, `key_id`, and `scope` may be `null`. `scope` is `"workflow-run"` for
short-lived run keys.

**Response 429 — rate limit exhausted:**
```json
{"detail": "Rate limit exceeded"}
```
Headers: `Retry-After: 60`

**Response 429 — budget exhausted:**
```json
{"error": "budget_exhausted", "message": "Team monthly budget of $500 exhausted"}
```

**Response 401:**
```json
{"detail": "Missing token"}
```

#### `GET /health`

Liveness probe. Returns `{"status": "ok"}` when the process is running.

#### `GET /ready`

Readiness probe. Checks Redis (`PING`) and Postgres (`SELECT 1`).

**Response 200:**
```json
{"status": "ready"}
```

**Response 503:**
```json
{"status": "not_ready", "errors": {"redis": "Connection refused"}}
```

### 2.4 Rate Limiting

Fixed-window per-team, per-model rate limiting using Redis pipelines.

- Window: 60 seconds.
- Key: `ratelimit:{team_id}:{model}` — `INCR` on each request; `EXPIRE 60 NX` sets TTL only on first request of each window.
- Default RPM: `RATE_LIMIT_DEFAULT_RPM=1000`. Can be overridden per team via the `policy:{team_id}` Redis hash field `rate_limit_rpm`.
- **Fail open:** Redis errors are swallowed; agents are never blocked by infra failures.

### 2.5 Budget Enforcement

Three tiers, checked in order (key → team → org):

| Tier | Redis key | When |
|---|---|---|
| Key | `budget_limit:key:{key_id}` | Only when request is authenticated by an API key |
| Team | `budget_limit:team:{team_id}` | Every request |
| Org | `budget_limit:org` | Every request |

Each limit is a JSON object `{"limit": 500.0, "action": "block"}` (or `"alert"`).
`action: "block"` → 429 returned. `action: "alert"` → allowed through but logged.
Absence of a limit key means unlimited.

**Fail open:** controlled by `BUDGET_REDIS_FAILOPEN` (default `true`). When `false`,
Redis unavailability causes a 503 instead of allowing the request.

Spend counters are updated asynchronously by the Observability service after each
completed request (`budget:team:{team_id}:{month}`, `budget:key:{key_id}:{month}`,
`budget:org:{month}`). The Admin service pre-seeds these counters to current MTD spend
when a budget limit is saved, ensuring enforcement is immediate on first set.

### 2.6 Configuration

Environment variables (read via `pydantic-settings`; on the current single host these are
supplied directly by Docker Compose, and in the V2/ACA target each is a Container Apps secret
reference resolved from Azure Key Vault — services fail fast if a required variable is
missing, with no local defaults):

| Variable | Source / Value | Description |
|---|---|---|
| `REDIS_URL` | Key Vault ref | Azure Cache for Redis connection URL |
| `DATABASE_URL` | Key Vault ref | Azure Database for PostgreSQL connection (asyncpg) |
| `JWKS_URI` | Entra ID tenant JWKS | OIDC JWKS endpoint for JWT validation |
| `ENTRA_TENANT_ID` | `aa81b43f-3969-4fd4-80c9-84c411508d82` | SimCorp Entra ID tenant |
| `ENTRA_CLIENT_ID` | `ai-gateway-admin` | Expected JWT `aud` claim |
| `RATE_LIMIT_DEFAULT_RPM` | `1000` | Default requests-per-minute per team |
| `BUDGET_REDIS_FAILOPEN` | `true` | Allow requests when Redis is unreachable |

---

## 3. Cache Service (port 8002)

### 3.1 Purpose

The Cache service is the primary entry point for all LLM calls. It sits between the
Auth service and LiteLLM, providing:

- **Exact caching** — deterministic SHA-256 hash of the normalized request body.
- **Semantic caching** — cosine similarity over OpenAI-compatible embeddings.
- **Auto-Drive routing** — selects the best-performing model automatically.
- **Guardrail enforcement** — per-team and global pattern rules checked on every request.
- **Anthropic-native passthrough** — `/anthropic/{path}` for SDKs that use the Anthropic wire format.
- **Model list proxy** — `GET /v1/models` forwarded to LiteLLM with gateway auth.
- **OpenAI streaming** — full SSE pass-through for live streaming; cache hits are replayed as SSE.

### 3.2 Exact Cache

Exact cache uses a deterministic SHA-256 hash of the canonical JSON request body
(`model` + `messages` + key parameters). Cache entries are namespaced per `{team_id}:{project_id}`.

**Bypass conditions (any of the following):**
- Team policy has `opt_out: true`
- Conversation has more than `conversation_turn_limit` user turns (default 3)
- Prompt contains PII patterns (git SHA, home directory paths, Python tracebacks, error messages, transaction IDs, personal account references)

**Cache hit response headers:**
```
X-Cache: HIT
X-Cache-Stage: exact
x-request-id: <uuid>
```

**Cache miss response headers:**
```
X-Cache: MISS
x-request-id: <uuid>
```

Successful responses from LiteLLM are stored in Redis with the team's configured
TTL (default 3600 seconds, ±10% jitter to prevent thundering-herd expiry).

### 3.3 Semantic Cache

When an exact match is not found, the cache embeds the prompt text using an
OpenAI-compatible embedding API and finds the nearest stored embedding via a
single HNSW-indexed vector query in PostgreSQL (pgvector), then verifies the
cosine similarity passes the threshold.

**Storage (`cache_entries` table, pgvector):** each row holds the embedding
(`vector`), the stored response, and the `(team_id, project_id)` scope. An HNSW
index on the embedding serves approximate-nearest-neighbour lookups in
sub-linear time, replacing the former O(N) Redis keyspace scan (migration 0035).
Expired rows are removed by a background expiry loop (every ~10 minutes) in
addition to TTL filtering at query time.

Match returns the stored response when `cosine_similarity >= similarity_threshold`
(default 0.90). This threshold is configurable per team via the Admin policy API.
On a below-threshold near miss, the highest similarity seen is carried into the
observability event as `similarity_score` (null on a clean miss) to baseline the
opportunity for a future LLM-judge tier.

**Circuit breaker:** after 5 consecutive embedding failures, the circuit trips and
all semantic cache operations are bypassed for 120 seconds. The circuit state is
stored in Redis (`embedding:circuit_open`) so all replicas share it.

Semantic cache hits set:
```
X-Cache: HIT
X-Cache-Stage: semantic
```

**SSE replay on cache hit:** when a client sends `stream: true`, cache hits (both
exact and semantic) are replayed as SSE chunks rather than returning a raw JSON body.
The replay emits: `role-delta` → `content-delta` → `finish-chunk` (with usage if
present) → `[DONE]`.

### 3.4 Auto-Drive Routing

The `/v1/chat/completions/auto` endpoint selects the best model from
`AUTOROUTE_MODELS` (comma-separated list) based on a 5-minute rolling performance
score. Selection is further filtered by request intent: complex tasks
(`code_generation`, `debugging`, `refactoring`, `testing`) are restricted to models
listed in `AUTOROUTE_COMPLEX_MODELS`; if none of those appear in `AUTOROUTE_MODELS`,
the full candidate list is used as a fallback. Simple intents may use any candidate.

**Scoring formula:**
```
score = (cache_hit_rate × 0.4) + (1 / (avg_latency_ms / 1000 + 1) × 0.4) + ((1 − error_rate) × 0.2)
```

Per-model stats are stored in Redis minute-bucketed keys (5 buckets, TTL 360 s):
```
autoroute:stats:{model}:requests:m{epoch_minute}
autoroute:stats:{model}:hits:m{epoch_minute}
autoroute:stats:{model}:latency_sum:m{epoch_minute}
autoroute:stats:{model}:errors:m{epoch_minute}
```

Models with zero traffic receive an exploration score of 0.5 so they receive
occasional traffic and are not permanently starved. Falls back to the first candidate
if Redis is unavailable.

### 3.5 Guardrail Enforcement

On every `/v1/chat/completions` request, the cache service loads guardrails from Redis:
- `guardrails:{team_id}` — team-specific rules
- `guardrails:global` — org-wide rules (team_id IS NULL)

Rules with `applies_to: "input"` or `applies_to: "both"` are checked against the
concatenated prompt text using compiled regex patterns. On a match:
- `action: "flag"` — records a guardrail hit event (async) and allows the request.
- `action: "block"` — immediately returns HTTP 400 and records the hit.

```json
{
  "error": "blocked_by_guardrail",
  "message": "Request blocked by guardrail: PII Detector"
}
```

Hit events are posted to `POST /guardrail-hits` on the Admin service asynchronously.

### 3.6 Cache Policy per Team

Per-team policies are loaded from Redis (`policy:{team_id}` hash) on each request.
Fields:

| Field | Default | Description |
|---|---|---|
| `ttl_seconds` | 3600 | Cache entry TTL (±10% jitter applied) |
| `similarity_threshold` | 0.90 | Minimum cosine similarity for a semantic cache hit |
| `opt_out` | false | Disables caching entirely for this team |
| `embedding_model` | `text-embedding-3-small` | Model used for semantic embedding |
| `rate_limit_rpm` | 1000 | Requests per minute (per team, per model) |
| `allowed_models` | `[]` (all) | Non-empty list restricts which models the team may call |
| `conversation_turn_limit` | 3 | User-turn count above which cache is bypassed |
| `budget_hard_cap` | 0 (disabled) | Per-team hard spend cap enforced in-process |

### 3.7 Endpoints

#### `POST /v1/chat/completions`

Main chat completions proxy. Validates the gateway token, checks guardrails, looks up
the cache, and forwards to LiteLLM on a miss.

**Request:** standard OpenAI `ChatCompletionRequest` body.

```json
{
  "model": "claude-sonnet-4-6",
  "messages": [{"role": "user", "content": "Hello"}],
  "stream": false
}
```

**Headers (inbound):**
- `Authorization: Bearer <jwt-or-api-key>` — required
- `x-request-id` / `x-correlation-id` — optional; generated if absent, propagated to LiteLLM and response
- `x-session-trace-id` — optional; logged to observability for session analytics
- `x-session-purpose` — optional; logged (e.g. `"code-review"`)
- `x-repo` — optional; logged for per-repo cost attribution

**Response 200 (cache miss):**
Standard OpenAI response body. Headers include `X-Cache: MISS` and `x-request-id`.

**Response 200 (cache hit, non-streaming):**
Cached response body. Headers include `X-Cache: HIT`, `X-Cache-Stage: exact|semantic`.

**Response 200 (cache hit, streaming requested):**
`Content-Type: text/event-stream`. SSE replay of the cached response.

**Response 401:**
```json
{"error": "Unauthorized"}
```

**Response 403 — model not permitted:**
```json
{
  "error": "model_not_permitted",
  "message": "Model 'gpt-4o' is not in your team's allowed model list"
}
```

**Response 400 — blocked by guardrail:**
```json
{
  "error": "blocked_by_guardrail",
  "message": "Request blocked by guardrail: Secrets Scanner"
}
```

**Response 429 — rate or budget limit:**
Forwarded directly from the Auth service.

**Response 503 — LiteLLM unreachable:**
```json
{
  "error": "upstream_unavailable",
  "message": "LLM provider temporarily unavailable"
}
```
Headers: `Retry-After: 30`

#### `POST /v1/chat/completions/auto`

Auto-Drive endpoint. Identical to `/v1/chat/completions` except the `model` field in
the request body is **ignored** and the gateway selects the best-scoring model from
`AUTOROUTE_MODELS`, restricted to `AUTOROUTE_COMPLEX_MODELS` for complex intents
(`code_generation`, `debugging`, `refactoring`, `testing`).

**Example:**
```bash
curl -X POST https://dev.aigw.scdom.net/v1/chat/completions/auto \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "What is 2+2?"}]}'
```

The response body includes the actual `model` field selected by Auto-Drive.

#### `GET /v1/models`

Returns the list of available models from LiteLLM. Requires gateway authentication.

**Response 200:** standard OpenAI models list response (forwarded from LiteLLM).

#### `POST /anthropic/{path}`

Anthropic-native passthrough for callers using the Anthropic SDK directly
(e.g. `ANTHROPIC_BASE_URL=https://dev.aigw.scdom.net/anthropic`).

Authentication accepts either:
- `x-api-key: sk-...` (Anthropic SDK default)
- `Authorization: Bearer sk-...`

The request body is forwarded to LiteLLM at `/anthropic/{path}` with the gateway's
`x-api-key` master key substituted. Supports streaming; token usage is extracted from
Anthropic SSE (`message_start` and `message_delta` events) and sent to observability.

Note: the Anthropic path does not use the exact/semantic cache — only auth and
observability are applied.

**Example:**
```python
import anthropic
client = anthropic.Anthropic(
    base_url="https://dev.aigw.scdom.net/anthropic",
    api_key="sk-my-gateway-key",
)
```

#### `GET /health`

Liveness probe. Returns `{"status": "ok"}`.

#### `GET /ready`

Readiness probe — checks Redis connectivity.

**Response 200:** `{"status": "ready"}`
**Response 503:** `{"status": "not_ready", "errors": {...}}`

### 3.8 Configuration

| Variable | Source / Value | Description |
|---|---|---|
| `REDIS_URL` | Key Vault ref | Azure Cache for Redis connection |
| `LITELLM_URL` | `http://litellm` | LiteLLM proxy URL |
| `LITELLM_MASTER_KEY` | Key Vault ref | Master key injected when forwarding to LiteLLM |
| `AUTH_URL` | `http://auth` | Auth service URL |
| `OBSERVABILITY_URL` | `http://observability` | Observability service URL |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Default embedding model |
| `EMBEDDING_API_KEY` | Key Vault ref | Gateway API key for embedding calls (routed via LiteLLM) |
| `EMBEDDING_BASE_URL` | `http://litellm/v1` | Base URL for the embedding API (via LiteLLM) |
| `DEFAULT_SIMILARITY_THRESHOLD` | `0.90` | Default cosine threshold for semantic cache hits |
| `DEFAULT_TTL_SECONDS` | `3600` | Default cache entry TTL |
| `INTERNAL_API_KEY` | Key Vault ref | Key used when posting events to observability |
| `CONVERSATION_TURN_LIMIT` | `3` | Max user turns before bypassing semantic cache |
| `BUDGET_CHECK_ENABLED` | `true` | Enable/disable the hard-budget gate |
| `AUTOROUTE_ENABLED` | `false` | Feature flag for Auto-Drive (endpoint always accessible) |
| `AUTOROUTE_MODELS` | `claude-haiku-4-5,gpt-4o-mini,claude-sonnet-4-6` | Comma-separated candidate model list |
| `AUTOROUTE_COMPLEX_MODELS` | `claude-sonnet-4-6` | Subset of `AUTOROUTE_MODELS` reserved for complex intents (code generation, debugging, refactoring, testing) |

---

## 4. LiteLLM Proxy (port 8003)

### 4.1 Purpose

LiteLLM provides an OpenAI-compatible API that routes requests to multiple AI
providers. The gateway treats it as an internal component: the Cache service forwards
requests using a master key, and provider API keys are managed inside LiteLLM's
configuration (not exposed to callers).

### 4.2 Supported Providers

The admin service seeds the model registry with the following providers and models
on startup (via `model_registry` table):

| Provider | Seed models |
|---|---|
| `anthropic` | claude-sonnet-4-6, claude-opus-4-7, claude-haiku-4-5 |
| `openai` | gpt-4o, gpt-4o-mini |
| `github-copilot` | copilot-gpt-4o, copilot-gpt-4o-mini, copilot-o3-mini, copilot-claude-3.5-sonnet |
| `azure` | azure-gpt-4o, azure-gpt-4o-mini, azure-o3-mini, azure-gpt-4.1 |
| `azure-ai-foundry` | phi-4, phi-4-mini, phi-3.5-mini, phi-3.5-moe, llama-3.3-70b, llama-3.1-405b, mistral-large-2, deepseek-r1, cohere-command-r-plus |
| `github-models` | github-gpt-4o |
| `google` | gemini-1.5-pro |

### 4.3 Provider Registration

LiteLLM reads provider credentials from its own configuration (environment variables
or a `config.yaml`). On the single host these provider keys are supplied as environment
variables to the `litellm` Compose service; in the V2/ACA target they are Container Apps
secret references resolved from Azure Key Vault. Required keys:

- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`
- `AZURE_API_KEY` / `AZURE_API_BASE` / `AZURE_API_VERSION`
- `GITHUB_TOKEN` (for GitHub Copilot and GitHub Models)

### 4.4 Fallback Routing

LiteLLM handles provider-level fallbacks and retries. The Cache service sets a
600-second timeout for non-streaming requests. LiteLLM returns standard OpenAI error
shapes; the Cache service propagates non-200 responses to the caller with the
`X-Cache: MISS` header.

### 4.5 OpenAI-Compatible API

The LiteLLM proxy exposes the standard OpenAI API surface:
- `POST /v1/chat/completions`
- `GET /v1/models`
- `POST /anthropic/{path}` (Anthropic native format)

The Cache service is the only caller; direct access to LiteLLM is not expected in
normal operation (it is on the internal Compose network only, not exposed by Caddy, and
so is not reachable from outside the VM).

**Anthropic prefix caching:** The Cache service injects
`anthropic-beta: prompt-caching-2024-07-31` on all requests so that provider-side
prompt caching compounds with the gateway's own cache.

---

## 5. Observability Service (port 8004)

### 5.1 Purpose

The Observability service ingests asynchronous telemetry events from the Cache
service and persists them to Postgres. It runs an internal publish-subscribe bus;
events are received via HTTP and fanned out to registered workers.

The service never blocks the request path. The Cache service posts events
fire-and-forget with a 2-second timeout.

### 5.2 Event Model

Events are `GatewayEvent` Pydantic objects:

```python
class GatewayEvent(BaseModel):
    team_id: str
    project_id: str | None
    key_id: str | None
    model: str | None
    tokens_input: int = 0
    tokens_output: int = 0
    cost_usd: float = 0.0
    cache_hit: bool = False
    latency_ms: int | None
    error: str | None
    timestamp: datetime          # defaults to utcnow()
    # Enhanced telemetry
    session_trace_id: str | None
    tool_invocation_count: int = 0
    retry_count: int = 0
    request_error_type: str | None
    cache_namespace: str | None  # "{team_id}:{project_id}"
    # Claude Code context headers
    repo: str | None
    session_purpose: str | None
    request_intent: str | None   # classified from prompt keywords
```

### 5.3 Workers

**Postgres worker** — subscribed to every event. For each event:

1. Estimates `cost_usd` from the `model_pricing` table (matched by model prefix,
   cached for 5 minutes). Formula: `(tokens_input × price_in + tokens_output × price_out) / 1000`.
2. Inserts a `cost_records` row.
3. Increments Redis budget counters (`budget:team:...`, `budget:key:...`, `budget:org:...`)
   with `INCRBYFLOAT`, expiring at end-of-month UTC.
4. Upserts a `sessions` row keyed by `session_trace_id` (if provided), computing
   cumulative metrics: turn count, total tokens, total cost, retry/error rates, tool
   invocations, average inter-request spacing, and a rule-based `quality_score` (1–5).
5. Upserts a `developer_activity_log` row (daily rollup per `developer_id`).

**Application Insights worker** — subscribes to every event and forwards structured
telemetry to Azure Application Insights when `APPINSIGHTS_CONNECTION_STRING` is set.

**Budget alert worker** — background loop that queries `cost_records` and sends
Slack-compatible webhook notifications when a team's spend crosses the configured
alert percentage.

**Session cleanup worker** — background loop that archives or removes stale session
rows.

### 5.4 Endpoints

#### `POST /events`

Accepts a `GatewayEvent` and publishes it to the internal bus.

**Authentication:** `x-internal-key: <INTERNAL_API_KEY>` header (constant-time
comparison via `secrets.compare_digest`).

**Request body:** `GatewayEvent` JSON (see §5.2).

**Response 202:**
```json
{"accepted": true}
```

**Response 401:**
```json
{"detail": "Invalid internal API key"}
```

#### `POST /guardrail-hits`

Receives a guardrail hit event from the Cache service and writes it to the
`guardrail_hits` table via the Admin service's `POST /guardrails/hits` endpoint.
(The actual write is delegated to the Admin service; Observability proxies the event.)

#### `POST /github/webhook`

Receives GitHub webhook events (push, pull_request, etc.) for repository-level cost
attribution and developer activity correlation.

#### `GET /health`

Liveness probe. Returns `{"status": "ok"}`.

#### `GET /ready`

Readiness probe — checks Redis and Postgres.

### 5.5 Configuration

| Variable | Source / Value | Description |
|---|---|---|
| `DATABASE_URL` | Key Vault ref | Azure Database for PostgreSQL connection |
| `REDIS_URL` | Key Vault ref | Azure Cache for Redis connection |
| `INTERNAL_API_KEY` | Key Vault ref | Expected `x-internal-key` header value |
| `APPINSIGHTS_CONNECTION_STRING` | Key Vault ref | Azure Application Insights connection string |

---

## 6. Admin Service (port 8005)

### 6.1 Purpose

The Admin service is the management plane for the entire gateway. It owns the
Postgres schema (via Alembic), exposes a REST API for every configuration surface,
and serves the admin and developer portals via the adjacent Next.js apps.

**Authentication model:**
- Most endpoints require `X-Admin-Token: <ADMIN_TOKEN>` header, or OIDC session
  cookie from the admin login flow.
- Developer-facing portal endpoints (`/portal/...`) authenticate via developer
  session tokens stored in Redis (`dev_session:{token}`).
- `GET /identity/jwks` requires no authentication.

**Security headers** (added to every response):
`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 1; mode=block`,
`Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy: geolocation=(), ...`

### 6.2 Teams and Projects

Teams group developers and define the billing/policy scope. Projects are optional
sub-divisions within a team (for finer-grained cache namespacing and cost attribution).

#### `GET /teams`

Returns all teams with their area assignments and budget fields.

**Response 200:**
```json
[
  {
    "id": "3f8a2c1d-...",
    "name": "Risk & Compliance",
    "slug": "risk-compliance",
    "created_at": "2026-01-15T09:00:00",
    "monthly_budget_usd": 500.0,
    "budget_alert_pct": 0.8,
    "budget_action": "block",
    "area_id": "a1b2c3d4-...",
    "area_name": "Risk & Compliance",
    "area_slug": "risk-compliance",
    "area_color": "#EF3E4A"
  }
]
```

#### `POST /teams`

Creates a new team. Records an audit log entry.

**Request body:**
```json
{"name": "Platform Engineering", "slug": "platform-eng", "area_id": null}
```

**Response 201:** team object with generated `id`.

#### `GET /teams/{team_id}`

Returns a single team by UUID.

#### `PUT /teams/{team_id}`

Updates a team's name, slug, and area. Records an audit log entry.

#### `DELETE /teams/{team_id}`

Deletes a team. Records an audit log entry. Returns 204 on success.

#### `GET /teams/{team_id}/projects`

Returns all projects belonging to a team.

**Response 200:**
```json
[{"id": "...", "team_id": "...", "name": "Copilot", "slug": "copilot", "created_at": "..."}]
```

#### `POST /teams/{team_id}/projects`

Creates a project within a team. Records an audit log entry.

**Request body:** `{"name": "Copilot", "slug": "copilot"}`

**Response 201:** project object.

### 6.3 API Key Management

The gateway issues two classes of API keys:

1. **Long-lived keys** — created by admins via `POST /teams/{team_id}/keys` or by
   developers via `POST /portal/teams/{team_id}/keys`. Used for ongoing developer
   access.
2. **Short-lived scoped keys** — issued automatically per workflow run (scope:
   `workflow-run`, TTL 1 hour). Returned once in `POST /runs` response; never stored
   in plaintext.

Keys are formatted `sk-<32-byte-url-safe-random>`. Only the SHA-256 hash is stored.
The plaintext is returned once at creation time and cannot be recovered.

#### `GET /teams/{team_id}/keys`

Lists all active (non-revoked) API keys for a team.

**Response 200:**
```json
[{"id": "...", "name": "CI/CD key", "team_id": "...", "created_at": "..."}]
```

#### `POST /teams/{team_id}/keys`

Creates a new API key for a team (admin endpoint).

**Request body:**
```json
{"name": "CI/CD key", "project_id": null}
```

**Response 201:**
```json
{
  "id": "c1d2e3f4-...",
  "name": "CI/CD key",
  "key": "sk-abc123...",
  "created_at": "2026-05-11T10:00:00"
}
```

The `key` field is the only time the plaintext is returned.

#### `DELETE /teams/{team_id}/keys/{key_id}`

Revokes a key by setting `revoked_at`. Returns 204.

#### Portal-facing key endpoints

The `/portal/teams/{team_id}/keys` router exposes identical create/list/revoke
endpoints, but authenticates via developer session token and enforces team membership.

- `GET /portal/teams/{team_id}/keys`
- `POST /portal/teams/{team_id}/keys`
- `DELETE /portal/teams/{team_id}/keys/{key_id}`

### 6.4 Model Registry

The model registry is seeded on startup and tracks available models per provider.

#### `GET /models` (model registry)

Returns all models in the registry.

#### `POST /models`

Registers a new model.

### 6.5 Policies (per-team cache + rate config)

Each team can have one policy (and optionally per-project policies). The policy is
written to Postgres **and** synced to Redis immediately so the Cache service picks up
changes without restart.

Redis key: `policy:{team_id}` (or `policy:{team_id}:{project_id}`)

#### `GET /teams/{team_id}/policy`

Returns the team's current policy or `{}` if none is set.

**Response 200:**
```json
{
  "id": "...",
  "team_id": "...",
  "cache_ttl_seconds": 3600,
  "cache_similarity_threshold": 0.90,
  "cache_opt_out": false,
  "embedding_model": "text-embedding-3-small",
  "rate_limit_rpm": 1000,
  "allowed_models": []
}
```

#### `PUT /teams/{team_id}/policy`

Creates or updates the team policy. Syncs to Redis immediately.

**Request body:**
```json
{
  "cache_ttl_seconds": 7200,
  "cache_similarity_threshold": 0.92,
  "cache_opt_out": false,
  "embedding_model": "text-embedding-3-small",
  "rate_limit_rpm": 500,
  "allowed_models": ["claude-sonnet-4-6", "claude-haiku-4-5"]
}
```

`allowed_models: []` means all models are permitted. Non-empty list restricts the
team to exactly those model IDs.

#### `GET /policies`

Returns policies for all teams in a single response (admin dashboard use).

### 6.6 Guardrails

Guardrails are pattern-matching or type-based rules applied to requests/responses by
the Cache service. They are stored in Postgres and synced to Redis on every create,
update, or delete.

**Default seed guardrails (global, created at startup):**

| Name | Type | Applies To | Action | Severity | Priority |
|---|---|---|---|---|---|
| PII Detector | pii_detector | input | block | critical | 10 |
| Secrets Scanner | secrets_scanner | input | block | critical | 20 |
| Prompt Injection | prompt_injection | input | flag | high | 30 |
| Topic Block — Trading Advice | topic_block | input | block | high | 40 |
| MNPI Detector | mnpi_detector | input | block | critical | 15 |
| Token Budget Cap | token_budget_cap | input | truncate | low | 5 |
| Output PII Redactor | output_pii_redactor | output | redact | critical | 10 |
| Hallucinated Citation Check | citation_check | output | flag | medium | 50 |
| Toxicity Filter | toxicity_filter | output | block | high | 20 |
| Confidence Floor on Numbers | confidence_floor | output | rewrite | medium | 60 |

#### `GET /guardrails`

Returns all guardrails. Optional query param `?team_id=<uuid>` filters to a team's
rules plus global rules.

**Response 200:**
```json
[
  {
    "id": "...",
    "name": "PII Detector",
    "description": "...",
    "type": "pii_detector",
    "applies_to": "input",
    "action": "block",
    "severity": "critical",
    "priority": 10,
    "config": {"patterns": ["email", "iban", "credit_card", "cpr", "ssn", "phone_eu"]},
    "enabled": true,
    "version": 1,
    "team_id": null,
    "hits_24h": 3,
    "blocks_24h": 1
  }
]
```

#### `GET /guardrails/summary`

Returns aggregate counts for the admin dashboard.

**Response 200:**
```json
{
  "active_count": 10,
  "input_count": 6,
  "output_count": 3,
  "both_count": 1,
  "hits_24h": 45,
  "blocked_24h": 12
}
```

#### `GET /guardrails/hits`

Returns recent guardrail hit records. Optional `?guardrail_id=<uuid>` filter.
Optional `?limit=<n>` (default 20, max 200).

#### `POST /guardrails`

Creates a new guardrail. Syncs to Redis.

**Request body:**
```json
{
  "name": "Block Competitor Names",
  "type": "topic_block",
  "applies_to": "input",
  "action": "block",
  "severity": "high",
  "priority": 50,
  "config": {"blocked_topics": ["competitor_a", "competitor_b"]},
  "team_id": "3f8a2c1d-..."
}
```

`team_id: null` creates a global guardrail applied to all teams.

**Response 201:** full guardrail object.

#### `PATCH /guardrails/{guardrail_id}`

Updates a guardrail. Bumps `version` by 1 on every update. Syncs to Redis.

Patchable fields: `name`, `description`, `applies_to`, `action`, `severity`,
`priority`, `config`, `enabled`.

#### `DELETE /guardrails/{guardrail_id}`

Deletes a guardrail. Syncs Redis. Returns 204.

#### `POST /guardrails/hits`

Internal endpoint called by the Cache service to record a guardrail hit. See §5.4.

### 6.7 Budget and Cost Tracking

The budget system has three tiers. Limits are persisted in Postgres (`teams.monthly_budget_usd`,
`api_keys.monthly_budget_usd`, `org_settings`), synced to Redis for fast enforcement
by the Auth service, and actual spend is tracked via `cost_records` in Postgres.

Budget limits stored in Redis expire every 5 minutes (`_BUDGET_REDIS_TTL = 300 s`) and
are re-seeded from Postgres on the next `PUT` call, so Redis stays warm as long as the
admin service is running.

#### `GET /teams/{team_id}/budget`

Returns team budget status.

**Response 200:**
```json
{
  "team_id": "...",
  "monthly_budget_usd": 500.0,
  "budget_alert_pct": 0.8,
  "budget_action": "block",
  "current_spend_usd": 312.45,
  "budget_remaining_usd": 187.55,
  "pct_used": 0.625
}
```

`budget_action` is `"alert"` (notify only) or `"block"` (return 429).

#### `PUT /teams/{team_id}/budget`

Sets or clears the team's monthly budget. Syncs to Redis. Seeds the running spend
counter to the current MTD spend so enforcement is immediate.

**Request body:**
```json
{
  "monthly_budget_usd": 500.0,
  "budget_alert_pct": 0.8,
  "budget_action": "block"
}
```

`monthly_budget_usd: null` removes the limit (deletes the Redis key).

#### `GET /keys/{key_id}/budget`

Returns the per-key budget status.

#### `PUT /keys/{key_id}/budget`

Sets or clears the per-key monthly budget.

**Request body:**
```json
{"monthly_budget_usd": 50.0}
```

#### `GET /org/budget`

Returns the organisation-level budget.

#### `PUT /org/budget`

Sets the organisation-level budget limit and notification policy.

**Request body:**
```json
{
  "monthly_budget_usd": 10000.0,
  "budget_alert_pct": 0.9,
  "budget_action": "alert"
}
```

#### `GET /budget/status`

Combined dashboard view: org summary + all teams with spend and budget state.

**Response 200:**
```json
{
  "org": {
    "monthly_budget_usd": 10000.0,
    "current_spend_usd": 4200.0,
    "pct_used": 0.42,
    "budget_action": "alert"
  },
  "teams": [...],
  "team_count": 12,
  "teams_over_alert": 2
}
```

#### `GET /budget/forecast`

Projects end-of-month spend using current MTD burn rate
(formula: `mtd_spend × days_in_month / days_elapsed`).

**Response 200:**
```json
{
  "as_of_date": "2026-05-11",
  "days_elapsed": 11,
  "days_remaining": 20,
  "days_in_month": 31,
  "org": {
    "mtd_spend_usd": 1500.0,
    "projected_month_end_usd": 4227.27,
    "monthly_budget_usd": 10000.0,
    "on_track": true
  },
  "teams": [...]
}
```

#### `GET /org/notifications`

Returns the configured Slack-compatible budget alert webhook URL.

**Response 200:**
```json
{"webhook_url": "https://hooks.slack.com/...", "enabled": true}
```

#### `PUT /org/notifications`

Configures the budget alert webhook. Empty string disables.

**Request body:**
```json
{"webhook_url": "https://hooks.slack.com/services/..."}
```

#### `POST /org/notifications/test`

Fires a test POST to the configured webhook and returns success/error.

### 6.8 MCP Server Registry

The admin service maintains a registry of MCP (Model Context Protocol) servers that
agents and developers can connect to. Three built-in servers are auto-registered on
startup: `Awesome Copilot`, `AI Librarian`, and `CodeMate Tools`.

SSRF protection is applied to all server URLs: private IP ranges, loopback, link-local,
AWS IMDS address, and alternative IP representations (decimal, hex, octal) are blocked.

#### `GET /mcp/servers`

Lists all MCP servers with tool and access counts.

**Response 200:**
```json
[
  {
    "id": "...",
    "name": "Awesome Copilot",
    "description": "Community agents, instructions, and recipes",
    "url": "http://admin/mcp/copilot-catalog",
    "auth_type": "none",
    "auth_header": null,
    "auth_secret": "***",
    "enabled": true,
    "status": "active",
    "tool_count": 5,
    "access_count": 3
  }
]
```

Note: `auth_secret` is always masked (`***`) in list and get responses.

#### `POST /mcp/servers`

Registers a new MCP server. URL is validated for SSRF risk.

**Request body:**
```json
{
  "name": "Internal Search",
  "description": "Semantic search over internal docs",
  "url": "https://mcp.corp.simcorp.com/search",
  "auth_type": "bearer",
  "auth_header": null,
  "auth_secret": "sk-internal-...",
  "enabled": true
}
```

`auth_type` is one of `"none"`, `"bearer"`, `"api_key"`.

**Response 201:** server object with `auth_secret: "***"`.

#### `GET /mcp/servers/{server_id}`

Returns a server with its tools and access grants.

**Response 200:**
```json
{
  "server": {...},
  "tools": [
    {"id": "...", "name": "search_docs", "description": "...", "input_schema": {...}, "enabled": true}
  ],
  "access": [
    {"server_id": "...", "team_id": "...", "team_name": "Engineering", "granted_at": "..."}
  ]
}
```

#### `PUT /mcp/servers/{server_id}`

Updates server fields. Passing `auth_secret: "***"` preserves the existing secret.

#### `DELETE /mcp/servers/{server_id}`

Deletes a server. Returns 204.

#### `POST /mcp/servers/{server_id}/ping`

Pings the server, syncs its tool list, and updates `status`, `last_ping_at`,
`last_ping_ms`, `tool_count`.

Tries `{url}/tools` first; falls back to `{url}` if 404. Accepts tool lists as
JSON array, `{"tools": [...]}`, or `{tool_name: schema}` dict.

**Response 200:**
```json
{
  "status": "active",
  "tool_count": 3,
  "latency_ms": 45,
  "tools": [{"name": "search", "description": "...", "input_schema": {...}}]
}
```

#### `GET /mcp/servers/{server_id}/tools`

Lists all tools for a server.

#### `PATCH /mcp/servers/{server_id}/tools/{tool_name}`

Enables or disables a specific tool.

**Request body:** `{"enabled": false}`

#### `GET /mcp/servers/{server_id}/access`

Lists teams that have been granted access to a server.

#### `POST /mcp/servers/{server_id}/access`

Grants a team access to a server.

**Request body:** `{"team_id": "3f8a2c1d-..."}`

**Response 201:** access grant object.

#### `DELETE /mcp/servers/{server_id}/access/{team_id}`

Revokes a team's access to a server. Returns 204.

#### `GET /mcp/summary`

Returns aggregate counts: `server_count`, `active_count`, `disabled_count`,
`error_count`, `pending_count`, `total_tools`, `enabled_tools`, `teams_with_access`.

### 6.9 Workflow Designer API

The workflow designer enables multi-step agent DAG composition. The three resource
groups are defined in `services/admin/app/routers/workflows.py`.

#### 6.9.1 Agent Registry (`/agents`)

Agents are containerised programs that read `/run/inputs.json` and write
`/run/outputs.json`. Each agent has a manifest describing its image, category,
input/output schema, and whether it is managed (platform-owned) or team-owned.

**Agent manifest schema** (from `agents/echo-agent/manifest.json`):
```json
{
  "slug": "echo-agent",
  "name": "Echo Agent",
  "description": "Returns its inputs verbatim under an 'echoed' key.",
  "image": "ai-gateway-echo-agent:dev",
  "category": "utility",
  "managed": true,
  "inputs_schema": {"type": "object"},
  "outputs_schema": {
    "type": "object",
    "properties": {
      "echoed": {"type": "object"},
      "agent": {"const": "echo-agent"}
    },
    "required": ["echoed", "agent"]
  }
}
```

**Agent container contract:**

| Item | Description |
|---|---|
| `/run/inputs.json` | Worker-written JSON inputs; agent reads this (read-only mount) |
| `/run/outputs.json` | Agent writes JSON outputs here; worker reads after container exit |
| `AIGW_RUN_ID` | UUID of the parent workflow run |
| `AIGW_NODE_ID` | This node's ID within the DAG |
| `AIGW_BASE_URL` | Gateway base URL (`http://cache`) |
| `AIGW_API_KEY` | Short-lived scoped API key for LLM calls via the gateway |

**Image naming rules:**
- Docker registry images: must match `^[a-z0-9][a-z0-9._/-]*:[a-z0-9._-]+$`
- Relay-hosted agents: must be `relay://{slug}` URI
- Managed agents: stored in ACR; user agents may use any registry with admin approval

##### `GET /agents`

Lists all enabled agents. Optional `?category=<string>` filter.

**Response 200:**
```json
{
  "agents": [
    {
      "id": "...",
      "slug": "echo-agent",
      "name": "Echo Agent",
      "description": "...",
      "image": "ai-gateway-echo-agent:dev",
      "manifest": {...},
      "category": "utility",
      "managed": true,
      "enabled": true
    }
  ]
}
```

##### `POST /agents`

Registers or upserts an agent (slug is the unique key). Image string is validated.

**Request body:**
```json
{
  "slug": "summarizer",
  "name": "Summarizer",
  "description": "Summarises a document",
  "image": "registry.simcorp/agents/summarizer:1.2.0",
  "manifest": {...},
  "category": "productivity",
  "managed": false,
  "owner_team_id": "3f8a2c1d-...",
  "owner_project_id": null
}
```

**Response 201:** `{"id": "...", "slug": "summarizer"}`

#### 6.9.2 Workflow Definitions (`/workflows`)

Workflows are versioned JSON DAGs. Each version is immutable; edits always create a
new version.

**DAG format (v0.5):**
```json
{
  "entry_node": "n1",
  "nodes": [
    {
      "id": "n1",
      "agent_slug": "summarizer",
      "inputs": {"format": "bullet_points"},
      "loop": {"enabled": false, "max_iterations": 10}
    },
    {
      "id": "n2",
      "agent_slug": "echo-agent",
      "inputs": {}
    }
  ],
  "edges": [
    {"from": "n1", "to": "n2", "condition": null},
    {"from": "n1", "to": "n3", "condition": "outputs.status == \"success\""}
  ]
}
```

**Condition syntax:** `<dotted.path> <op> <literal>` where op is `==`, `!=`, `>`, `>=`,
`<`, `<=`. Literal may be a quoted string, number, `true`, `false`, or `null`.
The prefix `outputs.` is optional (stripped). No condition (`null`) means the edge is
always taken. Conditions are evaluated against the preceding node's `outputs` dict.

**Loop nodes:** set `loop.enabled: true` and `loop.max_iterations: N`. The node will
repeat up to N times while `outputs._loop_continue == true`. Iteration count is
tracked in `run_nodes.iteration`.

##### `GET /workflows`

Lists workflows. Optional `?team_id=<uuid>` filter.

**Response 200:**
```json
{
  "workflows": [
    {
      "id": "...",
      "slug": "weekly-summary",
      "team_id": "...",
      "project_id": null,
      "name": "Weekly Summary",
      "description": "...",
      "latest_version": 3,
      "created_at": "2026-05-01T09:00:00"
    }
  ]
}
```

##### `POST /workflows`

Creates a new workflow definition (no DAG yet — DAG is added via versions).

**Request body:**
```json
{
  "slug": "weekly-summary",
  "name": "Weekly Summary",
  "description": "Aggregates weekly metrics",
  "team_id": "3f8a2c1d-...",
  "project_id": null
}
```

**Response 201:** `{"id": "...", "slug": "weekly-summary"}`

##### `POST /workflows/{workflow_id}/versions`

Saves a new DAG version. Atomically increments `latest_version`. Validates that:
- `nodes` is a non-empty list
- `edges` is a list (may be empty)
- `entry_node` is declared and present in `nodes`

**Request body:**
```json
{
  "dag": { ... },
  "created_by": "c1d2e3f4-..."
}
```

**Response 201:** `{"workflow_id": "...", "version": 4}`

##### `GET /workflows/{workflow_id}/versions/{version}`

Returns a specific DAG version.

**Response 200:**
```json
{
  "workflow_id": "...",
  "version": 3,
  "dag": { ... },
  "created_by": "...",
  "created_at": "2026-05-10T14:30:00"
}
```

#### 6.9.3 Workflow Runs (`/runs`)

##### `POST /runs`

Submits a run. Rate-limited at 100 runs/hour/team (Redis counter; configurable per
team like other rate limits). Returns 429 with `Retry-After` header if exceeded.

On success, the server:
1. Resolves `version` to `latest_version` if not supplied.
2. Issues a scoped API key (`scope: "workflow-run"`, TTL 3600 s) for the run's agents.
3. Inserts a `workflow_runs` row.
4. Inserts the `entry_node` into `work_queue` and `run_nodes`.
5. Publishes `workflow.run.started` event to the observability bus.

**Request body:**
```json
{
  "workflow_id": "a1b2c3d4-...",
  "version": null,
  "inputs": {"document_url": "https://..."},
  "team_id": "3f8a2c1d-...",
  "project_id": null,
  "triggered_by": "user-uuid-or-api-key-uuid",
  "triggered_by_kind": "user"
}
```

`triggered_by_kind` is `"user"` or `"api_key"`.

**Response 201:**
```json
{
  "id": "run-uuid-...",
  "scoped_api_key": "sk-..."
}
```

The `scoped_api_key` is returned **once only** and is not stored in plaintext.
The workflow worker uses this key (via Redis) to inject `AIGW_API_KEY` into agent
containers. All LLM calls from agent containers must use this key via
`http://cache`.

**Response 429:**
```json
{"detail": "Run rate limit exceeded for this team"}
```
Headers: `Retry-After: 3600`

##### `GET /runs/{run_id}`

Returns run status and per-node state.

**Response 200:**
```json
{
  "run": {
    "id": "...",
    "workflow_id": "...",
    "version": 3,
    "status": "running",
    "inputs": {"document_url": "..."},
    "outputs": null,
    "error": null,
    "triggered_by": "...",
    "triggered_by_kind": "user",
    "team_id": "...",
    "project_id": null,
    "started_at": "2026-05-11T10:00:00",
    "finished_at": null,
    "created_at": "2026-05-11T09:59:58"
  },
  "nodes": [
    {
      "node_id": "n1",
      "iteration": 0,
      "status": "succeeded",
      "agent_id": "...",
      "inputs": {...},
      "outputs": {"summary": "...", "_loop_continue": false},
      "error": null,
      "started_at": "2026-05-11T10:00:01",
      "finished_at": "2026-05-11T10:00:45"
    }
  ]
}
```

Run `status` is one of: `pending`, `running`, `succeeded`, `failed`, `cancelled`.

##### `POST /runs/{run_id}/cancel`

Cancels a pending or running run. Sets status to `cancelled`, revokes the scoped API
key, and publishes `workflow.run.finished` event.

Returns 409 if the run is already in a terminal state.

**Response 200:** `{"status": "cancelled"}`

##### `GET /runs/{run_id}/stream`

SSE endpoint for live run observability. Requires Redis.

**Response:** `Content-Type: text/event-stream`

The stream begins with a `snapshot` event containing the current run state and all
node statuses, then delivers live events from the Redis pubsub channel, and ends with
`workflow.run.finished`. Heartbeats are sent every 15 seconds to keep proxies alive.

**SSE event types:**
- `snapshot` — initial state dump (nodes + run status)
- `workflow.run.started` — run was submitted
- `workflow.node.started` — a node began executing
- `workflow.node.log` — stdout line from the agent container
- `workflow.node.finished` — a node completed (success or failure)
- `workflow.run.finished` — run reached a terminal state

**Example:**
```
event: snapshot
data: {"kind": "snapshot", "ts": "2026-05-11T10:00:00+00:00", "payload": {...}}

event: workflow.node.started
data: {"kind": "workflow.node.started", "run_id": "...", "node_id": "n1", ...}

: heartbeat

event: workflow.run.finished
data: {"kind": "workflow.run.finished", "run_id": "...", "status": "succeeded"}
```

After the `workflow.run.finished` event the server closes the connection.

### 6.10 Identity Tokens API

The admin service issues RS256-signed identity tokens for agents. The signing key is
an RSA-2048 key pair generated on first startup and stored encrypted in Redis.

#### `POST /identity/tokens`

Issues a signed identity token for an agent slug.

**Request body:**
```json
{
  "slug": "summarizer",
  "name": "Summarizer Agent",
  "team_id": "3f8a2c1d-...",
  "scopes": ["call:litellm", "read:knowledge-base"],
  "ttl_seconds": 2592000
}
```

`name` defaults to `slug` if omitted. `scopes` are stored as the `capabilities`
claim in the JWT.

**Response 200:**
```json
{
  "token": "eyJhbGciOiJSUzI1NiJ9...",
  "expires_at": "2026-06-10T10:00:00+00:00"
}
```

#### `GET /identity/jwks`

Public endpoint (no authentication required). Returns the admin service's RSA public
key in JWK Set format so any service in the gateway can verify identity tokens.

**Response 200:**
```json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "aigw-identity-1",
      "use": "sig",
      "alg": "RS256",
      "n": "...",
      "e": "AQAB"
    }
  ]
}
```

#### `POST /identity/verify`

Verifies an identity token and returns its claims.

**Request body:** `{"token": "eyJhbGciOiJSUzI1NiJ9..."}`

**Response 200 (valid):**
```json
{
  "valid": true,
  "claims": {
    "sub": "summarizer",
    "name": "Summarizer Agent",
    "team_id": "3f8a2c1d-...",
    "capabilities": ["call:litellm", "read:knowledge-base"],
    "exp": 1749546000
  }
}
```

**Response 200 (invalid):**
```json
{"valid": false, "error": "Token has expired"}
```

### 6.11 Awesome Copilot Catalog MCP

The admin service serves an MCP-compatible endpoint that aggregates community agent
instructions and recipes from the Awesome GitHub Copilot community repository. A
background task syncs the catalog every 6 hours.

Endpoint: `GET /mcp/copilot-catalog` — returns the MCP tool/resource manifest for
the catalog. Auto-registered as an MCP server on startup.

### 6.12 CodeMate MCP

The admin service serves an MCP endpoint for SimCorp codebase search tools.

Endpoint: `GET /mcp/codemate` — returns the MCP tool manifest for CodeMate. Requires
SimCorp network access. Auto-registered as an MCP server on startup.

### 6.13 Dashboard and Reports

The admin service exposes dashboard aggregation endpoints used by the admin portal:

- `GET /dashboard` — token usage, cache hit rates, top teams by spend, recent errors
- `GET /reports` — configurable time-range cost reports per team/model/date

### 6.14 Audit Log

Every mutating operation (team create/update/delete, key create/revoke, policy
upsert, budget change, guardrail CRUD) is recorded via `app.audit.record(...)` which
inserts a row into `audit_log`.

#### `GET /audit-log`

Returns recent audit log entries, filterable by resource type, resource ID, and actor.

### 6.15 Configuration

Environment variables for the Admin service:

| Variable | Source / Value | Description |
|---|---|---|
| `DATABASE_URL` | Key Vault ref | Azure Database for PostgreSQL connection |
| `REDIS_URL` | Key Vault ref | Azure Cache for Redis connection |
| `SECRET_KEY` | Key Vault ref | Session signing key |
| `ADMIN_TOKEN` | Key Vault ref | Static bearer token for admin API calls |
| `OIDC_ISSUER` | Entra ID issuer URL | OIDC issuer URL for developer login |
| `OIDC_CLIENT_ID` | Key Vault ref | OIDC client ID (Entra ID app registration) |
| `OIDC_CLIENT_SECRET` | Key Vault ref | OIDC client secret |
| `LITELLM_MASTER_KEY` | Key Vault ref | Master key for LiteLLM calls |
| `AUTH_URL` | `http://auth` | Auth service URL for health checks |
| `CACHE_URL` | `http://cache` | Cache service URL for health checks |
| `LITELLM_URL` | `http://litellm` | LiteLLM URL for health checks |
| `OBSERVABILITY_URL` | `http://observability` | Observability service URL |
| `IDENTITY_KEY_SECRET` | Key Vault ref | Encryption key for RSA signing key in Redis |
| `CORS_ORIGINS` | `["https://dev.aigw.scdom.net"]` | Allowed CORS origins |
| `ALLOWED_EMAIL_DOMAINS` | `[]` (all) | Restrict developer registration to specific email domains |
| `ENVIRONMENT` | `production` | Deployment environment name |

---

Sections 7–17 and Appendices A–D. For sections 1–6 (Auth, Cache, LiteLLM, Observability, Admin, and architecture overview) see `SYSTEM_REFERENCE.md`.

---

## 7. Identity Service (port 8006)

### 7.1 Purpose — Agent DNS / queryable registry

The Identity Service is a queryable registry for all agents in the gateway ecosystem. It acts as "DNS for agents": any workflow, agent, or tool can look up peers by slug, capability tag, category, or partial name match. The service stores agent metadata in PostgreSQL and tracks liveness via Redis heartbeat keys.

On startup it seeds itself from the admin service (`GET /agents`) so that managed agents registered through the portal are immediately discoverable without manual registration.

### 7.2 Agent Registration

Agents register by `POST /agents/register` with a JSON body. Registered agents are stored in the `agent_identities` table. Registration is idempotent: re-posting the same slug performs an upsert, updating all fields and resetting `last_seen`.

If `IDENTITY_SERVICE_TOKEN` is set, the `X-Service-Token` header must match it. In dev mode (empty token), the endpoint is open.

Agents may optionally include an `identity_token` — a signed JWT issued by the admin service (see section 15.3). If provided and valid, `token_verified` is set to `true` on the registration record.

**Registration request fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `slug` | string | yes | Stable identifier, must be unique. URL-safe. |
| `name` | string | yes | Human-readable display name. |
| `category` | string | no | Organisational category (e.g. `utility`, `research`). |
| `capabilities` | string[] | no | Tags describing what this agent can do (e.g. `["code-review", "summarise"]`). |
| `endpoint` | string | no | HTTP endpoint at which the agent can be invoked directly. Empty for relay agents. |
| `team_id` | UUID | no | Owning team UUID for access scoping. |
| `managed` | bool | no | `true` for agents registered through the admin portal; defaults to `false`. |
| `identity_token` | string | no | RS256 JWT for DID-style verified identity (see 15.3). |

### 7.3 Identity Resolution (`GET /resolve/{name}`)

DNS-style resolution that accepts any of: slug, capability tag, or partial name/slug. Returns a ranked list of matching agents:

1. **Exact slug match** — highest priority.
2. **Capability tag match** — agents whose `capabilities` array contains `name`.
3. **Partial ILIKE match** — agents whose `slug` or `name` contains `name` (case-insensitive).

Duplicates are de-duplicated (exact match wins). Online status is populated for every result from Redis heartbeat keys.

### 7.4 Online Status (heartbeat)

An agent is considered **online** when its Redis heartbeat key `identity:online:{slug}` exists. The TTL is 60 seconds. Agents must call `POST /agents/{slug}/heartbeat` at least every 60 seconds to maintain online status.

If the agent was registered via the Agent Relay, a relay token is stored in Redis at `relay:agent:{slug}:token`. In that case, heartbeats must include the matching `X-Relay-Token` header. The check fails open (allows) if no relay token is stored, preventing breakage for managed agents that do not use the relay.

The `aigw-agent serve` command automatically pings the heartbeat endpoint every 30 seconds.

### 7.5 DID Tokens — JWT signing, JWKS

The Identity Service does not issue tokens itself; it verifies them. Tokens are issued by the admin service (see 15.3). When an agent supplies `identity_token` during registration, the Identity Service fetches the admin JWKS from `{admin_url}/identity/jwks`, tries each RSA key, and sets `token_verified = true` if any key verifies the RS256 signature.

### 7.6 All Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | none | Returns `{"status": "ok"}` |
| `GET` | `/agents` | none | List all agents with optional filters |
| `GET` | `/agents/{slug}` | none | Get a single agent by slug |
| `GET` | `/agents/{slug}/identity` | none | Lightweight summary: `token_verified`, `capabilities`, `online` |
| `GET` | `/agents/{slug}/endpoint` | none | Resolve to endpoint URL + online status |
| `POST` | `/agents/{slug}/heartbeat` | X-Relay-Token (if relay) | Refresh online TTL; update `last_seen` |
| `POST` | `/agents/register` | X-Service-Token | Register or upsert an agent identity |
| `DELETE` | `/agents/{slug}` | X-Service-Token | Remove an agent from the registry |
| `GET` | `/resolve/{name}` | none | DNS-style lookup: slug, capability, or partial name |
| `GET` | `/capabilities` | none | List all distinct capability tags across all agents |

**`GET /agents` query parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `capability` | string | Filter to agents that have this capability tag. |
| `category` | string | Filter by category. |
| `team_id` | UUID | Filter by owning team. |
| `managed` | bool | Filter to managed (`true`) or unmanaged (`false`) agents. |

**`AgentIdentity` response shape:**

```json
{
  "id": "uuid",
  "slug": "echo-agent",
  "name": "Echo Agent",
  "category": "utility",
  "capabilities": ["echo", "test"],
  "endpoint": "http://workflow-worker:8000/invoke/echo-agent",
  "team_id": null,
  "managed": true,
  "online": true,
  "token_verified": false,
  "registered_at": "2026-01-15T10:00:00Z",
  "last_seen": "2026-05-11T09:00:00Z"
}
```

### 7.7 Configuration

| Env Var | Source / Value | Description |
|---------|---------|-------------|
| `DATABASE_URL` | Key Vault ref | Azure Database for PostgreSQL connection string |
| `REDIS_URL` | Key Vault ref | Azure Cache for Redis for heartbeat keys |
| `ADMIN_URL` | `http://admin` | Admin service URL for startup seed and JWKS fetch |
| `IDENTITY_SERVICE_TOKEN` | Key Vault ref | Required `X-Service-Token` for register/deregister |

---

## 8. Agent Relay (port 8007)

### 8.1 Purpose — WebSocket tunnel for laptop agents

The Agent Relay allows laptop-hosted or CI-hosted agents to participate in workflow runs without exposing any inbound network port. The agent initiates an outbound WebSocket connection and waits for invocations; the relay brokers them to the workflow worker.

### 8.2 Registration Protocol

Before opening the WebSocket, the agent performs an HTTP registration:

```
POST /register
{
  "slug": "my-agent",
  "name": "My Agent",
  "capabilities": ["code-review"]
}
```

Response:
```json
{
  "relay_token": "550e8400-e29b-41d4-a716-446655440000",
  "slug": "my-agent"
}
```

The `relay_token` is a UUID that acts as a session credential for the WebSocket connection. It is stored in memory and in Redis at `relay:agent:{slug}:token` with a 1-hour TTL for multi-instance routing.

If `AGENT_RELAY_SECRET` is set, the `X-Relay-Secret` header must match it on all HTTP calls (`/register` and `/invoke`). The WebSocket path itself is not authenticated — possession of a valid `relay_token` is sufficient.

### 8.3 WebSocket Message Format

The agent connects to `WS /connect/{relay_token}`. Once connected, it receives **invoke** messages and must reply with **result** messages.

**Invoke message (relay → agent):**
```json
{
  "invocation_id": "uuid",
  "inputs": { "key": "value" },
  "env": { "AIGW_RUN_ID": "uuid", "AIGW_NODE_ID": "n1", "AIGW_BASE_URL": "http://cache", "AIGW_API_KEY": "sk-..." },
  "run_id": "uuid",
  "node_id": "n1"
}
```

**Result message (agent → relay):**
```json
{
  "invocation_id": "uuid",
  "outputs": { "result": "processed" },
  "exit_code": 0
}
```

The `invocation_id` must be echoed back so the relay can match the response to the correct pending future.

### 8.4 Invocation Flow

1. Workflow worker calls `POST /invoke/{slug}` with `{inputs, env, run_id, node_id}`.
2. Relay looks up the relay token for `slug` in memory (falls back to Redis for multi-instance coordination).
3. Relay sends an invoke message to the agent's WebSocket.
4. Relay awaits a result message on an `asyncio.Future` (timeout: 300 seconds).
5. On response, relay returns `{outputs, exit_code}` to the workflow worker.
6. On timeout, relay returns HTTP 504.
7. On disconnect, relay returns HTTP 503.

### 8.5 Security (`X-Relay-Secret`)

When `AGENT_RELAY_SECRET` is configured:
- `POST /register` requires `X-Relay-Secret: <secret>` — prevents unauthorised agents from claiming slots.
- `POST /invoke/{slug}` requires `X-Relay-Secret: <secret>` — prevents external callers from triggering agent invocations.
- The workflow worker sends `X-Relay-Secret` automatically from its `AGENT_RELAY_SECRET` env var.

In dev mode (empty secret), all callers are allowed.

### 8.6 Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | none | Returns `{"status": "ok"}` |
| `GET` | `/agents` | none | List metadata for all currently connected agents (slug, name, capabilities, connected_at). `relay_token` is intentionally omitted. |
| `POST` | `/register` | X-Relay-Secret | Register an agent; returns relay_token |
| `WS` | `/connect/{relay_token}` | relay_token in path | Agent WebSocket tunnel |
| `POST` | `/invoke/{agent_slug}` | X-Relay-Secret | Invoke a relay agent by slug; waits for result |

### 8.7 Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `REDIS_URL` | `redis://redis:6379/0` | Redis for relay token persistence and multi-instance routing |
| `AGENT_RELAY_SECRET` | `""` (open) | Shared secret for `/register` and `/invoke`. Empty = dev mode (no auth). |

---

## 9. AI Librarian (port 8008)

### 9.1 Knowledge Base

The Librarian maintains a shared knowledge base of research documents stored in PostgreSQL (`knowledge_items` table) with embeddings cached in Redis. Documents have a `topic`, `tags`, `title`, `content`, `source_url`, and a Redis key pointing to their embedding vector.

The database schema:
```sql
knowledge_items (
  id UUID PRIMARY KEY,
  title TEXT,
  content TEXT,
  source_url TEXT,
  topic TEXT,
  tags TEXT[],
  embedding_key TEXT,   -- Redis key: lib:embed:{id}
  ingested_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ
)

research_topics (
  id UUID PRIMARY KEY,
  topic TEXT UNIQUE,
  description TEXT,
  search_query TEXT,
  last_researched_at TIMESTAMPTZ,
  interval_seconds INT,  -- default 3600
  enabled BOOLEAN
)
```

### 9.2 Semantic Search (how it works)

Search is a two-stage pipeline:

1. **Postgres filter** — if `topic` or `tags` are specified, filter rows in Postgres first. Without filters, fetch the 500 most recently ingested items.
2. **Cosine similarity in memory** — fetch all embedding vectors from Redis in a single `MGET` call, compute cosine similarity against the query embedding, sort by score, return the top-N results.

Documents without an embedding (e.g. if the embedding API was unavailable at ingest time) receive a similarity score of 0.0 and appear last. The result set includes the score as `score` (rounded to 4 decimal places).

### 9.3 Research Agent Loop

A background asyncio task runs continuously, polling for stale research topics. On startup it waits 30 seconds for other services to be ready, then checks every `RESEARCH_INTERVAL_SECONDS` (default: 3600).

A topic is considered stale if `last_researched_at IS NULL` or `last_researched_at < NOW() - interval_seconds`.

For each stale topic the loop:
1. Calls `POST http://cache/v1/chat/completions` with `gpt-4o-mini` (gateway routes this to the configured provider).
2. The system prompt requests a structured JSON response: `{"title": "...", "content": "...", "tags": [...]}`.
3. Parses the JSON and calls `ingest_document()` to embed and persist it.
4. Updates `last_researched_at = NOW()`.

#### Default Research Topics

The following topics are seeded on first startup:

| Topic slug | Description | Default interval |
|------------|-------------|-----------------|
| `ai-coding` | AI-assisted software development, LLM coding agents, best practices | 1 hour |
| `saas-best-practices` | SaaS architecture, multi-tenancy, developer experience | 2 hours |
| `security-sdlc` | SAST, DAST, supply chain security, DevSecOps | 2 hours |
| `platform-engineering` | Internal developer platforms, golden paths, DORA/SPACE metrics | 2 hours |

#### Adding a Topic

`POST /research/topics` with:
```json
{
  "topic": "my-topic",
  "description": "Optional description",
  "search_query": "Full query sent to the LLM for research",
  "interval_seconds": 7200
}
```

#### Manual Trigger

`POST /research/topics/{topic}/trigger` — queues an immediate research run for the named topic as a background task. Returns `{"status": "triggered", "topic": "..."}` immediately.

### 9.4 MCP Server (tools: search, ingest, topics)

The Librarian exposes a JSON-RPC 2.0 MCP server at `POST /mcp`. Three tools are available:

**`search`** — semantic knowledge base search.
**`ingest`** — add a document (requires `X-Service-Token` if `LIBRARIAN_SERVICE_TOKEN` is set).
**`topics`** — list all topics with item counts.

Full schemas are in Appendix C.

### 9.5 SSE Transport

`GET /mcp/sse` opens an HTTP+SSE stream. The first event is `event: endpoint` with the `POST /mcp` URL as data. Subsequent events relay JSON-RPC responses for any POSTs the client makes to that URL. A keepalive comment (`: keepalive`) is sent every 15 seconds.

### 9.6 All Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | none | `{"status": "ok"}` |
| `POST` | `/ingest` | X-Service-Token | Ingest a document (title, content, topic, tags, source_url) |
| `GET` | `/search` | none | Semantic search (`q`, `topic`, `tags`, `limit`) |
| `GET` | `/topics` | none | List topics with item counts |
| `GET` | `/topics/{topic}` | none | List items for a topic (`limit` query param) |
| `DELETE` | `/items/{item_id}` | none | Delete a knowledge item and its embedding |
| `GET` | `/research/topics` | none | List all research topic configs |
| `POST` | `/research/topics` | none | Create a research topic |
| `POST` | `/research/topics/{topic}/trigger` | none | Manually trigger research for a topic |
| `DELETE` | `/research/topics/{topic}` | none | Delete a research topic |
| `GET` | `/mcp` | none | MCP manifest (name, version, tools list) |
| `POST` | `/mcp` | none / X-Service-Token (ingest) | JSON-RPC 2.0 MCP endpoint |
| `GET` | `/mcp/sse` | none | HTTP+SSE MCP transport |
| `GET` | `/mcp/manifest` | none | MCP manifest |
| `GET` | `/mcp/tools` | none | List tools (for admin ping_server) |
| `POST` | `/mcp/tools/search` | none | Direct REST call to search tool |
| `POST` | `/mcp/tools/ingest` | X-Service-Token | Direct REST call to ingest tool |
| `POST` | `/mcp/tools/topics` | none | Direct REST call to topics tool |

**Ingest validation rules:**
- `content` must not exceed 50,000 characters.
- `source_url`, if provided, must start with `http://` or `https://`.
- `tags` must not exceed 20 items, each at most 50 characters.

### 9.7 Configuration

| Env Var | Source / Value | Description |
|---------|---------|-------------|
| `DATABASE_URL` | Key Vault ref | Azure Database for PostgreSQL connection |
| `REDIS_URL` | Key Vault ref | Azure Cache for Redis for embeddings cache |
| `EMBEDDING_API_KEY` | Key Vault ref | Gateway API key for embedding calls (routed via LiteLLM) |
| `EMBEDDING_BASE_URL` | `http://litellm/v1` | Base URL for embedding API (via LiteLLM) |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model name |
| `CACHE_URL` | `http://cache` | Cache service URL (used by research loop for LLM calls) |
| `RESEARCH_INTERVAL_SECONDS` | `3600` | How often the background loop polls for stale topics |
| `CORS_ORIGINS` | `https://dev.aigw.scdom.net` | Comma-separated allowed CORS origins |
| `LIBRARIAN_SERVICE_TOKEN` | Key Vault ref | Token required on `X-Service-Token` for ingest endpoints |

---

## 10. Workflow Designer

### 10.1 Concepts

| Concept | Description |
|---------|-------------|
| **Workflow** | A named, versioned DAG definition. Stored in `workflows` + `workflow_versions` tables in admin's PostgreSQL. |
| **Version** | An immutable snapshot of a workflow DAG. Identified by integer `version` number. New edits create a new version. |
| **Run** | One execution of a specific workflow version. Stored in `workflow_runs`. Has a `status` (pending → running → succeeded / failed / cancelled) and scoped API key. |
| **Node** | A single unit of work in the DAG. Maps to one agent invocation. Stores per-run state in `run_nodes`. |
| **Edge** | A directed connection between two nodes. Carries an optional `condition` expression evaluated against the predecessor's outputs. |

### 10.2 DAG JSON Format — Full Specification

The `dag` column in `workflow_versions` is a JSONB document. Schema version: 0.5.

```json
{
  "entry_node": "fetch",
  "nodes": [
    {
      "id": "fetch",
      "agent_slug": "web-fetcher",
      "inputs": {
        "url": "https://example.com"
      }
    },
    {
      "id": "classify",
      "agent_slug": "content-classifier",
      "inputs": {}
    },
    {
      "id": "summarise",
      "agent_slug": "summariser",
      "inputs": {},
      "loop": {
        "enabled": true,
        "max_iterations": 5
      }
    },
    {
      "id": "notify-slack",
      "agent_slug": "slack-notifier",
      "inputs": {}
    },
    {
      "id": "notify-email",
      "agent_slug": "email-notifier",
      "inputs": {}
    }
  ],
  "edges": [
    {
      "from": "fetch",
      "to": "classify",
      "condition": null
    },
    {
      "from": "classify",
      "to": "summarise",
      "condition": "outputs.category == \"article\""
    },
    {
      "from": "classify",
      "to": "notify-email",
      "condition": "outputs.category == \"spam\""
    },
    {
      "from": "summarise",
      "to": "notify-slack",
      "condition": null
    },
    {
      "from": "summarise",
      "to": "notify-email",
      "condition": null
    }
  ]
}
```

This example shows:
- **Entry node** — `fetch` is the first node enqueued when a run starts.
- **Conditional edges** — `classify` fans out to `summarise` or `notify-email` based on `outputs.category`.
- **Loop node** — `summarise` loops up to 5 times while `_loop_continue: true` appears in its outputs.
- **Parallel fan-out** — `summarise` has two outgoing unconditional edges; both `notify-slack` and `notify-email` start in parallel when `summarise` succeeds.

### 10.3 Node Spec Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | yes | Node identifier; must be unique within the DAG |
| `agent_slug` | string | yes | Slug of the agent to execute (looked up in `agents` table) |
| `inputs` | object | no | Default input values; merged with predecessor outputs and run-level inputs |
| `loop` | object or bool | no | Loop configuration (see 10.5). `true` is shorthand for `{"enabled": true, "max_iterations": 10}` |

### 10.4 Edge Condition Syntax

Conditions are simple binary comparisons of the form:

```
<dotted.path> <operator> <literal>
```

- **Path** — dot-separated key path into the predecessor node's `outputs` dict. The prefix `outputs.` is optional and stripped automatically.
- **Operators** — `==`, `!=`, `>`, `>=`, `<`, `<=`
- **Literals** — quoted string (`"value"` or `'value'`), integer, float, `true`, `false`, `null`

Examples:
```
outputs.status == "success"
outputs.score > 0.8
outputs._loop_continue == true
outputs.category != "spam"
result.count >= 10
```

A `null` or missing `condition` is an unconditional edge — it always fires. If a condition cannot be parsed, it evaluates to `false` (edge does not fire).

### 10.5 Loop Node Behaviour

A node with `loop.enabled: true` re-enqueues itself after each successful iteration if:
1. The iteration count is less than `max_iterations - 1` (0-indexed; default max is 10).
2. The node's `outputs` contain `_loop_continue: true`.

If either condition is not met, the loop exits and outgoing edges are evaluated normally. Loop iterations are tracked by an `iteration` counter in `run_nodes` and `work_queue`.

### 10.6 Running a Workflow (`POST /runs`)

Workflow runs are submitted to the admin service:

```
POST /runs
Authorization: Bearer <api-key>

{
  "workflow_id": "uuid",
  "version": 1,
  "inputs": { "key": "value" },
  "team_id": "uuid"
}
```

On submission the admin service:
1. Creates a `workflow_runs` row with `status = pending`.
2. Issues a short-lived **scoped API key** (`workflow-run` scope) tied to this run.
3. Stores the plaintext key in Redis at `workflow:scoped_key:{run_id}` (TTL 61 minutes).
4. Inserts the entry node into `run_nodes` and `work_queue`.

The workflow worker claims the queued item and begins execution.

### 10.7 Live Run Viewer (SSE)

Run state changes and agent log lines are published to Redis pubsub on channel `workflow:events:{run_id}`. The admin service streams these to clients as Server-Sent Events.

Event types published:
- `node_started` — node began running (includes `agent_id`)
- `node_log` — a log line from the agent container (first 1,000 characters)
- `node_finished` — node completed (status, outputs, error)
- `run_finished` — the entire run completed (status)

The Developer Portal's live run viewer subscribes to these events and renders a real-time node status graph.

### 10.8 Worker Internals

**Claim loop** — the worker polls `work_queue` using `SELECT ... FOR UPDATE SKIP LOCKED` every `WORKER_POLL_INTERVAL_S` seconds (default: 1.0). Concurrency is bounded by a semaphore of size `WORKER_CONCURRENCY` (default: 5). A claim is marked with `claimed_by = {worker_id}` and `claim_expires = NOW() + {claim_ttl_s}`.

**Sweeper** — a background task runs every `WORKER_SWEEPER_INTERVAL_S` (default: 30s). It resets `claimed_by = NULL` for any rows where `claim_expires < NOW()`, recovering jobs from crashed workers. It also purges the corresponding `workflow:scoped_key:{run_id}` from Redis to prevent credential leakage.

**DAG advancement** — after a node finishes successfully, the worker calls `ready_successors()` to find nodes whose predecessors have all `succeeded` and whose edge conditions are satisfied. Each ready successor is inserted into `run_nodes` and `work_queue`. If the finished node is terminal (no outgoing edges) and all nodes in the run have succeeded, the run is marked `succeeded`.

**Docker dispatch** — for standard agents, the worker spawns a sibling Docker container via the host `docker.sock`. Inputs are written to `{HOST_RUNS_PATH}/{run_id}/{node_id}/inputs.json`; the same directory is bind-mounted into the container at `/run`. After the container exits, `outputs.json` is read back. The container runs with `ReadonlyRootfs`, `CapDrop: ALL`, and `no-new-privileges` security settings. AutoRemove is disabled so the worker can inspect the exit code before cleanup.

**Relay dispatch** — for agents whose `image` starts with `relay://`, the worker uses the RelayRuntime, which POSTs to `POST {AGENT_RELAY_URL}/invoke/{slug}` with the same `X-Relay-Secret` header.

### 10.9 Scoped API Keys for Agent Containers

Each run has a scoped API key injected into every agent container as `AIGW_API_KEY`. This key has `scope = workflow-run` and is tied to the run's team. It is revoked automatically when the run finishes (either by the worker in `_mark_run_finished()` or by the sweeper on stale claims).

The cache service enforces that `workflow-run` scoped keys may **only** call `/v1/chat/completions*` — all other paths return 403.

### 10.10 DAG Compile-time Security Linting

When a new workflow version is submitted via `POST /workflows/{id}/versions`, the admin service validates the following security invariants before accepting the DAG:

| Check | Rule | Error |
|---|---|---|
| Node count | Max 50 nodes | 422 — exceeds maximum node count |
| Loop bound | `loop.max_iterations` ≤ 10 | 422 — exceeds limit of 10 |
| Image format | Must match `registry/image:tag` or `relay://slug` | 422 — invalid image format |
| Edge conditions | Must match `field.path OP value` syntax | 422 — invalid condition syntax |
| Reachability | Every node must be reachable from `entry_node` | 422 — Unreachable nodes detected |

These checks implement the **Configuration-level validation** layer from the gh-aw security architecture.

### 10.11 SafeOutputs Security Patterns (gh-aw)

The workflow worker implements three safety layers derived from gh-aw's SafeOutputs subsystem:

#### Input Sanitization (`services/workflow-worker/app/sanitizer.py`)
Applied to `inputs.json` before the agent container launches:
- `@mention` strings replaced with `(mention redacted)`
- `<` and `>` HTML-escaped to `&lt;` / `&gt;`
- Individual strings truncated at 50,000 chars
- Total key count capped at 100 keys
- Total payload size capped at 1 MB

#### Output Threat Detection (`services/workflow-worker/app/threat_detection.py`)
After each node completes, `outputs.json` is scanned **before DAG advancement**:
- Scoped key patterns (`aigw_run_*`)
- API key patterns (Anthropic, OpenAI, GitHub, JWT, private key headers)
- Prompt injection phrases ("ignore previous instructions", etc.)
- Enriched from admin guardrails on startup; defaults apply if admin unreachable
- Fail-open: unreachable guardrails service → allow through
- On detection: run marked `failed` with `error="threat-detection-blocked"`, run halted

#### Secret Redaction
After reading `outputs.json`, `aigw_run_*` patterns are redacted to `[REDACTED]` before DB persistence, preventing scoped keys from appearing in `workflow_runs.outputs`.

---

## 11. Agents

### 11.1 Agent Contract

Agents are executables (typically Docker containers) that follow a simple file-based contract:

**Input:** read from `/run/inputs.json` at startup. This is a JSON object with keys set by the workflow node spec and predecessor outputs.

**Output:** write to `/run/outputs.json` before exiting. Must be a valid JSON object. The file is pre-created as `{}` by the worker so that a crash still produces valid output.

**Exit code:** `0` = success; non-zero = failure. The worker treats non-zero exit codes as node failures.

### 11.2 Required Env Vars

These environment variables are injected into every agent container by the workflow worker:

| Variable | Description |
|----------|-------------|
| `AIGW_RUN_ID` | UUID of the current workflow run |
| `AIGW_NODE_ID` | ID of the current node within the DAG |
| `AIGW_BASE_URL` | Base URL of the cache service (`http://cache`) — use this for LLM API calls |
| `AIGW_API_KEY` | Scoped API key for the current run (scope: `workflow-run`). Revoked when the run ends. |

### 11.3 Manifest Schema

Each agent has a `manifest.json` file that describes its interface. This is uploaded when registering the agent via `POST /agents`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `slug` | string | yes | Unique identifier. URL-safe. Used in DAG `agent_slug` fields and relay `relay://` URIs. |
| `name` | string | yes | Human-readable display name. |
| `description` | string | yes | What the agent does. Shown in the portal agent catalog. |
| `image` | string | yes | Docker image name (e.g. `ai-gateway-echo-agent:dev`), or `relay://{slug}` for relay agents. |
| `category` | string | no | Organisational category (e.g. `utility`, `research`, `integration`). |
| `managed` | bool | no | `true` for agents registered and managed through the portal. Default: `false`. |
| `inputs_schema` | JSON Schema object | no | JSON Schema describing the expected structure of `inputs.json`. |
| `outputs_schema` | JSON Schema object | no | JSON Schema describing the structure of `outputs.json`. |

Full example (echo-agent):
```json
{
  "slug": "echo-agent",
  "name": "Echo Agent",
  "description": "Returns its inputs verbatim under an `echoed` key. Use for smoke tests and as a workflow-designer canvas template.",
  "image": "ai-gateway-echo-agent:dev",
  "category": "utility",
  "managed": true,
  "inputs_schema": {"type": "object"},
  "outputs_schema": {
    "type": "object",
    "properties": {
      "echoed": {"type": "object"},
      "agent": {"const": "echo-agent"}
    },
    "required": ["echoed", "agent"]
  }
}
```

### 11.4 Building an Agent (Dockerfile pattern)

A minimal agent container:

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agent.py .

CMD ["python", "agent.py"]
```

```python
# agent.py
import json, os

inputs_path = "/run/inputs.json"
outputs_path = "/run/outputs.json"

with open(inputs_path) as f:
    inputs = json.load(f)

# ... do work using inputs and AIGW_* env vars ...

outputs = {"result": "done", "inputs_received": inputs}

with open(outputs_path, "w") as f:
    json.dump(outputs, f)
```

The `/run` directory is bind-mounted by the workflow worker at runtime; the image does not need to include it.

### 11.5 Registering an Agent

```
POST /agents
Authorization: Bearer <admin-api-key>
Content-Type: application/json

{
  "slug": "my-agent",
  "name": "My Agent",
  "image": "registry.internal/my-agent:1.0.0",
  "description": "Processes incoming requests",
  "category": "integration",
  "managed": true,
  "inputs_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
  "outputs_schema": {"type": "object", "properties": {"answer": {"type": "string"}}}
}
```

Agents can also be registered from the portal (Admin: MCP / Agents section) or via the agent manifest file.

### 11.6 Relay Agents (`relay://` image prefix)

When an agent's `image` field starts with `relay://`, the workflow worker uses the `RelayRuntime` instead of Docker. The slug is extracted from the URI:

```
"image": "relay://my-laptop-agent"
```

The worker sends `POST {AGENT_RELAY_URL}/invoke/my-laptop-agent` with the inputs and env vars. The relay forwards this to whatever laptop/CI process has registered that slug and opened a WebSocket connection.

This allows agents running on developer laptops or CI machines to participate in production workflows without any inbound network exposure.

### 11.7 aigw-agent CLI

The `aigw-agent` package (`pip install -e packages/aigw-agent`) provides two commands:

**Serve a local agent:**
```
aigw-agent serve <script_or_dir> [OPTIONS]

Arguments:
  SCRIPT_OR_DIR   Path to a Python script or a directory containing main.py

Options:
  --relay-url URL    Agent relay base URL (e.g. https://dev.aigw.scdom.net/agent-relay)
  --slug SLUG        Agent slug (default: script filename stem)
  --name NAME        Human-readable name (default: slug)
```

When a directory is passed, `main.py` inside it is used as the script.

The serve command:
1. Registers the agent with the relay (`POST /register`).
2. Opens a WebSocket to `WS /connect/{relay_token}`.
3. Displays a live Rich table showing connection status and invocation counts.
4. On each invoke message, runs the script as a subprocess with `AIGW_INPUTS_PATH` and `AIGW_OUTPUTS_PATH` set to temporary files, then sends back the outputs.
5. Pings `POST {identity_url}/agents/{slug}/heartbeat` every 30 seconds so the agent appears online in the Identity Service.

**Environment:** `IDENTITY_URL` — override the Identity Service URL. Default is the relay URL with `:8007` replaced by `:8006`.

**Check connected agents:**
```
aigw-agent status [--relay-url URL]
```

Calls `GET /agents` on the relay and prints a table of currently connected agents (slug, name, capabilities, connection time).

### 11.8 Autonomous Agents (`_spawn` output)

An agent can trigger a sub-workflow by including a `_spawn` key in its `outputs.json`:

```json
{
  "result": "done",
  "_spawn": {
    "workflow_id": "uuid-of-workflow-to-trigger",
    "version": 1,
    "inputs": { "parent_result": "done" }
  }
}
```

The workflow worker intercepts `_spawn` and calls `POST {admin_url}/runs` with:
- Only `workflow_id`, `version`, and `inputs` from the agent-supplied payload (other keys are stripped).
- `team_id` injected from the parent run (the agent cannot escalate to a different team).
- `triggered_by = "workflow-worker-spawn"` and `triggered_by_kind = "system"`.

This is fire-and-forget: the parent workflow node does not wait for the spawned sub-workflow.

---

## 12. MCP Servers

### 12.1 Protocol (JSON-RPC 2.0 + SSE transport)

All MCP servers in the gateway implement the [Model Context Protocol](https://spec.modelcontextprotocol.io) version `2024-11-05`. The protocol uses JSON-RPC 2.0 over HTTP POST, with an optional HTTP+SSE transport for clients that require it.

**Request/Response shape:**
```json
// Request
{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "search", "arguments": {...}}}

// Success response
{"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "..."}]}}

// Error response
{"jsonrpc": "2.0", "id": 1, "error": {"code": -32601, "message": "Tool not found: foo"}}
```

**Notifications** (requests without `id`) always receive HTTP 204 with no body.

### 12.2 Awesome Copilot Catalog

Served by the admin service. Syncs content hourly from the [github/awesome-copilot](https://github.com/github/awesome-copilot) repository on GitHub.

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/mcp/copilot-catalog` | MCP manifest |
| `GET` | `/mcp/copilot-catalog/tools` | List tools |
| `POST` | `/mcp/copilot-catalog` | JSON-RPC 2.0 MCP endpoint |
| `GET` | `/mcp/copilot-catalog/sse` | HTTP+SSE transport |
| `GET` | `/mcp/copilot-catalog/items` | List all catalog items (REST) |
| `GET` | `/mcp/copilot-catalog/items/{id}` | Get a catalog item by ID (REST) |
| `POST` | `/mcp/copilot-catalog/sync` | Trigger immediate sync from GitHub |
| `GET` | `/mcp/copilot-catalog/meta` | Catalog metadata (last sync, item counts) |

**Tools:**

| Tool | Description |
|------|-------------|
| `search` | Search the catalog by keyword. Optional `kind` filter: `agent`, `instruction`, `recipe`. |
| `list` | List all items of a given `kind`. |
| `get` | Get full details of a catalog item by `id`. |

**Sync:** The catalog is synced from GitHub in the background on startup and then every hour. Items are parsed from the awesome-copilot repository's agents/, instructions/, and recipes/ directories. Synced content is stored in Redis.

### 12.3 CodeMate Tools

A proxy to the SimCorp CodeMate MCP server at `https://mcp.prod.codemate.az.scdom.net/tools/api/mcp`. Requires SimCorp network access.

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/mcp/codemate` | MCP manifest (fetches from upstream if reachable, falls back to cached) |
| `GET` | `/mcp/codemate/tools` | List tools |
| `POST` | `/mcp/codemate` | JSON-RPC 2.0 MCP endpoint |
| `GET` | `/mcp/codemate/sse` | HTTP+SSE transport |
| `POST` | `/mcp/codemate/tools/{tool_name}` | Direct REST proxy to upstream tool |

**Tools:**

| Tool | Description |
|------|-------------|
| `codebase_search__search_code` | Search SimCorp codebase by natural language or symbol name |
| `codebase_search__find_system_objects_by_caption` | Find SimCorp system objects (forms, views, workflows) by caption text |

### 12.4 AI Librarian MCP

Served by the Librarian service (port 8008).

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/mcp` | MCP manifest |
| `POST` | `/mcp` | JSON-RPC 2.0 MCP endpoint |
| `GET` | `/mcp/sse` | HTTP+SSE transport |

**Tools:** `search`, `ingest`, `topics` (see Appendix C for full schemas).

### 12.5 VS Code / Copilot Agent Setup (`.vscode/mcp.json`)

The repository includes a `.vscode/mcp.json` that configures four MCP servers for VS Code Copilot:

```json
{
  "servers": {
    "codematetools": {
      "type": "http",
      "url": "https://mcp.prod.codemate.az.scdom.net/tools/api/mcp"
    },
    "ai-gateway-catalog": {
      "type": "sse",
      "url": "https://dev.aigw.scdom.net/api/admin/mcp/copilot-catalog/sse"
    },
    "ai-gateway-codemate": {
      "type": "sse",
      "url": "https://dev.aigw.scdom.net/api/admin/mcp/codemate/sse"
    },
    "ai-librarian": {
      "type": "sse",
      "url": "https://dev.aigw.scdom.net/api/librarian/mcp/sse"
    }
  }
}
```

`codematetools` connects directly to the upstream SimCorp server. The three `ai-gateway-*` entries connect through the gateway, which provides authentication and audit logging. All four servers are available in Copilot Chat once the developer is on the corporate VPN.

### 12.6 MCP Protocol Details

The gateway's `MCPServer` class (`services/admin/app/mcp_protocol.py`) implements the following methods:

| Method | Description |
|--------|-------------|
| `initialize` | Returns `protocolVersion`, `capabilities`, and `serverInfo`. Required handshake before any tool calls. |
| `notifications/initialized` | Client notification confirming handshake. Server responds with HTTP 204. |
| `tools/list` | Returns the full list of registered tools with their `inputSchema`. |
| `tools/call` | Dispatches to the named tool handler. Returns `{"content": [{"type": "text", "text": "<json>"}]}`. |
| `ping` | Returns `{}` — used for keep-alive checks. |

All error responses use standard JSON-RPC 2.0 error codes:
- `-32601` — Method or tool not found.
- `-32603` — Internal tool execution error.

---

## 13. Admin Portal (port 3001)

The Admin Portal is a Next.js application running as the Docker Compose service `admin-portal` (container port 3001), reached via the gateway FQDN at `https://dev.aigw.scdom.net/admin`. It is aimed at platform engineers and team administrators managing the gateway on behalf of ~2,000 engineers.

### `/admin/dashboard` — Platform Overview

System overview page with real-time gauges and charts. Key panels:

- **System performance** — arc gauges for cache hit rate, active sessions, error rate.
- **Request volume & cache hits** — time-series chart of total requests vs cache hits.
- **Top teams by spend** — ranked list of teams with current month spend.
- **Model mix** — spend breakdown by model.
- **Provider health** — live status of each configured provider.
- **Cache** — live cache statistics (hit rate, total entries).
- **Recent activity** — last N requests with status codes.
- **Active alerts** — list of firing budget and health alerts.

### `/admin/teams` — Team Management

List all teams with their spend, member count, and status. Supports creating new teams and searching. Each team row links to the team detail page.

### `/admin/teams/[id]` — Team Detail

Detailed view of a single team with tabbed sections:
- **Members** — list team members with roles, add/remove members.
- **API Keys** — list and revoke API keys scoped to this team.
- **Budget** — current month spend vs budget cap, with a spend history chart.
- **Policies** — cache and rate-limiting policy configuration for this team.

### `/admin/areas` — Area / Department Management

Areas are the organisational grouping above teams (e.g. a business unit or department). This page lists all areas with their description and team count. Supports creating, editing, and deleting areas.

### `/admin/users` — User Management

Lists all user accounts with their display name, email, team membership, and role. Supports searching and editing user details.

### `/admin/models` — Model Registry

Lists all available AI models with their provider, enabled/disabled status, and display name. Admins can toggle models on or off gateway-wide; disabled models are rejected at the auth layer.

### `/admin/providers` — Provider Configuration + Auto-Drive

Lists configured AI providers (OpenAI, Anthropic, Google, GitHub Models) with their API key status. The **Auto-Drive** feature automatically selects the lowest-cost provider for a given capability at runtime. Admins can configure Auto-Drive rules and view provider health metrics.

### `/admin/policies` — Per-Team Cache & Rate Limit Policies

Shows all policy overrides with their team association. Policies control:
- Semantic cache similarity threshold (override of the global default `0.90`).
- Cache TTL (seconds).
- Rate limit (requests per minute).
- Per-model rate limits.

Supports creating, editing, and deleting policy rows.

### `/admin/guardrails` — Content Filtering Rules

Manages content guardrails applied to all requests:
- **Active guardrails** — list of rules with type, description, and toggle to enable/disable.
- **Recent hits** — log of requests that triggered a guardrail.
- **Coverage** — percentage of requests passing through each active rule.

Guardrail types include `pii_detector` and custom pattern rules.

### `/admin/mcp` — MCP Server Registry

Registry of MCP servers known to the gateway. The admin service pings each registered server at startup to verify it is reachable and to discover its tools. This page shows:
- Registered MCP servers with their URL, auth type, and last-seen status.
- Per-server tool list.
- Ability to register new external MCP servers or edit/remove existing ones.

### `/admin/plugins` — Plugin Catalog

Similar to the MCP server registry but for plugins. Plugins are registered by URL and support Browse, enable/disable, and documentation display. This page also contains the Copilot Catalog browser (content synced from awesome-copilot).

### `/admin/skills` — Skills (stub)

Governance view for published agent skills. Allows reviewing skill versions, model usage, and promotion status from draft through to org-wide availability. Currently a planning stub — full functionality is under development.

### `/admin/requests` — Recent Requests Log

Live feed of recent API requests across all teams. Shows request ID, team, model, tokens, cost, cache status, and latency. Supports filtering by team, model, and status.

### `/admin/audit` — Audit Log

Queryable audit log of all administrative actions (team changes, API key operations, policy edits, guardrail changes). Columns include timestamp, actor, action, resource, and outcome.

### `/admin/reports` — Usage Reports

Cost reports showing spend over time, broken down by team, model, and provider. Includes CSV export.

### `/admin/alerts` — Budget Alerts

Three panels:
- **Active alerts** — currently firing budget and health threshold alerts.
- **Rule index** — configured alert rules with threshold values and notification channels.
- **Channels** — configured Slack-compatible webhook endpoints for alert delivery.

### `/admin/approvals` — Approval Queue

Queue for requests requiring manual approval: expanded tool scopes, skill publishes, and policy exceptions. Approval workflows route here based on team-level risk thresholds. Currently a planning stub.

### `/admin/devops` — DevOps AI Agent Chat

An AI chat interface backed by `POST /devops-agent/chat` on the admin service. The agent has read-only access to live gateway data and can call these tools:

| Tool | Description |
|------|-------------|
| `check_service_health` | Check health status of all services |
| `get_gateway_metrics` | Retrieve current traffic and performance metrics |
| `get_recent_errors` | Fetch and analyse recent API errors |
| `get_budget_status` | Check team budget utilisation |
| `get_model_usage` | Show model usage statistics for a period |
| `get_audit_log` | Query recent audit log entries |
| `get_top_teams_by_spend` | Ranked spend leaderboard |

Pre-built suggested prompts include "Full health check", "Error analysis", "Budget overview", and "Optimisation tips". The agent cannot modify configuration or restart services.

### `/admin/insights` — AI-Generated Insights Panel

Displays AI-generated operational insights from the agentic optimisation worker. Each insight card shows:
- **Severity** — Critical, Warning, or Info.
- **Category** — cache, model, budget, error, health, or usage.
- **Title and description** — the insight text.
- **Suggested action** — if the insight has a recommended remediation.
- **Team** — which team the insight is about (if applicable).
- **Auto-applied** flag — whether the suggested action was automatically enacted.

Insights can be dismissed individually. The backend endpoint is `/insights` on the admin service.

### `/admin/cache` — Cache Stats and Invalidation

Detailed semantic cache statistics:
- **Hit rate over time** — chart of cache hit/miss ratio.
- **Similarity distribution** — histogram of cosine similarity scores for semantic hits.
- **Default policy** — global cache threshold and TTL settings with edit capability.
- **Per-team overrides** — list of teams with custom cache policies.
- **Top cached prompts** — most frequently cache-hit prompts.

### `/admin/quotas` — Quotas & Budgets

Organisation-level budget overview:
- **Org-level budget** — total MTD spend vs org cap.
- **Per-team budgets** — table of all teams with their May 2026 spend and cap.
- **Forecast vs cap** — chart of projected monthly spend against the org budget cap.

---

## 14. Developer Portal (port 3002)

The Developer Portal is a Next.js application running as the Docker Compose service `portal` (container port 3002), reached via the gateway FQDN at `https://dev.aigw.scdom.net/`. It is aimed at the ~2,000 engineers consuming the gateway.

### `/portal` — Home Dashboard

Personalised welcome page showing:
- Recent request history for the developer's API keys.
- Quick-access links to API keys, playground, workflows, and documentation.
- Current month spend summary.

### `/playground` — LLM Playground

Interactive playground for testing models. Supports:
- Model selector (all gateway-enabled models).
- System prompt and multi-turn conversation.
- Temperature and max-tokens sliders.
- Token count and cost estimate.
- Copy-as-curl and copy-as-code buttons.

### `/agents` — Agent Catalog + Identity Search

Browse all registered agents from the Identity Service. Features:
- Search by name, capability, or category.
- Online/offline status indicators (live from heartbeat).
- DID token verification badge.
- Links to the agent's manifest and endpoint.

### `/workflows` — Workflow List

List all workflows the developer's team has access to. Shows workflow name, last run status, last run time, and a button to open the designer.

### `/workflows/[workflowId]/designer` — Drag-Drop Canvas

Visual workflow designer. Features:
- Drag-and-drop node canvas for building DAGs.
- Node property panel (agent selector, input defaults, loop config).
- Edge condition editor.
- Version history and publish (creates a new version).
- "Test run" button that submits a run with sample inputs and opens the run viewer.

### `/workflows/[workflowId]/runs/[runId]` — Live Run Viewer

Real-time run status viewer. Displays the DAG with each node coloured by status (pending, running, succeeded, failed). Subscribes to the SSE event stream for live updates. Shows per-node:
- Status badge and timestamps.
- Log output from the agent container.
- Output JSON (expandable).

### `/keys` — API Key Management

Manage the developer's own API keys:
- List existing keys with creation date, last used, and scope.
- Create new keys (name, optional per-model rate limit).
- Revoke keys.
- Security best practices panel.

### `/models` — Model Catalog

Browse all gateway-enabled models. Shows model name, provider, context window, pricing, and availability. Allows filtering by provider and capability.

### `/mcp` — MCP Servers

Browse MCP servers available to the developer's team. Shows server name, URL, tool list, and connection instructions. Includes the Awesome Copilot Catalog and CodeMate servers from the gateway.

### `/plugins` — Plugin Browser + Copilot Catalog Tab

Two-tab view:
- **Gateway Plugins** — plugins registered in the admin portal, browseable by the developer.
- **Copilot Catalog** — live feed from the Copilot Catalog MCP, showing agents, instructions, and recipes from awesome-copilot.

### `/prompts` — Prompts + Research Knowledge Base

Browse and search the AI Librarian knowledge base. Features:
- Search across all topics with semantic relevance scoring.
- Topic filter sidebar.
- Document detail view with source URL and tags.
- Ingest a new document (links to API docs).

### `/skills` — Skills (stub)

Browse and discover published agent skills. Under development.

### `/usage` — Usage & Spend

Spend analytics for the developer's team:
- **Spend over time** — bar chart of daily/weekly spend.
- **Team summary** — total requests, tokens, and cost for the current period.
- **About these stats** — explanation of how costs are calculated.

### `/docs` — Quickstart

Embedded quickstart documentation covering:
- How to obtain an API key.
- Making your first API call (curl and Python examples).
- Using the gateway's OpenAI-compatible endpoint.
- Links to model catalog, playground, and MCP configuration.

---

## 15. Security

### 15.1 Authentication

The gateway supports two authentication methods at the auth service (port 8001):

**API Key** — `Authorization: Bearer sk-<key>`. The key is SHA-256 hashed and looked up in the `api_keys` table. The team ID and policy are loaded from the database.

**OIDC JWT** — issued by Azure Entra ID. The auth service validates the token signature against the JWKS endpoint at `JWKS_URI` and verifies the `aud` claim matches `ENTRA_CLIENT_ID`.

The admin portal uses a session cookie backed by Redis (`portal_session:{token}` with a 1-hour TTL).

### 15.2 API Key Scopes

| Scope | Description | Where used |
|-------|-------------|------------|
| `standard` | Full access to chat completions and gateway features | Developer portal, CI/CD |
| `workflow-run` | Scoped to a single workflow run; auto-revoked when the run ends | Injected into agent containers as `AIGW_API_KEY` |

### 15.3 DID Identity Tokens

The admin service acts as an identity authority for agents. It maintains an RSA-2048 signing key pair stored encrypted in Redis (`identity:signing_key`) with a 90-day TTL. The key is encrypted with Fernet using a key derived from `IDENTITY_KEY_SECRET`.

**Token issuance** (`POST /identity/token`):
- Issues a signed RS256 JWT with claims: `iss` (`ai-gateway`), `sub` (agent slug), `name`, `iat`, `exp` (30-day default), `capabilities`, and optionally `team_id`.

**Public key** (`GET /identity/jwks`):
- Returns a JWKS document with the current signing key's RSA public parameters (`n`, `e`, `kid`).

**Verification:**
- Any service can verify tokens by fetching JWKS and validating the RS256 signature.
- The Identity Service verifies tokens at registration time (if `identity_token` is provided).

### 15.4 Required Production Secrets

| Env Var | Service | Purpose | Consequence if missing |
|---------|---------|---------|------------------------|
| `AGENT_RELAY_SECRET` | `agent-relay`, `workflow-worker` | Shared secret authenticating relay registrations and invocations | Anyone on the internal network can register arbitrary relay agents |
| `ADMIN_INTERNAL_TOKEN` | `workflow-worker`, `admin` | Bearer token for worker→admin calls (sub-workflow spawns) | Any internal service can trigger workflow runs |
| `IDENTITY_KEY_SECRET` | `admin` (identity signing) | Fernet encryption key for the RSA signing key in Redis | Signing key stored in plaintext; exfiltrable by any Redis reader |
| `IDENTITY_SERVICE_TOKEN` | `identity` | Token gating `POST /agents/register` and `DELETE /agents/{slug}` | Any process on the internal network can register or deregister agent identities |
| `LIBRARIAN_SERVICE_TOKEN` | `librarian` | Token gating `/ingest` and `/mcp/tools/ingest` | Any process on the internal network can inject arbitrary documents into the knowledge base |

Additionally, the admin portal's `SECRET_KEY` and `OIDC_CLIENT_SECRET` must be changed from their development defaults in production.

**Generating secrets:**
```bash
python3 -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

### 15.5 Rate Limiting

The auth service implements per-team, per-model fixed-window rate limiting using Redis counters with a 60-second window. The counter key is `ratelimit:{team_id}:{model}`. If a team has no policy row, `RATE_LIMIT_DEFAULT_RPM` is used (default: 1,000 RPM).

Rate limits can be overridden per-team in the admin portal's Policies page.

### 15.6 Guardrails (content filtering)

Guardrails are applied by the cache service before forwarding requests to LiteLLM. Active guardrail rules are loaded from the `guardrails` table in PostgreSQL. The `pii_detector` type scans prompts and completions for personally identifiable information patterns. Custom pattern rules use configurable regular expressions.

Guardrail hits are logged to the audit log and visible in the admin portal's Guardrails page.

### 15.7 Workflow Agent Security (gh-aw SafeOutputs patterns)

Four security layers are applied during workflow execution, derived from the gh-aw defense-in-depth architecture:

| Layer | When | What |
|---|---|---|
| **Network isolation** | Container launch | Agent container attaches only to the `aigateway` Docker network — no host/bridge access |
| **Input sanitization** | Before `inputs.json` written | @mentions redacted, XML escaped, 50k char / 100 key / 1MB limits enforced |
| **Output threat detection** | After node exits, before DAG advances | Scans outputs for leaked credentials, API keys, injection phrases |
| **Secret redaction** | Before DB persistence | `aigw_run_*` patterns replaced with `[REDACTED]` in `workflow_runs.outputs` |

The `workflow-run` scoped API key injected as `AIGW_API_KEY` is **additionally** blocked by the cache service from accessing any path outside `/v1/chat/completions`.

### 15.8 Audit Logging

Every significant action is written to the `audit_log` table by the observability service. Audit events include:
- API key creation, revocation, and use.
- Team and policy changes made through the admin portal.
- Guardrail hits.
- Workflow run submissions and completions.
- Sub-workflow spawns.

The audit log is queryable from the admin portal's Audit page and is retained indefinitely (no automatic purge).

---

## 16. Configuration Reference

Full environment variable reference across all services. Variables common to multiple services are listed once under their primary service. On the current single host, these values are supplied directly as environment variables to the Compose services; the "Key Vault ref" source shown in the tables below describes the deferred V2/ACA target, where the same values are Container Apps secret references resolved from Azure Key Vault via managed identity. Either way, services fail fast on a missing required variable.

### Shared infrastructure

| Env Var | Source / Value | Services | Description |
|---------|---------|----------|-------------|
| `DATABASE_URL` | Key Vault ref | auth, cache, observability, admin, identity, librarian | Azure Database for PostgreSQL connection (asyncpg) |
| `REDIS_URL` | Key Vault ref | all services | Azure Cache for Redis connection string |

### Auth service (port 8001)

| Env Var | Source / Value | Description |
|---------|---------|-------------|
| `JWKS_URI` | Entra ID tenant JWKS | OIDC public key endpoint for JWT validation |
| `ENTRA_TENANT_ID` | `aa81b43f-3969-4fd4-80c9-84c411508d82` | SimCorp Azure Entra tenant ID |
| `ENTRA_CLIENT_ID` | Key Vault ref | Expected `aud` claim in JWTs |
| `RATE_LIMIT_DEFAULT_RPM` | `1000` | Fallback RPM when no policy row exists |

### Cache service (port 8002)

| Env Var | Source / Value | Description |
|---------|---------|-------------|
| `LITELLM_URL` | `http://litellm` | Upstream for cache misses |
| `LITELLM_MASTER_KEY` | Key Vault ref | Bearer token for LiteLLM API |
| `AUTH_URL` | `http://auth` | Auth service for upstream validation |
| `OBSERVABILITY_URL` | `http://observability` | Async event posting |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model for semantic similarity |
| `EMBEDDING_API_KEY` | Key Vault ref | Gateway API key for embedding calls (routed via LiteLLM) |
| `EMBEDDING_BASE_URL` | `http://litellm/v1` | Base URL for embedding API (via LiteLLM) |
| `DEFAULT_SIMILARITY_THRESHOLD` | `0.90` | Cosine similarity threshold for cache hits |
| `DEFAULT_TTL_SECONDS` | `3600` | Cache entry TTL in seconds |

### Observability service (port 8004)

| Env Var | Source / Value | Description |
|---------|---------|-------------|
| `BUS_PROVIDER` | `azure` | Event bus provider (Azure Service Bus) |
| `AZURE_SERVICE_BUS_CONNECTION_STRING` | Key Vault ref | Azure Service Bus connection string |
| `AZURE_SERVICE_BUS_TOPIC` | `observability-events` | Service Bus queue/topic name |
| `AZURE_SERVICE_BUS_SUBSCRIPTION` | `gateway-workers` | Subscription name |
| `APPINSIGHTS_CONNECTION_STRING` | Key Vault ref | Azure Application Insights connection string |

### Admin service (port 8005)

| Env Var | Source / Value | Description |
|---------|---------|-------------|
| `SECRET_KEY` | Key Vault ref | Session signing key |
| `ADMIN_TOKEN` | Key Vault ref | Required `X-Admin-Token` header value |
| `OIDC_ISSUER` | Entra ID issuer URL | OIDC issuer URL |
| `OIDC_CLIENT_ID` | Key Vault ref | OIDC client ID (Entra ID app registration) |
| `OIDC_CLIENT_SECRET` | Key Vault ref | OIDC client secret |
| `LITELLM_MASTER_KEY` | Key Vault ref | Bearer token for LiteLLM management API |
| `AUTH_URL` | `http://auth` | Auth service URL |
| `CACHE_URL` | `http://cache` | Cache service URL |
| `LITELLM_URL` | `http://litellm` | LiteLLM URL |
| `OBSERVABILITY_URL` | `http://observability` | Observability service URL |
| `IDENTITY_KEY_SECRET` | Key Vault ref | Fernet encryption key for the RSA signing key |
| `GITHUB_WEBHOOK_SECRET` | Key Vault ref | HMAC secret for GitHub webhook validation |
| `ADMIN_INTERNAL_TOKEN` | Key Vault ref | Bearer token for internal service-to-service calls |

### Identity service (port 8006)

| Env Var | Source / Value | Description |
|---------|---------|-------------|
| `ADMIN_URL` | `http://admin` | Admin service URL for startup seed and JWKS fetch |
| `IDENTITY_SERVICE_TOKEN` | Key Vault ref | Required `X-Service-Token` for register/deregister |

### Agent Relay (port 8007)

| Env Var | Source / Value | Description |
|---------|---------|-------------|
| `AGENT_RELAY_SECRET` | Key Vault ref | Shared secret for `/register` and `/invoke` |

### AI Librarian (port 8008)

| Env Var | Source / Value | Description |
|---------|---------|-------------|
| `EMBEDDING_API_KEY` | Key Vault ref | Gateway API key for embedding calls (routed via LiteLLM) |
| `EMBEDDING_BASE_URL` | `http://litellm/v1` | Embedding API base URL (via LiteLLM) |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model |
| `CACHE_URL` | `http://cache` | Cache service URL for research loop LLM calls |
| `RESEARCH_INTERVAL_SECONDS` | `3600` | Background research loop poll interval |
| `CORS_ORIGINS` | `https://dev.aigw.scdom.net` | Comma-separated CORS origins |
| `LIBRARIAN_SERVICE_TOKEN` | Key Vault ref | Required `X-Service-Token` for ingest endpoints |

### Workflow Worker

| Env Var | Default | Description |
|---------|---------|-------------|
| `WORKER_ID` | `worker-{hostname}` | Worker instance identifier |
| `WORKER_CONCURRENCY` | `5` | Maximum concurrent jobs |
| `WORKER_POLL_INTERVAL_S` | `1.0` | Work queue poll interval in seconds |
| `WORKER_CLAIM_TTL_S` | `120` | Seconds before a claim is considered stale |
| `WORKER_SWEEPER_INTERVAL_S` | `30` | Stale claim recovery interval |
| `HOST_RUNS_PATH` | `/tmp/aigw-runs` | Host path for agent I/O directories (bind-mounted into containers) |
| `AGENT_CONTAINER_NETWORK` | `aigateway` | Docker network for agent containers |
| `AGENT_RELAY_URL` | `http://agent-relay` | Agent Relay base URL |
| `ADMIN_URL` | `http://admin` | Admin service URL for sub-workflow spawns |
| `AGENT_CONTAINER_RUNTIME` | `docker` | Container runtime: `docker` or `kubernetes` |
| `AGENT_RELAY_SECRET` | Key Vault ref | Relay authentication secret |
| `ADMIN_INTERNAL_TOKEN` | Key Vault ref | Bearer token for worker→admin calls |

### Provider API keys

| Env Var | Provider |
|---------|----------|
| `ANTHROPIC_API_KEY` | Anthropic (Claude models) |
| `OPENAI_API_KEY` | OpenAI (GPT-4o, GPT-4o Mini) |
| `GEMINI_API_KEY` | Google (Gemini 1.5 Pro, Flash) |
| `GITHUB_MODELS_API_KEY` | GitHub Models |

---

## 17. Deployment

### 17.1 Deploying to the single-host VM (current)

All services run on a single Linux VM (`vm-aigw-dev-sdc`, `10.179.231.68`, Azure Sweden
Central) via Docker Compose, behind a Caddy reverse proxy that terminates TLS. Caddy is the
only externally exposed service (ports 443 and 22). Compose uses two files —
`docker-compose.yml` plus the `docker-compose.host.yml` overlay (the host overlay carries
the GHCR `image:` keys); commands always pass both:

```bash
docker compose -f docker-compose.yml -f docker-compose.host.yml up -d
```

Deploy model: `git push` to `master` → CI builds and pushes images to GHCR → the VM pulls.
Routine single-service update: `scripts/update-service.sh <svc>`; full deploy:
`scripts/deploy-vm.sh`. Host stand-up is intentionally manual (not IaC). Schema migrations
run `alembic upgrade head` against Postgres before the application services start.

#### V2/ACA target (deferred)

In the deferred V2/prod target the gateway is deployed to Azure Container Apps in the
SimCorp Landing Zone (`rg-aigw-dev-sdc`, Sweden Central). Container images are built in CI
and pushed to ACR; the Bicep templates (`infra/bicep/`) roll them out and wire up Key Vault,
PostgreSQL, Redis, Service Bus, and Application Insights. CI/CD workflows for this target are
archived in `.github/workflows/_archived/` and do not currently run.

```bash
# V2/ACA target — deploy the environment with a specific image tag
az deployment group create \
  --resource-group rg-aigw-dev-sdc \
  --template-file infra/bicep/environments/dev/main.bicep \
  --parameters infra/bicep/environments/dev/main.bicepparam \
  --parameters imageTag=sha-<git-sha>
```

In that target, schema migrations run as a Container Apps job:

```bash
az containerapp job start \
  --name job-db-migrate-dev-sdc \
  --resource-group rg-aigw-dev-sdc
```

The V2 gateway FQDN is `aigw-dev.lab.cloud.scdom.net`.

### 17.2 Access

Access the gateway from the corporate VPN (ZPA) at `https://dev.aigw.scdom.net` (VM
`10.179.231.68`). Developers and administrators authenticate via Azure Entra ID SSO
(tenant `aa81b43f-3969-4fd4-80c9-84c411508d82`). The Developer Portal is reached at
`https://dev.aigw.scdom.net/` and the Admin Portal at `https://dev.aigw.scdom.net/admin`.

### 17.3 Running Tests

Fast unit and service tests run locally without any deployed infrastructure. Install all
service packages first:

```bash
pip install \
  -e "services/auth[dev]" \
  -e "services/cache[dev]" \
  -e "services/observability[dev]" \
  -e "services/admin[dev]"

# Run all tests
pytest services/ -v

# Run tests for a specific service
pytest services/workflow-worker/ -v

# Lint and format
ruff check services/
ruff format services/
```

The test suites use `pytest-asyncio` for async tests and `httpx.AsyncClient` for
service-level integration tests. External dependencies are mocked where possible; the
raw-SQL suites use `testcontainers[postgres]` (requires a running Docker daemon).
End-to-end smoke tests run against the deployed environment.

### 17.4 GitHub Agentic Workflows (gh-aw)

[gh-aw](https://github.github.com/gh-aw/) is a GitHub CLI extension that runs AI coding agents inside GitHub Actions. The AI Gateway integrates with gh-aw in five ways:

**1. Gateway-triggered from GitHub events** — a gh-aw workflow fires on PR open or issue label, then calls `POST https://dev.aigw.scdom.net/api/admin/runs` to start a DAG. For example, when a PR is opened, a gh-aw action can trigger an AI Librarian research brief workflow that posts a summary as a PR comment.

```yaml
# Example: .github/workflows/ai-brief.yml
on:
  pull_request:
    types: [opened]
jobs:
  brief:
    runs-on: ubuntu-latest
    steps:
      - run: |
          curl -X POST https://dev.aigw.scdom.net/api/admin/runs \
            -H "Authorization: Bearer ${{ secrets.AIGW_API_KEY }}" \
            -d '{"workflow_id": "pr-brief", "inputs": {"pr_url": "${{ github.event.pull_request.html_url }}"}}'
```

**2. Gateway as the AI engine** — configure gh-aw's BYO-model option to route inference through `https://dev.aigw.scdom.net/v1/chat/completions`. All inference calls get the gateway's caching, cost tracking, guardrails, and per-team rate limits applied automatically.

```yaml
gh-aw run improve-pr \
  --model-url https://dev.aigw.scdom.net/v1/chat/completions \
  --model gpt-4o \
  --api-key $AIGW_API_KEY
```

**3. GitHub tokens to Gateway identity** — exchange a GitHub Actions per-job OIDC token at `POST https://dev.aigw.scdom.net/auth/validate` to obtain a Gateway-scoped identity. This gives each GitHub Actions job a team-attributed identity for cost tracking and audit logging without needing to distribute long-lived API keys to CI.

**4. Relay agent with gh-aw** — a developer laptop running `aigw-agent serve` can process invocations triggered by gh-aw's continuous improvement workflows. When gh-aw needs to run a task that requires local tools (IDE state, file system access, local test runner), it invokes the relay agent rather than spawning a new container, enabling hybrid local/cloud workflows.

**5. Gateway Observability + gh-aw metrics** — post gh-aw run summaries to `POST https://dev.aigw.scdom.net/api/observability/events` for unified cost and activity dashboards per team. This gives engineering leaders a single view of AI usage whether the call came from the gateway directly or from a gh-aw agent in CI.

**Install:**
```bash
gh extension install github/gh-aw
```

---

### 17.4 GitHub Agentic Workflows (gh-aw)

**gh-aw** (<https://github.github.com/gh-aw/>) is a GitHub CLI extension that runs AI coding agents inside GitHub Actions using plain markdown workflow files instead of YAML. It provides 10+ event triggers, 8+ safe output types (create PR, add comment, add label, etc.), and a 5-layer security model (read-only tokens, zero-secrets, Squid proxy allowlisting, scoped write-gating, prompt-injection scanning).

**Install:**

```bash
gh extension install github/gh-aw
```

**Five integration patterns with the AI Gateway:**

| Pattern | How |
|---|---|
| **Gateway-triggered from GitHub events** | A gh-aw workflow fires on `pr.opened` or `issues.labeled`, then `POST https://dev.aigw.scdom.net/api/admin/runs` to start a workflow DAG — e.g., AI Librarian research brief posted as a PR comment |
| **Gateway as the AI engine** | Configure gh-aw's BYO-model option to route inference through `https://dev.aigw.scdom.net/v1/chat/completions` — all calls inherit caching, guardrails, and cost tracking |
| **GitHub tokens → Gateway identity** | Exchange the per-job read-only GitHub OIDC token at `https://dev.aigw.scdom.net/auth/validate` for a Gateway-scoped identity with team cost attribution and rate limiting |
| **Relay agent ↔ gh-aw** | A laptop relay agent (`aigw-agent serve`) processes invocations triggered by gh-aw continuous improvement or multi-repo sync workflows |
| **Unified observability** | Post gh-aw run summaries to `https://dev.aigw.scdom.net/api/observability/events` for unified agent activity + model cost dashboards per team |

**Example — research brief on every PR:**

```markdown
<!-- .github/workflows/ai-gateway-research.md -->
---
on: pull_request.opened
---
Call POST https://dev.aigw.scdom.net/api/admin/runs with:
- workflow_id: <research-workflow-uuid>
- inputs: {pr_title: "{{ event.pull_request.title }}", pr_body: "{{ event.pull_request.body }}"}
Post the result as a PR comment.
```

### 17.5 Shipped gh-aw Workflows

Seven ready-to-use workflow definitions in `.github/workflows/`:

| File | Trigger | Purpose | Gateway services used |
|---|---|---|---|
| `simcorp-pr-describe.md` | `label_command: ai-describe` | Generates structured PR description | /v1 |
| `simcorp-budget-alerts.md` | Daily 08:00 UTC | Issues a GitHub alert when any team hits ≥80% monthly budget | /budget, /v1 |
| `simcorp-chargeback-report.md` | Weekly Monday 09:00 UTC | Full cost breakdown with cache savings and forecast | /budget, /reports, /v1 |
| `simcorp-run-diagnosis.md` | `workflow_run` failure | Diagnoses CI failures using Gateway DevOps agent | /system/health, /audit, /v1 |
| `simcorp-pr-review.md` | `pull_request` opened/sync | Code review + CodeMate codebase context | /v1, /mcp/codemate |
| `simcorp-security-scan.md` | `pull_request` opened/sync | Guardrails scan + TruffleHog + Semgrep → SARIF to GitHub Security tab | /guardrails, /v1 |
| `simcorp-issue-triage.md` | `issues` opened | Triage + AI Librarian knowledge base search | /v1, /librarian |
| `simcorp-workflow-health.md` | Weekly Monday 07:00 UTC | Meta-agent: monitors failed runs, flags threat-detection events | /runs, /agents, /system/health |

**Setup:** Add these GitHub Actions secrets/variables to your org:

| Name | Type | Value |
|---|---|---|
| `AIGW_API_KEY` | Secret | Service-account API key from Gateway admin → Teams → API Keys |
| `AIGW_BASE_URL` | Variable | `https://dev.aigw.scdom.net/v1` (OpenAI-compat inference endpoint) |
| `AIGW_BASE_URL_ADMIN` | Variable | `https://dev.aigw.scdom.net/api/admin` (admin service) |
| `AIGW_LIBRARIAN_URL` | Variable | `https://dev.aigw.scdom.net/api/librarian` (librarian) |

**Compile lock files** (required after frontmatter changes):
```bash
gh extension install github/gh-aw
gh aw compile
```

Full research report: `docs/gh-aw-research.md`

## Appendix A: DAG JSON Full Schema

Complete, annotated 4-node workflow example:

```json
{
  // entry_node: the first node to execute when a run is submitted.
  // Must match one of the node IDs in the "nodes" array.
  "entry_node": "ingest",

  "nodes": [
    {
      // id: unique node identifier within this DAG (string, required)
      "id": "ingest",
      // agent_slug: must match a slug in the agents table with enabled=true
      "agent_slug": "doc-ingester",
      // inputs: default input values merged with run-level inputs at execution time.
      // The entry node also receives inputs submitted at POST /runs time.
      "inputs": {
        "source": "https://example.com/doc.pdf"
      }
      // No loop config → runs exactly once
    },
    {
      "id": "classify",
      "agent_slug": "content-classifier",
      "inputs": {}
      // Receives _predecessors.ingest = <outputs from ingest node>
    },
    {
      "id": "summarise",
      "agent_slug": "summariser",
      "inputs": {},
      // loop: object (or bool true for defaults)
      "loop": {
        // enabled: must be true for looping to activate
        "enabled": true,
        // max_iterations: maximum number of times this node can run.
        // Iteration counting is 0-based; the node runs at most max_iterations times.
        "max_iterations": 5
        // To loop, the node must also output {"_loop_continue": true}
      }
    },
    {
      "id": "notify",
      "agent_slug": "slack-notifier",
      "inputs": {
        "channel": "#ai-research"
      }
    }
  ],

  "edges": [
    {
      // from/to: must be valid node IDs
      "from": "ingest",
      "to": "classify",
      // condition: null = unconditional edge (always fires on success)
      "condition": null
    },
    {
      "from": "classify",
      "to": "summarise",
      // Conditional edge: only fires if classify outputs {"category": "article"}
      // The "outputs." prefix is optional — both forms are equivalent:
      //   "outputs.category == \"article\""
      //   "category == \"article\""
      "condition": "outputs.category == \"article\""
    },
    {
      "from": "classify",
      "to": "notify",
      // Fan-out: classify can also go directly to notify if it's not an article
      "condition": "outputs.category != \"article\""
    },
    {
      "from": "summarise",
      "to": "notify",
      // After the summarise loop exits (loop_continue = false OR max_iterations reached),
      // this unconditional edge fires
      "condition": null
    }
  ]
}
```

**Condition syntax reference:**

| Pattern | Example | Meaning |
|---------|---------|---------|
| `path == "string"` | `outputs.status == "ok"` | Exact string match |
| `path != "string"` | `outputs.category != "spam"` | String inequality |
| `path > number` | `outputs.score > 0.8` | Numeric greater-than |
| `path >= number` | `outputs.count >= 10` | Numeric greater-or-equal |
| `path == true/false` | `outputs._loop_continue == true` | Boolean match |
| `path == null` | `outputs.error == null` | Null check |
| `path` (bare) | `outputs.success` | Truthiness check (no operator) |

---

## Appendix B: Agent Manifest Schema

Full schema for `manifest.json` with all fields:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["slug", "name", "description", "image"],
  "properties": {
    "slug": {
      "type": "string",
      "description": "Stable unique identifier. URL-safe characters only. Used in DAG agent_slug fields and relay:// URIs. Example: 'echo-agent'."
    },
    "name": {
      "type": "string",
      "description": "Human-readable display name shown in the portal. Example: 'Echo Agent'."
    },
    "description": {
      "type": "string",
      "description": "What the agent does. Shown in the agent catalog and portal."
    },
    "image": {
      "type": "string",
      "description": "Docker image reference (e.g. 'registry.internal/my-agent:1.0.0') or 'relay://{slug}' for relay agents."
    },
    "category": {
      "type": "string",
      "description": "Organisational category tag. Examples: 'utility', 'research', 'integration', 'notification'."
    },
    "managed": {
      "type": "boolean",
      "default": false,
      "description": "true for agents registered and managed through the admin portal."
    },
    "inputs_schema": {
      "type": "object",
      "description": "JSON Schema describing the expected structure of /run/inputs.json. Used for validation in the workflow designer and portal. If omitted, any input is accepted.",
      "example": {
        "type": "object",
        "properties": {
          "query": {"type": "string"},
          "limit": {"type": "integer", "default": 10}
        },
        "required": ["query"]
      }
    },
    "outputs_schema": {
      "type": "object",
      "description": "JSON Schema describing the structure of /run/outputs.json. Used by the workflow designer to provide autocomplete for edge conditions.",
      "example": {
        "type": "object",
        "properties": {
          "result": {"type": "string"},
          "score": {"type": "number"},
          "_loop_continue": {"type": "boolean"}
        },
        "required": ["result"]
      }
    }
  },
  "additionalProperties": false
}
```

**Notes:**
- `relay://` agents do not have a Docker image; the slug in the URI must match a registered relay agent.
- `inputs_schema` and `outputs_schema` are advisory at runtime — the worker does not validate them during execution, but the designer uses them for UI hints.
- To support autonomous spawning, include `_spawn` as an optional property in `outputs_schema`.

---

## Appendix C: MCP Tool Schemas

### Awesome Copilot Catalog (admin :8005 `/mcp/copilot-catalog`)

**`search`**
```json
{
  "name": "search",
  "description": "Search the Awesome Copilot catalog by keyword",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Search keywords"
      },
      "kind": {
        "type": "string",
        "enum": ["agent", "instruction", "recipe"],
        "description": "Filter by item type"
      },
      "limit": {
        "type": "integer",
        "default": 5,
        "description": "Maximum number of results"
      }
    },
    "required": ["query"]
  }
}
```

**`list`**
```json
{
  "name": "list",
  "description": "List all items of a given type from the Awesome Copilot catalog",
  "inputSchema": {
    "type": "object",
    "properties": {
      "kind": {
        "type": "string",
        "enum": ["agent", "instruction", "recipe"]
      },
      "limit": {
        "type": "integer",
        "default": 20
      }
    }
  }
}
```

**`get`**
```json
{
  "name": "get",
  "description": "Get full details of a catalog item by its slug ID",
  "inputSchema": {
    "type": "object",
    "properties": {
      "id": {
        "type": "string",
        "description": "Item slug ID"
      }
    },
    "required": ["id"]
  }
}
```

---

### CodeMate Tools (admin :8005 `/mcp/codemate`)

**`codebase_search__search_code`**
```json
{
  "name": "codebase_search__search_code",
  "description": "Search SimCorp codebase by natural language or symbol",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Natural language or symbol search query"
      },
      "limit": {
        "type": "integer",
        "default": 10,
        "description": "Maximum number of results"
      }
    },
    "required": ["query"]
  }
}
```

**`codebase_search__find_system_objects_by_caption`**
```json
{
  "name": "codebase_search__find_system_objects_by_caption",
  "description": "Find SimCorp system objects (forms, views, workflows) by caption",
  "inputSchema": {
    "type": "object",
    "properties": {
      "caption": {
        "type": "string",
        "description": "Caption text to search for"
      }
    },
    "required": ["caption"]
  }
}
```

---

### AI Librarian (librarian :8008 `/mcp`)

**`search`**
```json
{
  "name": "search",
  "description": "Search the knowledge base semantically",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Natural language search query"
      },
      "topic": {
        "type": "string",
        "description": "Filter results to a specific topic slug"
      },
      "limit": {
        "type": "integer",
        "default": 5,
        "description": "Maximum number of results (1–100)"
      }
    },
    "required": ["query"]
  }
}
```

**`ingest`**
```json
{
  "name": "ingest",
  "description": "Add a document to the knowledge base",
  "inputSchema": {
    "type": "object",
    "properties": {
      "title": {
        "type": "string",
        "description": "Document title"
      },
      "content": {
        "type": "string",
        "description": "Document body text (max 50,000 characters)"
      },
      "topic": {
        "type": "string",
        "description": "Topic slug to associate this document with"
      },
      "tags": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Tag list (max 20 items, each max 50 characters)"
      }
    },
    "required": ["title", "content"]
  }
}
```

**`topics`**
```json
{
  "name": "topics",
  "description": "List all research topics with item counts",
  "inputSchema": {
    "type": "object"
  }
}
```

---

## Appendix D: API Quick Reference

One-liner per endpoint, grouped by service.

### Auth service (port 8001)
```
GET  /health                         Health check
POST /validate                       Validate and decode a Bearer token
GET  /keys                           List API keys for authenticated team
POST /keys                           Create a new API key
DELETE /keys/{key_id}                Revoke an API key
GET  /rate-limit/{team_id}/{model}   Get current rate limit counter
```

### Cache service (port 8002)
```
GET  /health                         Health check
POST /v1/chat/completions            OpenAI-compatible chat completions (with caching)
GET  /stats                          Cache hit/miss statistics
DELETE /cache/{key}                  Invalidate a specific cache entry
POST /events                         (internal) Ingest an observability event
```

### LiteLLM proxy (port 8003)
```
GET  /health                         Health check
POST /v1/chat/completions            OpenAI-compatible chat (provider routing)
POST /v1/completions                 Text completions
POST /v1/embeddings                  Embeddings
GET  /v1/models                      List available models
POST /model/update                   (admin) Hot-update provider keys
```

### Observability service (port 8004)
```
GET  /health                         Health check
POST /events                         Ingest a completion event (cost, tokens, audit)
GET  /sessions/{session_id}          Get session aggregate stats
GET  /cost-records                   Query cost records (date range, team)
GET  /audit-log                      Query audit log
```

### Admin service (port 8005)
```
GET  /health                         Health check
GET  /system/health                  Aggregate health of all services
GET  /teams                          List teams
POST /teams                          Create a team
GET  /teams/{id}                     Get team detail
PATCH /teams/{id}                    Update a team
DELETE /teams/{id}                   Delete a team
GET  /areas                          List areas
POST /areas                          Create an area
PATCH /areas/{id}                    Update an area
DELETE /areas/{id}                   Delete an area
GET  /agents                         List registered agents
POST /agents                         Register an agent
PATCH /agents/{id}                   Update an agent
DELETE /agents/{id}                  Remove an agent
GET  /policies                       List policies
POST /policies                       Create a policy
PATCH /policies/{id}                 Update a policy
DELETE /policies/{id}                Delete a policy
GET  /guardrails                     List guardrails
POST /guardrails                     Create a guardrail
PATCH /guardrails/{id}               Update a guardrail
DELETE /guardrails/{id}              Delete a guardrail
GET  /models                         List model registry entries
POST /models                         Register a model
PATCH /models/{id}                   Enable/disable a model
GET  /api-keys                       List API keys (admin view)
POST /api-keys                       Create an API key
DELETE /api-keys/{id}                Revoke an API key
GET  /audit-log                      Query audit log
GET  /reports/costs                  Cost report (date range, team, model)
GET  /requests                       Recent request log
POST /runs                           Submit a workflow run
GET  /runs/{run_id}                  Get run status
GET  /runs/{run_id}/events           SSE stream of run events
POST /runs/{run_id}/cancel           Cancel a running workflow
GET  /mcp/servers                    List registered MCP servers
POST /mcp/servers                    Register an MCP server
DELETE /mcp/servers/{id}             Remove an MCP server
GET  /mcp/copilot-catalog            Catalog MCP manifest
POST /mcp/copilot-catalog            Catalog JSON-RPC 2.0 endpoint
GET  /mcp/copilot-catalog/sse        Catalog SSE transport
GET  /mcp/codemate                   CodeMate MCP manifest
POST /mcp/codemate                   CodeMate JSON-RPC 2.0 endpoint
GET  /mcp/codemate/sse               CodeMate SSE transport
POST /devops-agent/chat              DevOps AI agent chat
GET  /insights                       List AI-generated insights
DELETE /insights/{id}                Dismiss an insight
GET  /identity/jwks                  JWKS public key endpoint
POST /identity/token                 Issue a DID identity token for an agent
POST /webhooks/github                GitHub webhook receiver
```

### Identity service (port 8006)
```
GET  /health                         Health check
GET  /agents                         List agents (capability/category/team/managed filters)
GET  /agents/{slug}                  Get agent by slug
GET  /agents/{slug}/identity         Lightweight identity summary
GET  /agents/{slug}/endpoint         Resolve endpoint URL
POST /agents/{slug}/heartbeat        Refresh online TTL
POST /agents/register                Register or upsert an agent
DELETE /agents/{slug}                Deregister an agent
GET  /resolve/{name}                 DNS-style resolve: slug, capability, or partial name
GET  /capabilities                   List all distinct capability tags
```

### Agent Relay (port 8007)
```
GET  /health                         Health check
GET  /agents                         List connected relay agents
POST /register                       Register a relay agent (returns relay_token)
WS   /connect/{relay_token}          Agent WebSocket tunnel
POST /invoke/{agent_slug}            Invoke a relay agent by slug
```

### AI Librarian (port 8008)
```
GET  /health                         Health check
POST /ingest                         Ingest a document
GET  /search                         Semantic search (q, topic, tags, limit)
GET  /topics                         List topics with item counts
GET  /topics/{topic}                 List items in a topic
DELETE /items/{item_id}              Delete a knowledge item
GET  /research/topics                List research topic configs
POST /research/topics                Create a research topic
POST /research/topics/{topic}/trigger  Trigger immediate research
DELETE /research/topics/{topic}      Delete a research topic
GET  /mcp                            MCP manifest
POST /mcp                            JSON-RPC 2.0 MCP endpoint
GET  /mcp/sse                        HTTP+SSE MCP transport
GET  /mcp/tools                      List tools (REST)
POST /mcp/tools/search               Search tool (REST)
POST /mcp/tools/ingest               Ingest tool (REST)
POST /mcp/tools/topics               Topics tool (REST)
```

---

## 18. Unified Identity Model (migration 0010–0011)

### 18.1 Overview

The platform uses a single `users` table for all human principals, replacing the prior split between `admin_users` and `developers`. Non-human principals (CI pipelines, integrations) are modelled as `service_accounts`.

All existing UUIDs were preserved during migration: every foreign-key reference in `cost_records`, `sessions`, `developer_achievements`, `team_members`, and related tables remains valid.

### 18.2 Schema

```sql
-- Primary identity table
users (
  id                  UUID PRIMARY KEY,
  email               VARCHAR(255) UNIQUE NOT NULL,
  display_name        VARCHAR(255),
  password_hash       TEXT,
  hash_type           TEXT CHECK (hash_type IN ('bcrypt', 'pbkdf2')),
  status              TEXT CHECK (status IN ('active', 'pending', 'suspended')),
  must_change_password BOOLEAN DEFAULT FALSE,
  primary_team_id     UUID REFERENCES teams(id),
  last_login_at       TIMESTAMPTZ,
  created_at, updated_at TIMESTAMPTZ
)

-- Scoped role grants
user_roles (
  id          UUID PRIMARY KEY,
  user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
  role        TEXT CHECK (role IN (
                'gateway_admin', 'area_owner', 'team_admin',
                'engineer', 'reporter', 'service_account')),
  scope_type  TEXT CHECK (scope_type IN ('global', 'area', 'team')),
  scope_id    UUID,          -- area.id or team.id when scope_type != 'global'
  granted_at  TIMESTAMPTZ,
  granted_by  UUID REFERENCES users(id)
)

-- Token-based onboarding (no SMTP required)
user_invitations (
  id          UUID PRIMARY KEY,
  email       VARCHAR(255),
  role        TEXT,
  scope_type  TEXT,
  scope_id    UUID,
  token_hash  TEXT UNIQUE,   -- SHA-256 of raw token; raw shown once
  invited_by  UUID REFERENCES users(id),
  expires_at  TIMESTAMPTZ,   -- 48 hours from creation
  accepted_at TIMESTAMPTZ
)

-- API-key-only principals
service_accounts (
  id              UUID PRIMARY KEY,
  name            VARCHAR(200),
  description     TEXT,
  key_hash        TEXT UNIQUE,   -- SHA-256 of raw key
  key_prefix      VARCHAR(20),   -- first 12 chars for identification
  owner_user_id   UUID REFERENCES users(id),
  team_id         UUID REFERENCES teams(id),
  status          TEXT CHECK (status IN ('active', 'suspended', 'revoked')),
  created_by      UUID REFERENCES users(id),
  last_used_at    TIMESTAMPTZ
)
```

### 18.3 Session model

Sessions are stored in Redis at key `session:{token}` with the following payload:

```json
{
  "user_id": "uuid",
  "email": "user@simcorp.com",
  "display_name": "Full Name",
  "roles": [
    {"role": "engineer", "scope_type": "global", "scope_id": null}
  ],
  "primary_team_id": "uuid | null",
  "team_name": "Engineering | null"
}
```

TTL: 8 hours (admins) / 7 days (developers). Extended to 30 days with `remember_me: true`.

### 18.4 Password hashing

- New passwords: bcrypt (cost 12)
- Legacy developer passwords: pbkdf2-sha256 (390,000 iterations)
- Transparent upgrade: pbkdf2 passwords are re-hashed to bcrypt on first successful login

### 18.5 Org hierarchy

```
Organisation (SimCorp — single tenant)
  └── Areas  (area_owner role — scoped to area.id)
        └── Teams  (team_admin role — scoped to team.id)
              └── Users  (engineer / reporter roles — global scope)
```

`gateway_admin` users have access to all areas and teams. `area_owner` and `team_admin` roles include a `scope_id` FK that restricts their authority to a specific area or team.

### 18.6 SSO / OIDC flow

```
Browser  →  GET /auth/oidc/login
         →  302 to Azure Entra ID
         →  user authenticates
         →  GET /auth/oidc/callback?code=...&state=...
         →  backend exchanges code for id_token
         →  extracts email + display_name claims
         →  finds or creates users row (engineer role if new)
         →  issues Redis session
         →  302 to /admin?sso_token=<token> or /?sso_token=<token>
         →  frontend stores token, strips query param
```

Entra ID config (`OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`) is supplied via Key Vault secret references. The redirect URI `https://dev.aigw.scdom.net/auth/oidc/callback` is registered on the Entra ID app registration.

### 18.7 Backwards compatibility

The `/admin-auth/*` and `/dev-auth/*` route families are kept as thin shims that delegate to `unified_auth.py`. Existing session tokens remain valid. The `require_admin_auth` dependency in `auth.py` checks `session:{token}` first, then falls back to the legacy `admin_session:{token}` format.

---

*Last updated: 2026-05-13*
