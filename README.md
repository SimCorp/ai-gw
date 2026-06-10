# AI Gateway — SimCorp Developer Platform

An enterprise API gateway that centralises access to hosted and local LLMs for ~2,000 engineers. It enforces authentication, rate limits, and cost policy before every request reaches a provider, and caches responses to cut spend.

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
               Anthropic      Azure       GitHub   … ollama (local)
               Claude         OpenAI      Models

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
```

Services are ready when all health checks pass (~2 min on first build).

Default dev credentials: `admin@simcorp.com` / `password` (you'll be forced to change on first login).

---

## Service Reference

All services are available via the nginx hub at **http://localhost:8080** — no need to remember individual port numbers.

| Service | Via nginx (preferred) | Direct port | Purpose |
|---|---|---|---|
| auth | http://localhost:8080/auth/ | :8001 | API key / JWT validation, per-team rate limiting |
| cache | http://localhost:8080/cache/ | :8002 | Semantic + exact cache proxy; public LLM endpoint |
| litellm | http://localhost:8080/litellm/ | :8003 | Provider routing, retries, fallbacks (OpenAI-compatible) |
| observability | http://localhost:8080/observability/ | :8004 | Async event ingestion, cost accounting |
| admin | http://localhost:8080/admin/ | :8005 | Operator + developer portal backend |
| identity | http://localhost:8080/identity/ | :8006 | Agent registry — DNS-style resolve, heartbeat TTL |
| agent-relay | http://localhost:8080/agent-relay/ | :8007 | WebSocket relay bus for agentic workflows |
| librarian | http://localhost:8080/librarian/ | :8008 | Knowledge ingestion, chunking, semantic search |
| memory | http://localhost:8080/memory/ | :8009 | Persistent agent memory scoped to user/team |
| league | http://localhost:8080/league/ | :8010 | AI-League gamified challenge platform |
| admin-portal | http://localhost:8080/admin-portal/ | :3001 | Admin Next.js app |
| portal | http://localhost:8080/portal/ | :3002 | Developer Next.js app |
| redis | — | :6379 | Cache store + rate-limit counters |
| postgres | — | :5432 | Teams, API keys, policies, cost records |
| dex (mock OIDC) | — | :5556 | Local Entra ID substitute for development |
| ollama | — | :11434 | Local model serving (opt-in via `--profile ollama`) |

> **Ports are pinned.** The nginx config in `infra/nginx/default.conf` hardcodes these port numbers — changing any service port in `docker-compose.yml` requires a matching update there.

---

## Using the Gateway

All API calls go to the **cache service** at `:8002`. Authenticate with an `sk-*` API key.

### OpenAI-compatible

```bash
curl http://localhost:8002/v1/chat/completions \
  -H "Authorization: Bearer sk-your-team-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-6",
    "messages": [{"role": "user", "content": "Summarise this quarter in one sentence."}]
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
```

### Python (anthropic SDK)

```python
import anthropic

client = anthropic.Anthropic(
    base_url="http://localhost:8002/anthropic",
    api_key="sk-your-team-key",
)
message = client.messages.create(model="claude-sonnet-4-6", max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}])
```

---

## Identity & Access

The platform uses a unified identity model — one `users` table for all human principals (admins, area owners, team admins, developers, viewers) and a separate `user_invitations` / `service_accounts` table for non-human principals.

### Roles

| Role | Where | What they can do |
|---|---|---|
| `platform_admin` | Global | Full access to all admin APIs and portals |
| `area_owner` | Area-scoped | Manage teams and policies within their area |
| `team_admin` | Team-scoped | Manage team members, API keys, and budgets |
| `developer` | Global | Developer portal access, personal API keys, usage stats |
| `viewer` | Global | Read-only developer portal access |
| `service_account` | — | API key only, no portal login |

### Auth endpoints (`/auth/*`)

| Method | Path | Auth required | Description |
|---|---|---|---|
| `POST` | `/auth/login` | — | Email + password login; returns session token |
| `POST` | `/auth/register` | — | Self-service developer sign-up |
| `GET` | `/auth/me` | Session | Current user profile + roles |
| `POST` | `/auth/logout` | Session | Invalidate session |
| `POST` | `/auth/change-password` | Session | Change password (clears session) |
| `GET` | `/auth/oidc/login` | — | Redirect to Entra ID / Dex for SSO |
| `GET` | `/auth/oidc/callback` | — | OIDC callback; creates/links user, issues session |
| `POST` | `/auth/invitations` | Session (admin/team_admin) | Create an invite link (48 h expiry) |
| `GET` | `/auth/invitations` | Session (admin/team_admin) | List invitations |
| `DELETE` | `/auth/invitations/{id}` | Session (admin/team_admin) | Revoke pending invite |
| `POST` | `/auth/invitations/accept` | — | Redeem invite token, create account |
| `POST` | `/auth/service-accounts` | Session (admin/team_admin) | Create service account + API key |
| `GET` | `/auth/service-accounts` | Session (admin/team_admin) | List service accounts |
| `PATCH` | `/auth/service-accounts/{id}/status` | Session | Suspend / revoke |
| `POST` | `/auth/service-accounts/{id}/rotate-key` | Session | Rotate API key |
| `GET` | `/auth/users` | Session (platform_admin) | List all users |
| `POST` | `/auth/users/{id}/roles` | Session (platform_admin) | Grant role |
| `DELETE` | `/auth/users/{id}/roles/{role}` | Session (platform_admin) | Revoke role |
| `PATCH` | `/auth/users/{id}/status` | Session (platform_admin) | Suspend / activate user |

### SSO configuration

The gateway ships with a local Dex instance for development. To switch to real Azure Entra ID, set these variables in `.env`:

```ini
OIDC_ISSUER=https://login.microsoftonline.com/<tenant-id>/v2.0
OIDC_CLIENT_ID=<app-registration-client-id>
OIDC_CLIENT_SECRET=<client-secret>
```

The redirect URI to register in Azure: `https://<your-host>/auth/oidc/callback`

---

## Admin Portal

**http://localhost:3001/admin**

Sign in with `admin@simcorp.com` / `password` (dev). Forced password change on first login.

| Page | Path | Function |
|---|---|---|
| Dashboard | `/admin` | Live cost, request count, cache-hit rate |
| Users & Access | `/admin/users` | Invite users, manage roles, suspend accounts, view service accounts |
| Teams | `/admin/teams` | Create/edit teams, set spend limits |
| Areas | `/admin/areas` | Group teams into business areas |
| API Keys | `/admin/api-keys` | Issue and revoke `sk-*` keys |
| Policies | `/admin/policies` | Per-team model allow-lists, rate limits |
| Guardrails | `/admin/guardrails` | Input/output safety rules |
| Pricing | `/admin/pricing` | Per-model cost configuration |
| Model Registry | `/admin/models` | Enable/disable models |
| MCP Servers | `/admin/mcp` | Manage Model Context Protocol server registry |
| AI Transformation | `/admin/transformation` | Org-wide agentic adoption metrics and team leaderboard |
| Audit Log | `/admin/audit` | Immutable request history |
| System Health | `/admin/system` | Health status of all services |
| Insights | `/admin/insights` | Cost and usage analytics |

### Inviting users

1. Go to **Users & Access → + Invite user**
2. Enter email and select role
3. Copy the invite link and send it to the user
4. The link expires in 48 hours and creates the account on redemption — no email relay needed

---

## Developer Portal

**http://localhost:3002/portal**

Self-service for developers. Sign up with email + password, or use the **Sign in with Entra ID (SSO)** button.

- Generate `sk-*` API keys scoped to your team
- View personal usage stats, cost per PR, and cache hit rate
- Track your AI transformation score and achievements (agentic first-mover badge, etc.)
- Opt in to the team or company leaderboard
- Set up webhook hooks for automated session tracking

### Force password change

New accounts (invited or bootstrapped) require a password change on first login. The portal shows an inline form — you cannot access any other page until you set a new password meeting the strength requirements (12+ chars, upper, lower, digit, special).

### Remember me

The "Stay signed in for 30 days" checkbox on login stores the session token in `localStorage` instead of `sessionStorage`, so it persists across browser restarts.

---

## AI Transformation Tracking

The platform classifies every session as **interactive**, **agentic**, or **autonomous** based on turn count, inter-request timing, and tool invocation density.

### Developer view (`/portal/transformation`)

- Agentic score (0–100) with SVG ring visualisation
- Weekly bar chart: agentic vs interactive sessions
- Achievement badge grid (First Agentic Session, 10-session streak, Top 10% team, etc.)
- Leaderboard opt-in: per-team and company-wide
- Setup tab with Claude Code hook instructions

### Admin view (`/admin/transformation`)

- Organisation-wide adoption chart (12-week rolling)
- Team summary table with agentic percentage bars and laggard detection
- Per-developer drill-down rows
- Manual classify trigger (`POST /admin/transformation/classify`)

### Session classification

Run manually or on a schedule:

```bash
curl -s -X POST http://localhost:8005/admin/transformation/classify \
  -H "Authorization: Bearer <admin-token>"
```

---

## Available Models

| Model ID | Provider |
|---|---|
| `claude-sonnet-4-6` | Anthropic |
| `claude-opus-4-7` | Anthropic |
| `claude-haiku-4-5` | Anthropic |
| `gpt-4o` | OpenAI |
| `gpt-4o-mini` | OpenAI |
| `azure-gpt-4o` | Azure OpenAI |
| `azure-gpt-4.1` | Azure OpenAI |
| `phi-4` | Azure AI Foundry |
| `deepseek-r1` | Azure AI Foundry |
| `llama-3.3-70b` | Azure AI Foundry |
| `copilot-gpt-4o` | GitHub Copilot |
| `gemini-1.5-pro` | Google |
| `local` | Ollama (llama3.2) — requires `--profile ollama` |

---

## Development

### Makefile commands

| Command | Description |
|---|---|
| `make up` | Build and start the full gateway stack |
| `make down` | Stop and remove containers |
| `make logs` | Tail logs from all services |
| `make test` | Run the full pytest suite against a live stack |
| `make test-smoke` | Health and auth checks only |
| `make sandbox` | Start the SSH-accessible Claude Code sandbox on port 2222 |

### Run tests locally (no Docker)

```bash
pip install \
  -e "services/auth[dev]" \
  -e "services/cache[dev]" \
  -e "services/observability[dev]" \
  -e "services/admin[dev]"

pytest services/ -v
```

### Lint

```bash
ruff check services/
ruff format services/
```

### Project layout

```
infra/
  docker-compose.yml     Full stack compose file
  dex/config.yaml        OIDC provider config (swap issuer for real Entra ID)
  postgres/              DB init scripts
services/
  auth/                  API key validation, JWT, rate limiting, budget enforcement
  cache/                 Semantic + exact caching proxy
  litellm/               Provider routing (config.yaml drives model list)
  observability/         Async event store, cost records, session classification
  admin/                 Operator + developer portal (FastAPI)
    app/routers/
      unified_auth.py    Single /auth/* surface for all user types
      admin_auth.py      /admin-auth/* shim (backwards compat)
      dev_auth.py        /dev-auth/* shim (backwards compat)
      transformation.py  AI transformation metrics
      users.py           Admin user management queries
    migrations/          Alembic migration chain (0001 → 0011)
apps/
  admin/                 Next.js admin portal (port 3001)
  portal/                Next.js developer portal (port 3002)
docs/
  api-reference.md       Full API reference
  developer-guide.md     Developer integration guide
  ops-runbook.md         Operations and incident runbook
  SYSTEM_REFERENCE.md    Deep architecture reference
```

---

## Configuration

All services read from the `.env` file at repo root.

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | for Claude | Anthropic API key |
| `GEMINI_API_KEY` | for Gemini | Google AI Studio key |
| `GITHUB_MODELS_API_KEY` | for GitHub Models | GitHub PAT |
| `LITELLM_MASTER_KEY` | yes | Shared secret between services |
| `SECRET_KEY` | yes (prod) | Session signing key |
| `ADMIN_TOKEN` | yes (prod) | Static bearer token for CI/automation |
| `DEV_BYPASS_AUTH` | no | `true` skips admin auth in dev |
| `OIDC_ISSUER` | no | OIDC issuer URL (default: local Dex) |
| `OIDC_CLIENT_ID` | no | OIDC client ID |
| `OIDC_CLIENT_SECRET` | no | OIDC client secret |
| `ALLOWED_EMAIL_DOMAINS` | no | Comma-separated list; restricts self-registration |
| `REDIS_URL` | no | Default `redis://localhost:6379/0` |
| `SECONDARY_GATEWAY_URL` | no | Optional shadow target for mirrored cache-service chat requests |
| `SECONDARY_GATEWAY_SAMPLE_RATE` | no | Fraction from `0.0` to `1.0` of chat requests to mirror |
| `DATABASE_URL` | no | Default `postgresql+asyncpg://aigateway:aigateway@localhost:5432/aigateway` |

Minimum viable local `.env`:

```ini
ANTHROPIC_API_KEY=sk-ant-...
LITELLM_MASTER_KEY=sk-litellm-local-dev
SECRET_KEY=change-me-in-production
DEV_BYPASS_AUTH=true
```

---

## Database Migrations

Migrations are managed by Alembic and run automatically at startup via the `db-migrate` service.

| Migration | Description |
|---|---|
| 0001–0007 | Core schema: teams, API keys, policies, cost records, sessions, guardrails |
| 0008 | `must_change_password` on developer accounts |
| 0009 | Agentic session classification, achievements, leaderboard opt-in |
| 0010 | Unified identity: `users` + `user_roles` tables; migrates `admin_users` + `developers` |
| 0011 | `user_invitations` + `service_accounts` tables |

To run manually:

```bash
docker compose -f infra/docker-compose.yml run --rm db-migrate
```
