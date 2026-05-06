# AI Gateway — Operations Runbook

**Audience:** Platform engineers and on-call responders  
**System:** Enterprise AI gateway serving ~2,000 SimCorp engineers  
**Last updated:** 2026-05-06

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Starting and Stopping](#2-starting-and-stopping)
3. [Health Monitoring](#3-health-monitoring)
4. [Common Failure Modes](#4-common-failure-modes)
5. [Database Maintenance](#5-database-maintenance)
6. [Adding a New AI Provider](#6-adding-a-new-ai-provider)
7. [Managing Teams and Rate Limits](#7-managing-teams-and-rate-limits)
8. [Log Locations and What to Look For](#8-log-locations-and-what-to-look-for)
9. [Environment Variables Reference](#9-environment-variables-reference)

---

## 1. Architecture Overview

### Service Map

```
Caller (developer tool / IDE extension)
    |
    v
auth  :8001  — JWT / API key validation, per-team rate limiting (Redis fixed-window)
    |
    v
cache :8002  — Semantic + exact cache (Redis), embedding via Ollama or OpenAI
    |
    v
litellm :8003 — Provider routing, OpenAI-compatible API (Anthropic / OpenAI / Google / GitHub Models)
    |
    v
Provider APIs  (anthropic.com, api.openai.com, generativelanguage.googleapis.com, …)

observability :8004  — Async event ingestion, writes cost_records + audit_log to Postgres
admin         :8005  — Team management, API keys, provider key config, system health dashboard
```

### Shared Infrastructure

| Component | Port | Role |
|-----------|------|------|
| PostgreSQL 16 | 5432 | Teams, API keys, policies, cost records, audit log, developers |
| Redis Stack 7.2 | 6379 | Rate limit counters, semantic cache, admin portal sessions |
| Dex (mock OIDC) | 5556 | Local Entra ID substitute for admin portal login |
| Ollama (optional) | 11434 | Local model serving and embedding generation |

### Key Data Flows

- **Authentication:** caller sends `Authorization: Bearer sk-<key>`. Auth service hashes the key, looks it up in `api_keys`, loads the team's policy from `policies`, checks the Redis rate limit counter at `ratelimit:{team_id}:{model}`, then forwards with `X-Litellm-Master-Key` injected.
- **Caching:** cache service computes a semantic embedding of the request and checks Redis for a similar past response. Hits skip litellm entirely. Misses are forwarded and the response is stored.
- **Observability:** after each completion, a structured event is posted to `:8004/events`. The service writes a `cost_records` row and, for notable events, an `audit_log` row.
- **Provider keys:** stored in the `provider_keys` table. On save, the admin portal calls `PATCH /model/update` on LiteLLM to inject the key at runtime — no restart required.

---

## 2. Starting and Stopping

### Start Everything

```bash
cd /home/bntp/repos/ai-gw

# First time: copy and edit environment variables
cp .env.example .env
# edit .env with real provider keys if needed

# Build and start all services
docker compose -f infra/docker-compose.yml up --build

# Background (detached)
docker compose -f infra/docker-compose.yml up --build -d
```

The `db-migrate` container runs `init.sql` before any app services start. LiteLLM has a 120-second `start_period` — allow 2–3 minutes for full cluster readiness.

### Start with Ollama (local model serving)

```bash
docker compose -f infra/docker-compose.yml --profile ollama up --build -d
```

### Stop Everything

```bash
docker compose -f infra/docker-compose.yml down
```

### Stop and Wipe Persistent Data

```bash
# Destroys postgres_data and ollama_data volumes — use with care
docker compose -f infra/docker-compose.yml down -v
```

### Restart a Single Service

```bash
docker compose -f infra/docker-compose.yml restart auth
docker compose -f infra/docker-compose.yml restart cache
docker compose -f infra/docker-compose.yml restart litellm
docker compose -f infra/docker-compose.yml restart observability
docker compose -f infra/docker-compose.yml restart admin
```

### Rebuild a Single Service After Code Change

```bash
docker compose -f infra/docker-compose.yml up --build auth -d
```

### Check Service Status

```bash
docker compose -f infra/docker-compose.yml ps
```

---

## 3. Health Monitoring

### System Health Dashboard

The admin portal exposes a built-in health dashboard:

| URL | Format | Notes |
|-----|--------|-------|
| `http://localhost:8005/system/health/ui` | HTML | Auto-refreshes every 10 seconds |
| `http://localhost:8005/system/health` | JSON | Suitable for external monitoring/alerting |

The dashboard checks all of the following simultaneously:

| Panel | What it shows |
|-------|---------------|
| Service status | HTTP reachability and latency for auth, cache, litellm, observability |
| Redis | Ping latency, used memory (MB), connected client count |
| PostgreSQL | Ping latency, active connection count |
| LiteLLM models | Number of models available, providers with keys configured |
| Gateway metrics | Requests in the last 60 seconds, cache hit rate in the last 60 seconds |
| Recent errors | Last 8 audit_log entries where action contains `error`, `fail`, or `revok` |

Overall status is `ok` only when every sub-check is `ok`; otherwise `degraded`.

### Individual Service Health Endpoints

```
GET http://localhost:8001/health   — auth
GET http://localhost:8002/health   — cache
GET http://localhost:8003/health/liveliness  — litellm
GET http://localhost:8004/health   — observability
GET http://localhost:8005/health   — admin
```

### Redis Health Check (CLI)

```bash
docker compose -f infra/docker-compose.yml exec redis redis-cli ping
# Expected: PONG

docker compose -f infra/docker-compose.yml exec redis redis-cli info memory | grep used_memory_human
docker compose -f infra/docker-compose.yml exec redis redis-cli info clients | grep connected_clients
```

### PostgreSQL Health Check (CLI)

```bash
docker compose -f infra/docker-compose.yml exec postgres \
  psql -U aigateway -c "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';"
```

### Key Metrics to Watch

| Metric | Where | Alert threshold (suggested) |
|--------|-------|-----------------------------|
| Service status != ok | `/system/health` | Any service unreachable |
| Redis used_memory_mb | `/system/health` > redis | > 80% of `maxmemory` setting |
| Postgres active_connections | `/system/health` > postgres | > 80 (default max is 100) |
| requests_last_60s | `/system/health` > gateway | Sudden drop to 0 during business hours |
| cache_hit_rate_last_60s | `/system/health` > gateway | Sustained drop below 0.20 |
| models_available | `/system/health` > litellm | 0 models available |

---

## 4. Common Failure Modes

### 4.1 Service Unreachable

**Symptoms:** Health dashboard shows `unreachable` for one or more services. HTTP calls to that service return connection refused.

**Diagnosis:**

```bash
# Check if the container is running
docker compose -f infra/docker-compose.yml ps

# Check recent logs for the failing service
docker compose -f infra/docker-compose.yml logs --tail=100 auth
docker compose -f infra/docker-compose.yml logs --tail=100 cache
docker compose -f infra/docker-compose.yml logs --tail=100 litellm
```

**Common causes and fixes:**

| Cause | Fix |
|-------|-----|
| Container exited (crash loop) | Check logs for Python traceback. Fix the root cause, then `docker compose up -d <service>` |
| Dependency not ready (e.g. litellm waiting on postgres) | Wait for `db-migrate` to complete; `docker compose ps` should show it as `exited 0` |
| Port conflict on host | Check `ss -tlnp | grep 800` and kill conflicting processes |
| Build failure | Run `docker compose build <service>` standalone to see the full error |

---

### 4.2 Auth Failures (HTTP 401)

**Symptoms:** Callers receive `401 Unauthorized`. Admin portal returns `401 Invalid admin token`.

**Diagnosis:**

- For **gateway callers** (`sk-` keys): the key may be revoked, expired, or the team may not exist.

```sql
-- Check key status in Postgres
docker compose -f infra/docker-compose.yml exec postgres \
  psql -U aigateway -c "
    SELECT ak.name, ak.created_at, ak.revoked_at, t.name AS team
    FROM api_keys ak JOIN teams t ON ak.team_id = t.id
    WHERE ak.revoked_at IS NOT NULL
    ORDER BY ak.revoked_at DESC LIMIT 10;"
```

- For **admin portal** (`X-Admin-Token` header): confirm the `ADMIN_TOKEN` env var is set and matches what the client is sending.

```bash
# Is dev bypass enabled?
docker compose -f infra/docker-compose.yml exec admin \
  printenv DEV_BYPASS_AUTH ADMIN_TOKEN
```

**Common causes and fixes:**

| Cause | Fix |
|-------|-----|
| API key revoked | Issue a new key via Admin > Teams > API Keys |
| `ADMIN_TOKEN` not set | Set `ADMIN_TOKEN` in `.env` and restart the admin service |
| `DEV_BYPASS_AUTH=false` with empty `ADMIN_TOKEN` | Admin will return 500 — set `ADMIN_TOKEN` |
| JWT from Dex expired | Re-authenticate through the OIDC flow |

---

### 4.3 Rate Limit Hit (HTTP 429)

**Symptoms:** Callers receive `429 Rate limit exceeded` with header `Retry-After: 60`.

**How it works:** Auth uses a fixed 60-second window. The Redis key `ratelimit:{team_id}:{model}` is incremented on each request and expires after 60 seconds. When the count exceeds the team's `rate_limit_rpm` policy, subsequent requests in the window are rejected.

**Diagnosis:**

```bash
# Check current counter for a team+model combination
docker compose -f infra/docker-compose.yml exec redis \
  redis-cli get "ratelimit:<team_id>:<model>"

# See all active rate limit keys
docker compose -f infra/docker-compose.yml exec redis \
  redis-cli keys "ratelimit:*"

# Check the team's configured limit
docker compose -f infra/docker-compose.yml exec postgres \
  psql -U aigateway -c "
    SELECT t.name, p.rate_limit_rpm
    FROM policies p JOIN teams t ON p.team_id = t.id;"
```

**Fix options:**

1. **Wait:** the window resets automatically after 60 seconds.
2. **Increase limit:** Admin portal > Teams > select team > Policies > raise `rate_limit_rpm`.
3. **Clear the counter manually (emergency only):**

```bash
docker compose -f infra/docker-compose.yml exec redis \
  redis-cli del "ratelimit:<team_id>:<model>"
```

---

### 4.4 Provider API Key Missing

**Symptoms:** LiteLLM returns `AuthenticationError` or `APIError`. The system health dashboard shows `models_available: 0` or a low count. The settings page at `http://localhost:8005/ui/settings` shows a provider as "not configured".

**Diagnosis:**

```bash
# Check what keys are stored in the database
docker compose -f infra/docker-compose.yml exec postgres \
  psql -U aigateway -c "
    SELECT env_var, updated_at FROM provider_keys;"

# Check LiteLLM model list (should list configured models)
curl -s -H "Authorization: Bearer sk-litellm-local-dev" \
  http://localhost:8003/v1/models | python3 -m json.tool
```

**Fix:**

1. Navigate to `http://localhost:8005/ui/settings`.
2. Enter the API key for the failing provider in the appropriate field.
3. Click **Save**. The portal stores the key in `provider_keys` and immediately calls `PATCH /model/update` on LiteLLM — no restart required.
4. Use the **Test** button on the settings page to verify connectivity. It fires a 1-token completion and reports latency.

**Key environment variables per provider:**

| Provider | Env var |
|----------|---------|
| Anthropic (Claude) | `ANTHROPIC_API_KEY` |
| OpenAI | `OPENAI_API_KEY` |
| Google (Gemini) | `GEMINI_API_KEY` |
| GitHub Models | `GITHUB_MODELS_API_KEY` |

---

### 4.5 Redis Full or Disconnected

**Symptoms:** Auth service returns 500 (cannot check rate limits). Cache service fails to read/write. Admin portal sessions drop. System health shows Redis as `unreachable` or high memory usage.

**Diagnosis:**

```bash
# Ping
docker compose -f infra/docker-compose.yml exec redis redis-cli ping

# Memory info
docker compose -f infra/docker-compose.yml exec redis redis-cli info memory

# Key count and type breakdown
docker compose -f infra/docker-compose.yml exec redis redis-cli dbsize
docker compose -f infra/docker-compose.yml exec redis redis-cli info keyspace
```

**Redis disconnected — fix:**

```bash
docker compose -f infra/docker-compose.yml restart redis
```

All services reconnect automatically. Rate limit windows will reset (acceptable as a recovery side-effect).

**Redis memory full — fix options:**

1. **Flush expired keys** (Redis does this lazily; trigger it):

```bash
docker compose -f infra/docker-compose.yml exec redis redis-cli debug sleep 0
```

2. **Flush semantic cache only** (safe, cache will rebuild on demand):

```bash
# Semantic cache keys typically follow a pattern — inspect first
docker compose -f infra/docker-compose.yml exec redis redis-cli keys "cache:*"
# Then delete matching keys
docker compose -f infra/docker-compose.yml exec redis redis-cli --scan --pattern "cache:*" \
  | xargs redis-cli del
```

3. **Flush portal sessions** (users will need to re-login):

```bash
docker compose -f infra/docker-compose.yml exec redis redis-cli --scan --pattern "portal_session:*" \
  | xargs redis-cli del
```

4. **Set a `maxmemory` policy** in `.env` if not already present to enable automatic eviction.

---

### 4.6 PostgreSQL Connection Exhausted

**Symptoms:** Services log `FATAL: remaining connection slots are reserved`. System health shows `active_connections` near 100 (the PostgreSQL default). New requests fail with 500.

**Diagnosis:**

```bash
docker compose -f infra/docker-compose.yml exec postgres \
  psql -U aigateway -c "
    SELECT state, count(*) FROM pg_stat_activity
    GROUP BY state ORDER BY count DESC;"

docker compose -f infra/docker-compose.yml exec postgres \
  psql -U aigateway -c "
    SELECT pid, state, application_name, query_start, query
    FROM pg_stat_activity
    WHERE state != 'idle'
    ORDER BY query_start;"
```

**Fix options:**

1. **Terminate idle connections** (safe):

```bash
docker compose -f infra/docker-compose.yml exec postgres \
  psql -U aigateway -c "
    SELECT pg_terminate_backend(pid)
    FROM pg_stat_activity
    WHERE state = 'idle'
      AND query_start < NOW() - INTERVAL '10 minutes';"
```

2. **Restart the service with the leak** if a specific service is holding too many connections.

3. **Longer term:** add `pool_size` and `max_overflow` settings to each service's SQLAlchemy engine configuration, or use PgBouncer as a connection pooler.

---

## 5. Database Maintenance

### Tables That Grow Over Time

| Table | Growth driver | Retention strategy |
|-------|--------------|-------------------|
| `cost_records` | One row per AI completion | Archive or delete rows older than 90 days |
| `audit_log` | One row per notable event | Archive or delete rows older than 90 days |
| `api_keys` | Accumulates revoked keys | Safe to delete rows where `revoked_at < NOW() - INTERVAL '1 year'` |

### Check Table Sizes

```sql
SELECT
    relname AS table_name,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
    pg_size_pretty(pg_relation_size(relid)) AS data_size
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC;
```

Run via:

```bash
docker compose -f infra/docker-compose.yml exec postgres \
  psql -U aigateway -c "<SQL above>"
```

### Prune cost_records (older than 90 days)

```bash
docker compose -f infra/docker-compose.yml exec postgres \
  psql -U aigateway -c "
    DELETE FROM cost_records
    WHERE created_at < NOW() - INTERVAL '90 days';"
```

### Prune audit_log (older than 90 days)

```bash
docker compose -f infra/docker-compose.yml exec postgres \
  psql -U aigateway -c "
    DELETE FROM audit_log
    WHERE timestamp < NOW() - INTERVAL '90 days';"
```

### Prune revoked API keys (older than 1 year)

```bash
docker compose -f infra/docker-compose.yml exec postgres \
  psql -U aigateway -c "
    DELETE FROM api_keys
    WHERE revoked_at IS NOT NULL
      AND revoked_at < NOW() - INTERVAL '1 year';"
```

### Vacuum After Large Deletes

```bash
docker compose -f infra/docker-compose.yml exec postgres \
  psql -U aigateway -c "VACUUM ANALYZE cost_records; VACUUM ANALYZE audit_log;"
```

### Back Up the Database

```bash
docker compose -f infra/docker-compose.yml exec postgres \
  pg_dump -U aigateway aigateway | gzip > aigateway-$(date +%Y%m%d).sql.gz
```

---

## 6. Adding a New AI Provider

### Via the Admin UI (preferred)

1. Open the admin portal at `http://localhost:8005`.
2. Navigate to **Settings** (or go directly to `http://localhost:8005/ui/settings`).
3. Find the provider row (Anthropic, OpenAI, Google, or GitHub Models).
4. Enter the API key in the text field for that provider.
5. Click **Save**. The portal:
   - Stores the key in the `provider_keys` table.
   - Sets the env var in the admin process immediately (`os.environ[env_var] = key`).
   - Calls `PATCH /model/update` on LiteLLM for each model belonging to that provider, injecting the key into LiteLLM's in-memory config. No restart required.
6. Click **Test** on the provider row to fire a 1-token test completion. The response shows pass/fail and latency.

### Verify LiteLLM Received the Key

```bash
curl -s -H "Authorization: Bearer sk-litellm-local-dev" \
  http://localhost:8003/v1/models | python3 -c "
import json, sys
models = json.load(sys.stdin)
for m in models.get('data', []):
    print(m['id'])
"
```

The model IDs for the provider should appear in the list.

### Adding a Completely New Provider (code change required)

If the provider is not yet in the `PROVIDERS` list in `services/admin/app/routers/settings.py`:

1. Add an entry to the `PROVIDERS` list with `name`, `icon`, `env_var`, `models`, `litellm_model_names`, and `test_model`.
2. Add the corresponding model rows to `model_registry` and `model_pricing` in `infra/postgres/init.sql`.
3. Add the model to LiteLLM's config file (`services/litellm/config.yaml` or equivalent).
4. Rebuild and restart: `docker compose -f infra/docker-compose.yml up --build admin litellm -d`.

---

## 7. Managing Teams and Rate Limits

### Create a Team

1. Admin portal > **Teams** > **New Team**.
2. Enter a team name and slug (URL-safe identifier).
3. The system creates a `teams` row and a default `policies` row with `rate_limit_rpm=1000`.

### Issue an API Key

1. Admin portal > **Teams** > select team > **API Keys** > **New Key**.
2. Copy the displayed key — it is shown only once. The system stores a hash (`key_hash`), not the plaintext.
3. Distribute the key to the team. They use it as `Authorization: Bearer sk-<key>`.

### Revoke an API Key

1. Admin portal > **Teams** > select team > **API Keys** > click **Revoke** next to the key.
2. The `revoked_at` timestamp is set immediately. Auth will reject the key on the next request.

Or via SQL (emergency revocation):

```bash
docker compose -f infra/docker-compose.yml exec postgres \
  psql -U aigateway -c "
    UPDATE api_keys SET revoked_at = NOW()
    WHERE name = '<key name>';"
```

### Adjust Rate Limits

1. Admin portal > **Teams** > select team > **Policies**.
2. Modify `rate_limit_rpm` (requests per minute per model, fixed 60-second window).
3. Save. The change takes effect on the next rate limit window (up to 60 seconds).

Or via SQL:

```bash
docker compose -f infra/docker-compose.yml exec postgres \
  psql -U aigateway -c "
    UPDATE policies SET rate_limit_rpm = 2000, updated_at = NOW()
    WHERE team_id = (SELECT id FROM teams WHERE slug = '<team-slug>');"
```

### Restrict a Team to Specific Models

In the `policies` table, `allowed_models` is a `TEXT[]` column. An empty array means all models are allowed.

```bash
docker compose -f infra/docker-compose.yml exec postgres \
  psql -U aigateway -c "
    UPDATE policies
    SET allowed_models = ARRAY['gpt-4o-mini', 'claude-haiku-4-5'], updated_at = NOW()
    WHERE team_id = (SELECT id FROM teams WHERE slug = '<team-slug>');"
```

### View Cost Data for a Team

```bash
docker compose -f infra/docker-compose.yml exec postgres \
  psql -U aigateway -c "
    SELECT
        model,
        SUM(tokens_input) AS total_input_tokens,
        SUM(tokens_output) AS total_output_tokens,
        SUM(cost_usd)::numeric(10,4) AS total_cost_usd,
        COUNT(*) FILTER (WHERE cache_hit) AS cache_hits,
        COUNT(*) AS total_requests
    FROM cost_records
    WHERE team_id = (SELECT id FROM teams WHERE slug = '<team-slug>')
      AND created_at >= NOW() - INTERVAL '30 days'
    GROUP BY model
    ORDER BY total_cost_usd DESC;"
```

---

## 8. Log Locations and What to Look For

### Viewing Logs

```bash
# All services, last 200 lines, follow
docker compose -f infra/docker-compose.yml logs -f --tail=200

# Single service
docker compose -f infra/docker-compose.yml logs -f --tail=200 auth
docker compose -f infra/docker-compose.yml logs -f --tail=200 cache
docker compose -f infra/docker-compose.yml logs -f --tail=200 litellm
docker compose -f infra/docker-compose.yml logs -f --tail=200 observability
docker compose -f infra/docker-compose.yml logs -f --tail=200 admin
```

### What to Look For by Service

**auth** — critical log patterns:

| Pattern | Meaning |
|---------|---------|
| `rate limit exceeded` | A team is being throttled — check their rpm policy |
| `Invalid API key` / `revoked` | Attempted use of an invalid or revoked key |
| `Redis connection` error | Auth cannot reach Redis — rate limiting is broken |
| `database` / `asyncpg` error | Cannot look up API keys — all requests will fail auth |

**cache** — critical log patterns:

| Pattern | Meaning |
|---------|---------|
| `embedding` error | Embedding model (Ollama/OpenAI) unreachable — cache bypassed, still functional |
| `Redis` error | Cache read/write failures — requests pass through to LiteLLM |
| `litellm` / upstream error | Provider call failed after cache miss |

**litellm** — critical log patterns:

| Pattern | Meaning |
|---------|---------|
| `AuthenticationError` | Provider API key missing or invalid |
| `RateLimitError` | Provider-side rate limit hit — different from gateway RPM limit |
| `ServiceUnavailableError` | Provider is down |
| `No models available` | LiteLLM has no configured models — check provider keys |

**observability** — critical log patterns:

| Pattern | Meaning |
|---------|---------|
| `database` error | Cannot write cost_records — cost tracking is broken |
| `asyncpg` / `connection` error | Postgres unreachable |

**admin** — critical log patterns:

| Pattern | Meaning |
|---------|---------|
| `SECRET_KEY is set to the development placeholder` | WARNING on startup — set a real `SECRET_KEY` in production |
| `ADMIN_TOKEN not configured` | Admin portal will return 500 for all protected endpoints |
| `LiteLLM push failed` | Provider key saved to DB but not injected into LiteLLM — retry via Settings page |

### Audit Log (in Postgres)

The `audit_log` table records key administrative actions. Query it directly or view the last 8 error entries on the system health dashboard.

```bash
docker compose -f infra/docker-compose.yml exec postgres \
  psql -U aigateway -c "
    SELECT timestamp, actor, action, resource_type, resource_id
    FROM audit_log
    ORDER BY timestamp DESC
    LIMIT 20;"
```

---

## 9. Environment Variables Reference

All services read from the `.env` file at the project root via `env_file: ../.env` in docker-compose. Values in the table below are the defaults when the `.env` file is absent.

### Infrastructure

| Variable | Default | Used by | Description |
|----------|---------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://aigateway:aigateway@localhost:5432/aigateway` | auth, observability, admin | SQLAlchemy async connection string. LiteLLM uses a separate `postgresql://` (no `+asyncpg`) form set in docker-compose directly. |
| `REDIS_URL` | `redis://localhost:6379/0` | auth, cache, admin | Redis connection string |

### Auth Service (:8001)

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis for rate limit counters |
| `DATABASE_URL` | see above | Postgres for API key lookup |
| `JWKS_URI` | `http://dex:5556/dex/keys` | OIDC public key endpoint for JWT validation |
| `ENTRA_TENANT_ID` | `local` | Azure Entra tenant ID (or `local` for Dex) |
| `ENTRA_CLIENT_ID` | `ai-gateway-admin` | Expected `aud` claim in JWTs |
| `RATE_LIMIT_DEFAULT_RPM` | `1000` | Fallback RPM when no policy row exists for a team |

### Cache Service (:8002)

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis for semantic cache storage |
| `LITELLM_URL` | `http://litellm:8003` | Upstream for cache misses |
| `LITELLM_MASTER_KEY` | `sk-litellm-local-dev` | Bearer token for LiteLLM API |
| `AUTH_URL` | `http://auth:8001` | Auth service for upstream validation |
| `OBSERVABILITY_URL` | `http://observability:8004` | Async event posting |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Model used for semantic similarity |
| `EMBEDDING_API_KEY` | `sk-placeholder` | API key for embedding calls |
| `EMBEDDING_BASE_URL` | `http://ollama:11434/v1` | Base URL for embedding API (Ollama or OpenAI) |
| `DEFAULT_SIMILARITY_THRESHOLD` | `0.95` | Cosine similarity threshold for cache hits |
| `DEFAULT_TTL_SECONDS` | `3600` | Cache entry TTL (1 hour) |

### Observability Service (:8004)

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | see above | Postgres for cost_records and audit_log writes |
| `BUS_PROVIDER` | `memory` | Event bus: `memory` (local) or `azure` |
| `AZURE_SERVICE_BUS_CONNECTION_STRING` | _(empty)_ | Required if `BUS_PROVIDER=azure` |
| `AZURE_SERVICE_BUS_TOPIC` | `gateway-events` | Topic name on Azure Service Bus |
| `AZURE_SERVICE_BUS_SUBSCRIPTION` | `gateway-workers` | Subscription name |
| `APPINSIGHTS_CONNECTION_STRING` | _(empty)_ | Azure Application Insights (optional) |

### Admin Portal (:8005)

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | see above | Postgres for all admin data |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis for portal sessions (`portal_session:{token}`) |
| `SECRET_KEY` | `change-me-in-production` | Session signing key — **must be changed in production** |
| `ADMIN_TOKEN` | _(empty)_ | Required `X-Admin-Token` header value when `DEV_BYPASS_AUTH=false` |
| `DEV_BYPASS_AUTH` | `false` | Set `true` in local dev to skip admin token checks |
| `OIDC_ISSUER` | `http://dex:5556/dex` | OIDC issuer URL for admin portal login |
| `OIDC_CLIENT_ID` | `ai-gateway-admin` | OIDC client ID |
| `OIDC_CLIENT_SECRET` | `ai-gateway-admin-secret` | OIDC client secret — **change in production** |
| `LITELLM_MASTER_KEY` | `sk-litellm-local-dev` | Bearer token for LiteLLM management API |
| `AUTH_URL` | `http://auth:8001` | Auth service URL (for health checks) |
| `CACHE_URL` | `http://cache:8002` | Cache service URL (for health checks) |
| `LITELLM_URL` | `http://litellm:8003` | LiteLLM URL (for health checks and key push) |
| `OBSERVABILITY_URL` | `http://observability:8004` | Observability service URL (for health checks) |

### Provider API Keys (stored in DB, also readable from env)

| Variable | Provider |
|----------|----------|
| `ANTHROPIC_API_KEY` | Anthropic (Claude Opus, Sonnet, Haiku) |
| `OPENAI_API_KEY` | OpenAI (GPT-4o, GPT-4o Mini) |
| `GEMINI_API_KEY` | Google (Gemini 1.5 Pro, Flash) |
| `GITHUB_MODELS_API_KEY` | GitHub Models (GPT-4o via GitHub) |
