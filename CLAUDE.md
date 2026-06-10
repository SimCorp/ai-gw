# AI Gateway — SimCorp Developer Platform

Enterprise AI gateway for ~2000 engineers. FastAPI services behind a shared Redis + PostgreSQL, orchestrated via Docker Compose for local development.

## Quick start

```bash
cp .env.example .env        # edit if you want real provider keys
docker compose -f infra/docker-compose.yml up --build
```

## Service ports

These ports are pinned — they do not change. See `infra/html/index.html` for the dev hub (served at `localhost:8080`).

| Service | URL (nginx) | Direct port | Purpose |
|---|---|---|---|
| **Portals** | | | |
| admin-portal | http://localhost:8080/admin-portal/ | http://localhost:3001/admin-portal/ | Admin Next.js app |
| portal | http://localhost:8080/portal/ | http://localhost:3002/portal/ | Developer Next.js app |
| **API services** | | | |
| auth | http://localhost:8080/auth/ | http://localhost:8001 | JWT / API key validation, rate limiting |
| cache | http://localhost:8080/cache/ | http://localhost:8002 | Semantic + exact cache proxy |
| litellm | http://localhost:8080/litellm/ | http://localhost:8003 | Provider routing (OpenAI-compatible) |
| observability | http://localhost:8080/observability/ | http://localhost:8004 | Async event ingestion |
| admin | http://localhost:8080/admin/ | http://localhost:8005 | Team management, API keys, dashboards |
| identity | http://localhost:8080/identity/ | http://localhost:8006 | Agent registry — DNS-style resolve, heartbeat TTL |
| agent-relay | http://localhost:8080/agent-relay/ | http://localhost:8007 | WebSocket relay bus for agentic workflows |
| librarian | http://localhost:8080/librarian/ | http://localhost:8008 | Knowledge ingestion, chunking, semantic search |
| memory | http://localhost:8080/memory/ | http://localhost:8009 | Persistent agent memory scoped to user/team |
| league | http://localhost:8080/league/ | http://localhost:8010 | AI-League gamified challenge platform |
| scanner | http://localhost:8080/scanner/ | http://localhost:8011 | Self-service security scanning (pen-test) for developer teams |
| it-tools | http://localhost:8080/tools-app/ | — (internal) | Developer utility tools (proxied SPA) |
| **Infrastructure** | | | |
| redis | — | localhost:6379 | Cache + rate limit counters |
| postgres | — | localhost:5432 | Teams, policies, cost records |
| dex (mock OIDC) | — | http://localhost:5556 | Local Entra ID substitute |
| ollama | — | http://localhost:11434 | Local model serving (opt-in: `--profile ollama`) |

## Running tests

```bash
pip install \
  -e "services/auth[dev]" \
  -e "services/cache[dev]" \
  -e "services/observability[dev]" \
  -e "services/admin[dev]" \
  -e "services/identity[dev]" \
  -e "services/agent-relay[dev]"

pytest services/ -v
```

> Note: most service tests run without Docker. The `identity` suite is the
> exception — it uses `testcontainers[postgres]` and needs a running Docker
> daemon (matching the `admin` service's approach).

## Linting

```bash
ruff check services/
ruff format services/
```

## Architecture

See `docs/superpowers/specs/2026-05-05-ai-gateway-design.md` for the full design.

Request path: `caller → auth(:8001) → cache(:8002) → litellm(:8003) → provider`

The admin portal (:8005) is a standalone web app sharing the same Postgres instance.
