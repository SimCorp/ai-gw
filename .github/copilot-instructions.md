# Copilot Instructions — AI Gateway (SimCorp Developer Platform)

Enterprise AI gateway serving ~2,000 SimCorp engineers.
FastAPI microservices (Python 3.12) + Next.js frontends (Node 20), running on a single Linux VM via Docker Compose.
Azure Container Apps (ACA) Bicep IaC is in-repo but archived — the current running deployment is the VM.

---

## Repository Layout

```
services/          # Python FastAPI backend services (one dir per service)
  auth/            # JWT / API-key validation, rate limiting  (:8001)
  cache/           # Semantic + exact cache proxy             (:8002)
  litellm/         # Provider routing (OpenAI-compatible)     (:8003)
  observability/   # Async event ingestion                    (:8004)
  admin/           # Org management, API keys, dashboards     (:8005)
  identity/        # Agent registry, DNS-style resolve        (:8006)
  agent-relay/     # WebSocket relay bus                      (:8007)
  librarian/       # Knowledge ingestion, semantic search     (:8008)
  memory/          # Persistent agent memory (user/team)      (:8009)
  league/          # AI-League gamified challenge platform    (:8010)
  scanner/         # Security scanning worker (no ingress)
  workflow-worker/ # Agentic workflow runner (no ingress)
  graphify/        # Graph-building service                   (:8012)
apps/
  admin/           # Admin Next.js portal  (:3001)
  portal/          # Developer Next.js portal (:3002)
packages/
  ui/              # Shared Shadcn UI components
  contracts/       # Shared TypeScript types
  hooks/           # Shared React hooks
  aigw-agent/      # Python CLI — register a local agent with the relay
  charts/          # Shared chart components
infra/
  docker-compose.yml        # Base Compose — always use with docker-compose.host.yml
  docker-compose.host.yml   # VM overlay (GHCR image: keys)
  Caddyfile                 # TLS + reverse proxy config
  bicep/                    # ACA IaC (archived, not running)
  observability/            # Loki / Prometheus / Grafana / Alloy config
docs/
  architecture/             # Service map, org model, environments
  ops-runbook.md            # Deployment, ops procedures, incident response
.github/
  workflows/ci.yml          # Lint → test → build/push to GHCR
  workflows/_archived/      # ACA CI/CD (not running — do NOT modify)
  agentic-workflows/        # Markdown-defined agent workflows
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend language | Python 3.12 |
| Backend framework | FastAPI 0.111 + uvicorn |
| ORM / DB | SQLAlchemy 2 (async) + asyncpg; raw `text()` SQL is common |
| DB migrations | Alembic — `services/admin/migrations/` |
| Databases | PostgreSQL 16 with pgvector; Redis (redis-stack 7.2) |
| Config | pydantic-settings (`app/config.py` per service) |
| Frontend | Next.js (Node 20), pnpm workspace, Turbo |
| UI library | Shadcn UI (packages/ui) |
| Python linter | ruff (line-length 100, py312 target, E+F+I rules) |
| Python formatter | ruff format |
| Frontend linter | ESLint (`pnpm lint`) |
| Python tests | pytest with `asyncio_mode = "auto"` |
| Frontend tests | Vitest (`pnpm test`) |
| Package manager (JS) | pnpm@9 via corepack |
| Containers | Docker Compose (always both files) |
| Image registry | GHCR (`ghcr.io/simcorp/ai-gw/<service>`) |

---

## Lint, Build, and Test Commands

### Python (backend services)

```bash
# Lint all services
ruff check services/
ruff format services/

# Install dev deps for a specific service (repeat for each needed)
pip install -e "services/auth[dev]"
pip install -e "services/cache[dev]"
pip install -e "services/observability[dev]"
pip install -e "services/admin[dev]"
pip install -e "services/identity[dev]"
pip install -e "services/agent-relay[dev]"
# ... etc. Same pattern for all services.

# Run tests for a single service (preferred in CI)
cd services/auth
BUS_PROVIDER=memory ENVIRONMENT=test python3 -m pytest tests/ -v --tb=short

# Run all service tests from repo root (services/conftest.py handles sys.path isolation)
BUS_PROVIDER=memory ENVIRONMENT=test pytest services/ -v
```

**Required env vars for tests** (each service conftest.py sets safe placeholders):
- `BUS_PROVIDER=memory` — disables Azure Service Bus, uses in-process queue
- `ENVIRONMENT=test` — enables test mode (no live credentials required)

**Raw-SQL test suites** (admin, identity) use `testcontainers[postgres]` and need a running Docker daemon.

### Frontend

```bash
corepack enable && corepack prepare pnpm@9 --activate
pnpm install --frozen-lockfile

pnpm lint       # ESLint across all apps + packages
pnpm build      # Turbo build (requires NEXT_PUBLIC_* vars — see ci.yml for values)
pnpm test       # Vitest across all packages
```

---

## Service Patterns and Conventions

### Python service structure (every backend service follows this)

```
services/<name>/
  app/
    __init__.py
    config.py          # pydantic-settings Settings class — all env vars declared here
    logging_config.py  # CorrelationIdMiddleware + init_logging()
    main.py            # FastAPI app, lifespan (Redis/DB init), /health, /ready
    router.py          # Main APIRouter (or routers/ for admin)
    observability.py   # init_observability() — OpenTelemetry + Prometheus
  tests/
    conftest.py        # Sets env placeholders before any app.* import; fixes sys.path
    test_*.py
  pyproject.toml       # [project] + [project.optional-dependencies] dev = [...]
  Dockerfile
  conftest.py          # sys.path fix for this service root
```

### Config pattern

Each service has `app/config.py`:
```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    redis_url: str
    database_url: str
    # ... service-specific fields
    
settings = Settings()
```
`Settings()` is instantiated at module import time — conftest.py must set env vars **before** importing from `app.*`.

### Inter-service communication

Services call each other by Docker container name:
- `http://litellm:8003` — provider routing
- `http://auth:8001` — token validation (called by cache)
- `http://observability:8004` — event ingestion
- `http://librarian:8008` — embeddings/search
- etc.

### Authentication / sessions

- Tokens are either **JWT** or **`sk-`-prefixed API keys**
- Sessions stored in Redis at `session:{token}` (TTL: 8h admin / 7d dev)
- `get_current_user` dependency in `services/admin/app/routers/unified_auth.py` — shared by all admin routers
- Roles: `gateway_admin` (power 6) > `area_owner` (5) > `unit_lead` (4) > `team_admin` (3) > `engineer`/`developer` (2) > `reporter`/`viewer` (1)
- Permission check: `can_access(user, target_path, min_role)` — pure Python path-prefix match on `organization_nodes.path`

### Organization model

`organization_nodes` table: materialized-path tree (path like `/uuid/uuid/...`). Org hierarchy: **Area → Unit → Team**. The old `/areas`, `/units`, `/teams` routers are deprecated; use `/nodes` (in `services/admin/app/routers/nodes.py`).

### Database migrations

Alembic lives in `services/admin/migrations/`. Run in Docker Compose as the `db-migrate` one-shot service. To create a new migration:
```bash
cd services/admin
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

### Logging

Structured JSON. Every service calls `init_logging("<service_name>")` at startup and adds `CorrelationIdMiddleware`. Log fields: `service`, `level`, `request_id`, `session_trace_id`. Follow a request across services by `request_id`.

### Health endpoints

Every service exposes:
- `GET /health` — liveness (process up)
- `GET /ready` — readiness (Redis + Postgres reachable)

---

## Key Files to Know

| File | Purpose |
|---|---|
| `infra/docker-compose.yml` | Base Compose — infrastructure + all services |
| `infra/docker-compose.host.yml` | VM overlay (GHCR image tags, host-specific settings) |
| `infra/Caddyfile` | TLS termination + path-based routing to containers |
| `services/admin/migrations/` | All Alembic DB migrations |
| `services/admin/app/routers/unified_auth.py` | Auth dependency, `can_access()`, role power map |
| `services/admin/app/routers/nodes.py` | Org hierarchy CRUD (`/nodes/*`) |
| `services/admin/app/db.py` | SQLAlchemy async engine (`sslmode` stripping logic) |
| `services/litellm/config.yaml` | LiteLLM provider + model routing config |
| `.env.example` | All env var names with local-dev defaults |
| `pyproject.toml` (root) | ruff config + root pytest config (`asyncio_mode=auto`) |
| `docs/architecture/services.md` | Full service map, request path, data flow |
| `docs/ops-runbook.md` | Deployment, restart, rollback procedures |
| `CLAUDE.md` | Quick-reference for the running deployment |

---

## Common Pitfalls

1. **`app` package name collision** — all services use `app/` as their package root. Never run `pytest services/` without the root `services/conftest.py` present — it handles `sys.path` isolation between services. When running a single service, `cd` into it first.

2. **`DATABASE_URL` with `sslmode`** — `services/admin/app/db.py` strips `?sslmode=...` from the URL before passing to asyncpg (which has no `sslmode` kwarg). Don't add `sslmode` directly to asyncpg DSNs elsewhere.

3. **Both Compose files required** — always run: `docker compose -f docker-compose.yml -f docker-compose.host.yml`. The base file alone is missing host-specific image tags.

4. **Tests need env vars before `app.*` imports** — each service's `conftest.py` sets env var placeholders at the top. If you add a new required config field, add its test placeholder to `tests/conftest.py`.

5. **`BUS_PROVIDER=memory`** — required for tests; omitting it causes the observability service to attempt an Azure Service Bus connection.

6. **Deprecated routers** — `areas.py`, `units.py`, `teams.py` in `services/admin/app/routers/` are not registered in `main.py`. Use `nodes.py` instead.

7. **ACA workflows are archived** — `.github/workflows/_archived/` workflows do NOT run. Do not modify or re-enable them without explicit instruction.

8. **NEXT_PUBLIC_* vars are baked at build time** — Next.js env vars must be set as Docker build args; they cannot be changed at runtime.

9. **LiteLLM uses a separate `litellm` DB** — the `aigateway` DB is owned by Alembic (admin service). Do not run Alembic migrations against the `litellm` DB.

10. **`DEV_BYPASS_AUTH=true`** — local dev env variable that bypasses session auth. Never set in production.

---

## Making Changes

### Adding a new Python service

1. Create `services/<name>/` following the standard layout above.
2. Add `pyproject.toml` with `[dev]` extras including `pytest>=8`, `pytest-asyncio>=0.23`.
3. Add `tests/conftest.py` that sets required env vars before any `app.*` import.
4. Add the service to `infra/docker-compose.yml` and `docker-compose.host.yml`.
5. Add to the `unit-tests` matrix in `.github/workflows/ci.yml`.
6. Add to the `build-push` matrix in `.github/workflows/ci.yml`.
7. Update `infra/Caddyfile` if the service needs external routing.

### Adding a new admin API router

1. Create `services/admin/app/routers/<name>.py` with `router = APIRouter(prefix="/<name>", tags=["<name>"])`.
2. Import and register in `services/admin/app/main.py` using the existing import pattern.
3. Use `get_current_user` as a dependency; check permissions with `can_access()` or `require_node_role()`.

### Adding a DB migration

```bash
cd services/admin
alembic revision --autogenerate -m "short description"
# Review the generated file in migrations/versions/
alembic upgrade head
```

### Frontend changes

- Shared components go in `packages/ui/src/`.
- Shared types go in `packages/contracts/src/`.
- App-specific pages go in `apps/admin/app/` or `apps/portal/app/` (Next.js App Router).
- Run `pnpm lint && pnpm build && pnpm test` before committing.

---

## Request Path (inference)

```
Browser → Caddy:443 → cache:8002
  cache: validates token (calls auth:8001 → POST /validate)
  cache: checks semantic/exact cache (Redis)
  cache hit: return cached response + log to observability:8004
  cache miss: forward to litellm:8003 → provider (OpenAI/Anthropic/etc.)
             store response in cache + log to observability:8004
```

---

## CI Pipeline (`.github/workflows/ci.yml`)

| Job | Trigger | What it does |
|---|---|---|
| `lint-python` | PR + push | `ruff check` + `ruff format --check` on `services/` |
| `lint-frontend` | PR + push | `pnpm lint` + `pnpm build` |
| `test-frontend` | PR + push | `pnpm test` (Vitest) |
| `unit-tests` | PR + push | Per-service pytest matrix (12 services) |
| `security` | PR + push | `pip-audit` CVE scan + `gitleaks` secret scan |
| `build-push` | push only | Builds + pushes all images to GHCR (needs lint+test green) |

CI skips markdown and docs changes (`paths-ignore: ["**.md", "docs/**"]`).

---

## Observability (troubleshooting the running stack)

Query **before** guessing about failures:

```bash
# Logs (Loki) — from the VM via ssh-aigw
curl -s 'http://localhost:3100/loki/api/v1/query_range' \
  --data-urlencode 'query={compose_service="cache"} |= "error"' --data-urlencode 'limit=50'

# Metrics (Prometheus / cAdvisor)
curl -s 'http://localhost:9090/api/v1/query?query=container_memory_usage_bytes{name="ai-gateway-cache-1"}'
```

Grafana UI: `https://dev.aigw.scdom.net/grafana/`

---

## Security Requirements

- **Never commit secrets** — `.gitleaks.toml` defines patterns; CI runs gitleaks on all pushes.
- **Never set `DEV_BYPASS_AUTH=true` outside local dev**.
- New dependencies must be free of known CVEs (CI runs `pip-audit` per service).
- Guardrails (PII detector, secrets scanner) are seeded in `services/admin/app/main.py` — do not remove.
