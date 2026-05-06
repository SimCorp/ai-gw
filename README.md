# AI Gateway — SimCorp Developer Platform

An enterprise API gateway that centralises access to hosted and local LLMs for ~2000 engineers. It enforces authentication, rate limits, and cost policy before every request reaches a provider, and caches responses to cut spend.

Five FastAPI services share a single PostgreSQL database and Redis instance. Developers interact through an OpenAI-compatible endpoint at `:8002`; operators manage everything through the admin portal at `:8005`.

---

## Architecture

```
                        ┌─────────────────────────────────────────────┐
                        │           Developer / CI caller              │
                        └──────────────────┬──────────────────────────┘
                                           │  sk-*  API key or JWT
                                           ▼
                        ┌──────────────────────────────────┐
                        │   auth  :8001                    │
                        │   • validates sk-* / JWT          │
                        │   • rate-limit (Redis fixed-win)  │
                        │   • injects team identity header  │
                        └──────────────────┬───────────────┘
                                           │
                                           ▼
                        ┌──────────────────────────────────┐
                        │   cache  :8002                   │
                        │   • exact-match cache (Redis)    │
                        │   • semantic cache (embeddings)  │
                        │   • OpenAI + Anthropic endpoints  │
                        └──────────────────┬───────────────┘
                                           │ cache miss
                                           ▼
                        ┌──────────────────────────────────┐
                        │   litellm  :8003                 │
                        │   • provider routing             │
                        │   • retries + fallbacks          │
                        │   • model name normalisation     │
                        └──────┬──────────┬───────┬────────┘
                               │          │       │
                    ┌──────────┘  ┌───────┘  ┌───┘
                    ▼             ▼           ▼
               Anthropic      Google       GitHub   … ollama (local)
               Claude         Gemini       Models

      ┌─────────────────────┐        ┌─────────────────────┐
      │  observability:8004 │        │  admin  :8005        │
      │  async event log    │        │  operator portal     │
      │  cost accounting    │        │  developer portal    │
      └─────────────────────┘        └─────────────────────┘

      ─────────────── shared ────────────────────────────────
                PostgreSQL :5432          Redis :6379
```

---

## Quick Start

```bash
# 1. Copy env template and fill in at least one provider key
cp .env.example .env

# 2. Start everything
make up

# 3. (optional) also start ollama for local model serving
docker compose -f infra/docker-compose.yml --profile ollama up --build
```

Services are ready when all health checks pass (~2 min on first build).

---

## Service Reference

| Service | URL | Purpose |
|---|---|---|
| auth | http://localhost:8001 | API key / JWT validation, per-team rate limiting |
| cache | http://localhost:8002 | Semantic + exact cache proxy; public LLM endpoint |
| litellm | http://localhost:8003 | Provider routing, retries, fallbacks (OpenAI-compatible) |
| observability | http://localhost:8004 | Async event ingestion, cost accounting |
| admin | http://localhost:8005 | Operator portal: teams, keys, dashboards, model registry |
| redis | localhost:6379 | Cache store + rate-limit counters |
| postgres | localhost:5432 | Teams, API keys, policies, cost records |
| dex (mock OIDC) | http://localhost:5556 | Local Entra ID substitute for development |
| ollama | http://localhost:11434 | Local model serving (opt-in profile) |
| claude-sandbox | localhost:2222 | SSH-accessible Claude Code sandbox (`make sandbox`) |

All five application services expose a `GET /health` endpoint that returns `{"status": "ok"}`.

---

## Using the Gateway

All API calls go to the **cache service** at `:8002`. Authenticate with an `sk-*` API key in the `Authorization` header.

### OpenAI-compatible endpoint

```bash
curl http://localhost:8002/v1/chat/completions \
  -H "Authorization: Bearer sk-your-team-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-6",
    "messages": [{"role": "user", "content": "Summarise this quarter in one sentence."}]
  }'
```

### Anthropic-compatible endpoint

```bash
curl http://localhost:8002/anthropic/v1/messages \
  -H "x-api-key: sk-your-team-key" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-6",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

### Python (openai SDK)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8002/v1",
    api_key="sk-your-team-key",
)

response = client.chat.completions.create(
    model="claude-sonnet-4-6",
    messages=[{"role": "user", "content": "Write a Python hello world."}],
)
print(response.choices[0].message.content)
```

### Python (anthropic SDK)

```python
import anthropic

client = anthropic.Anthropic(
    base_url="http://localhost:8002/anthropic",
    api_key="sk-your-team-key",
)

message = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}],
)
print(message.content[0].text)
```

---

## Available Models

| Model ID | Provider | Notes |
|---|---|---|
| `claude-sonnet-4-6` | Anthropic | Default; falls back to `gemini-1.5-pro` on failure |
| `claude-opus-4-7` | Anthropic | Highest capability |
| `claude-haiku-4-5` | Anthropic | Fastest / cheapest Anthropic option |
| `gemini-1.5-pro` | Google | Fallback for Anthropic failures |
| `github-gpt-4o` | GitHub Models (Azure) | GPT-4o via `models.inference.ai.azure.com` |
| `local` | Ollama (llama3.2) | No external API key; requires `--profile ollama` |

LiteLLM retries up to 3 times and allows 1 fail before activating the fallback chain.

---

## Admin Portal

**http://localhost:8005**

Requires the `ADMIN_TOKEN` value (set in `.env`) as a bearer token. Set `DEV_BYPASS_AUTH=true` in `.env` to skip auth for local development.

Sections:

| Page | Path | Function |
|---|---|---|
| Dashboard | `/` | Live cost, request count, cache-hit rate |
| Teams | `/teams` | Create/edit teams, set spend limits |
| Members | `/teams/{id}/members` | Add/remove team members |
| API Keys | `/api-keys` | Issue and revoke `sk-*` keys |
| Policies | `/policies` | Per-team model allow-lists, rate limits |
| Pricing | `/pricing` | Per-model cost configuration |
| Model Registry | `/model-registry` | Enable/disable models, view config |
| Audit Log | `/audit-log` | Immutable request history |
| System Health | `/system` | Health status of all five services |
| System Health UI | `/system/health/ui` | Visual health dashboard with live status indicators |
| Settings | `/settings` | Provider and gateway configuration |

---

## Developer Self-Service Portal

**http://localhost:8005/portal**

No admin credentials needed. Sign up with an email address and password — no OIDC account required.

- Sign up and get a personal team created automatically
- Generate `sk-*` API keys scoped to your team
- View a quickstart guide with copy-paste code examples
- Read the agent integration guide for CI/CD and IDE tooling

---

## Development

### Makefile commands

| Command | Description |
|---|---|
| `make up` | Build and start the full gateway stack |
| `make down` | Stop and remove containers |
| `make logs` | Tail logs from all services |
| `make test` | Run the full containerised pytest suite (50 tests) against a live stack |
| `make test-smoke` | Smoke tests only — fast health and auth checks |
| `make test-proxy` | Proxy and cache path tests |
| `make sandbox` | Start the SSH-accessible Claude Code sandbox on port 2222 |
| `make claude-agent` | Launch an interactive Claude agent (no SSH) |

### Lint and format

```bash
ruff check services/
ruff format services/
```

### Project layout

```
infra/              Docker Compose, Postgres init SQL, Dex OIDC config
services/
  auth/             API key validation, JWT verification, rate limiting
  cache/            Semantic + exact caching proxy
  litellm/          Provider routing (config.yaml drives the model list)
  observability/    Async event store, cost records
  admin/            Operator + developer portal (FastAPI + Bootstrap 5)
tests/              Containerised integration test suite (run via make test)
docs/               Design specs and ADRs
```

---

## Test Suite

The `tests/` directory contains a containerised pytest suite with ~50 integration tests. Tests run against a live gateway stack and use `DEV_BYPASS_AUTH=true` for local runs.

```bash
# Requires the gateway stack to be running first
make up
make test

# Focused runs
make test-smoke   # health checks, auth validation
make test-proxy   # cache and proxy path coverage
```

---

## Claude Sandbox

`make sandbox` starts a Docker container with the Claude Code CLI pre-installed, exposing SSH on port 2222. It provides an isolated, gateway-connected environment for running Claude agents against the local stack.

**Connect:**

```bash
ssh claude@localhost -p 2222
# password: gateway
```

**Inside the container, run `go`** — an interactive setup wizard that prompts for your Anthropic API key (paste an existing key, create a new one, or use the developer portal), lets you select a model, then launches Claude Code with `ANTHROPIC_BASE_URL` pre-configured to point at the gateway.

```bash
claude@sandbox:~$ go
# Follow the prompts, then Claude Code starts automatically
```

All traffic is routed through the gateway, so cost accounting, caching, and rate limiting apply.

---

## Configuration

All services read from the `.env` file at repo root. Key variables:

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | for Claude models | Anthropic API key |
| `GEMINI_API_KEY` | for Gemini | Google AI Studio key |
| `GITHUB_MODELS_API_KEY` | for `github-gpt-4o` | GitHub Models PAT |
| `LITELLM_MASTER_KEY` | yes | Shared secret between cache/admin and litellm; default `sk-litellm-local-dev` |
| `SECRET_KEY` | yes (prod) | Session signing key for admin portal; default is insecure placeholder |
| `ADMIN_TOKEN` | yes (prod) | Bearer token for admin API; required when `DEV_BYPASS_AUTH=false` |
| `DEV_BYPASS_AUTH` | no | Set `true` to skip admin auth in local dev; default `false` |
| `REDIS_URL` | no | Default `redis://localhost:6379/0` |
| `DATABASE_URL` | no | Default `postgresql+asyncpg://aigateway:aigateway@localhost:5432/aigateway` |
| `JWKS_URI` | no | OIDC JWKS endpoint; default points to local Dex |
| `EMBEDDING_API_KEY` | for semantic cache | Key for the embeddings model used by the cache service |
| `EMBEDDING_BASE_URL` | no | Default `http://ollama:11434/v1` (uses local Ollama) |

Minimum viable local `.env` to get all services running with Claude:

```ini
ANTHROPIC_API_KEY=sk-ant-...
LITELLM_MASTER_KEY=sk-litellm-local-dev
SECRET_KEY=change-me-in-production
DEV_BYPASS_AUTH=true
```

---

## Full Design Doc

`docs/superpowers/specs/2026-05-05-ai-gateway-design.md`
