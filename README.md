# AI Gateway — SimCorp Developer Platform

An enterprise API gateway that centralises access to hosted LLMs for ~2,000 engineers. It enforces authentication, rate limits, and cost policy before every request reaches a provider, and caches responses to cut spend.

The platform runs on **Azure Container Apps** in the SimCorp Landing Zone (Sweden Central). Developers reach it over the corporate VPN at the gateway's dev FQDN; operators manage everything through the admin portal. There is no local stack — see [Deploying & running](#deploying--running).

---

## Architecture

```
                        ┌─────────────────────────────────────────────┐
                        │      Developer / CI caller (corp VPN)        │
                        └──────────────────┬──────────────────────────┘
                                           │  sk-*  API key or JWT
                                           │  https://aigw-dev.lab.cloud.scdom.net
                                           ▼
                        ┌──────────────────────────────────┐
                        │   auth  (ca-auth)                 │
                        │   • validates sk-* / JWT          │
                        │   • rate-limit (Redis fixed-win)  │
                        │   • injects team identity header  │
                        └──────────────────┬───────────────┘
                                           ▼
                        ┌──────────────────────────────────┐
                        │   cache  (ca-cache)               │
                        │   • exact-match cache (Redis)     │
                        │   • semantic cache (embeddings)   │
                        │   • OpenAI + Anthropic endpoints  │
                        └──────────────────┬───────────────┘
                                           │ cache miss
                                           ▼
                        ┌──────────────────────────────────┐
                        │   litellm  (ca-litellm)           │
                        │   • provider routing              │
                        │   • retries + fallbacks           │
                        │   • model name normalisation      │
                        └──────┬──────────┬───────┬─────────┘
                               │          │       │
                    ┌──────────┘  ┌───────┘  ┌────┘
                    ▼             ▼          ▼
               Anthropic      Azure       GitHub
               Claude         OpenAI      Models

      ┌─────────────────────┐        ┌─────────────────────┐
      │  observability      │        │  admin               │
      │  async event log    │        │  operator portal     │
      │  cost accounting    │        │  developer portal     │
      └─────────────────────┘        └─────────────────────┘

      ──────────────── managed PaaS (private endpoints) ─────────────
        Azure Database for PostgreSQL    Azure Cache for Redis
        Azure Key Vault                  Azure Service Bus
```

Each service is a Container App (`ca-<service>-dev-sdc`) with internal ingress; the ACA environment is `internal: true` (no public IP). The `auth` app fronts the inference request path and is exposed on the custom domain. PaaS dependencies (PostgreSQL Flexible Server, Cache for Redis, Key Vault, Service Bus) are reached over private endpoints. See [`docs/superpowers/specs/2026-06-08-azure-enterprise-deployment-design.md`](docs/superpowers/specs/2026-06-08-azure-enterprise-deployment-design.md) for the full deployment design.

---

## Access

The gateway is **VNet-only**, reachable over the corporate VPN. There is no public endpoint.

| Environment | Gateway FQDN | Subscription | Region |
|---|---|---|---|
| Dev | `https://aigw-dev.lab.cloud.scdom.net` | SC LZ PlatformAITooling Dev | Sweden Central |
| Test | (provisioned in Phase 4) | SC LZ PlatformAITooling Test | Sweden Central |

Sign in to the portals with your SimCorp identity via **Entra ID SSO**.

---

## Using the Gateway

All API calls go to the gateway FQDN and are authenticated with an `sk-*` API key.

### OpenAI-compatible

```bash
curl https://aigw-dev.lab.cloud.scdom.net/v1/chat/completions \
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
    base_url="https://aigw-dev.lab.cloud.scdom.net/v1",
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
    base_url="https://aigw-dev.lab.cloud.scdom.net/anthropic",
    api_key="sk-your-team-key",
)
message = client.messages.create(model="claude-sonnet-4-6", max_tokens=1024,
    messages=[{"role": "user", "content": "Hello"}])
```

---

## Services

| Service | Container App | Internal port | Purpose |
|---|---|---|---|
| auth | `ca-auth-dev-sdc` | 8001 | API key / JWT validation, per-team rate limiting; inference entry point |
| cache | `ca-cache-dev-sdc` | 8002 | Semantic + exact cache proxy; OpenAI/Anthropic endpoints |
| litellm | `ca-litellm-dev-sdc` | 8003 | Provider routing, retries, fallbacks (OpenAI-compatible) |
| observability | `ca-observability-dev-sdc` | 8004 | Async event ingestion, cost accounting |
| admin | `ca-admin-dev-sdc` | 8005 | Operator + developer portal backend |
| identity | `ca-identity-dev-sdc` | 8006 | Agent registry — DNS-style resolve, heartbeat TTL |
| agent-relay | `ca-agent-relay-dev-sdc` | 8007 | WebSocket relay bus for agentic workflows |
| librarian | `ca-librarian-dev-sdc` | 8008 | Knowledge ingestion, chunking, semantic search |
| memory | `ca-memory-dev-sdc` | 8009 | Persistent agent memory scoped to user/team |
| league | `ca-league-dev-sdc` | 8010 | AI-League gamified challenge platform |
| scanner | `ca-scanner-dev-sdc` | — | Security scanning worker (background) |
| workflow-worker | `ca-workflow-worker-dev-sdc` | — | Agentic workflow runner (background, scale-to-zero) |
| admin-portal | `ca-admin-portal-dev-sdc` | 3001 | Admin Next.js app |
| portal | `ca-portal-dev-sdc` | 3002 | Developer Next.js app |

Services discover each other over the ACA environment's internal DNS (`http://ca-<service>-dev-sdc`). Managed PaaS — PostgreSQL, Redis, Key Vault, Service Bus — is reached over private endpoints; connection strings are injected from Key Vault via each app's managed identity.

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
| `GET` | `/auth/oidc/login` | — | Redirect to Entra ID for SSO |
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

Authentication is handled by **Azure Entra ID**. The OIDC settings are supplied to the `auth` and `admin` Container Apps from Key Vault:

```ini
OIDC_ISSUER=https://login.microsoftonline.com/aa81b43f-3969-4fd4-80c9-84c411508d82/v2.0
OIDC_CLIENT_ID=<app-registration-client-id>
OIDC_CLIENT_SECRET=<client-secret>   # Key Vault secret ref
```

The redirect URI registered in Entra ID: `https://aigw-dev.lab.cloud.scdom.net/auth/oidc/callback`

---

## Admin Portal

Reachable over the VPN (Admin Container App). Sign in with your SimCorp identity via Entra ID SSO.

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

Reachable over the VPN (Developer Container App). Sign in with **Entra ID (SSO)**.

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
curl -s -X POST https://aigw-dev.lab.cloud.scdom.net/api/admin/transformation/classify \
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

---

## Deploying & running

The platform is deployed via Bicep to Azure Container Apps. CI builds and pushes service images; `deploy.yml` deploys them on a `master` push.

### Deploy (dev)

```bash
az deployment group create \
  --resource-group rg-aigw-dev-sdc \
  --template-file infra/bicep/environments/dev/main.bicep \
  --parameters infra/bicep/environments/dev/main.bicepparam \
  --parameters imageTag=sha-<git-sha>
```

Deployments are idempotent; rollback is a re-deploy with the previous `imageTag` (ACA revisions are atomic). See [`docs/ops-runbook.md`](docs/ops-runbook.md) for revision management, log streaming, and scale rules.

### Run tests

Fast unit/integration tests run locally — no deployed environment needed. The raw-SQL suites (e.g. `identity`, `admin`) use `testcontainers`, which needs a running Docker daemon.

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

End-to-end smoke tests run against the deployed Azure environment from a VNet-connected runner (see `deploy.yml`).

### Lint

```bash
ruff check services/
ruff format services/
```

### Project layout

```
infra/
  bicep/
    environments/dev/      main.bicep + main.bicepparam (per-env values)
    environments/test/     Test environment parameters
    modules/               networking, containerEnv, containerApps, postgres,
                           redis, keyVault, acr, serviceBus, monitoring, …
services/
  auth/                  API key validation, JWT, rate limiting, budget enforcement
  cache/                 Semantic + exact caching proxy
  litellm/               Provider routing (config.yaml drives model list)
  observability/         Async event store, cost records, session classification
  admin/                 Operator + developer portal (FastAPI)
    app/routers/
      unified_auth.py    Single /auth/* surface for all user types
      transformation.py  AI transformation metrics
      users.py           Admin user management queries
    migrations/          Alembic migration chain
  identity/ agent-relay/ librarian/ memory/ league/ scanner/ workflow-worker/
apps/
  admin/                 Next.js admin portal
  portal/                Next.js developer portal
docs/
  api-reference.md       Full API reference
  developer-guide.md     Developer integration guide
  ops-runbook.md         Operations and incident runbook
  SYSTEM_REFERENCE.md    Deep architecture reference
```

---

## Configuration

Runtime configuration is supplied to each Container App from **Azure Key Vault** via native ACA secret references, resolved by the app's managed identity. Services fail fast on startup if a required value is missing — there are no local defaults.

| Variable | Source | Description |
|---|---|---|
| `DATABASE_URL` | KV `postgres-url` | PostgreSQL connection string (asyncpg) |
| `REDIS_URL` | KV `redis-url` | Cache + rate-limit store |
| `LITELLM_MASTER_KEY` | KV `litellm-master-key` | Shared secret between services |
| `SECRET_KEY` | KV | Session signing key |
| `OIDC_ISSUER` / `OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET` | KV | Entra ID SSO settings |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | KV `app-insights-conn` | Telemetry |
| `SERVICE_BUS_CONNECTION` | KV `service-bus-conn` | Observability event bus |
| `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` / `GITHUB_MODELS_API_KEY` | KV | Provider keys |
| `ALLOWED_EMAIL_DOMAINS` | env | Comma-separated list; restricts self-registration |

Secrets are written to Key Vault by the `keyVault` Bicep module and never appear in IaC output or CI logs. See the deployment design for the full secret inventory.

---

## Database Migrations

Migrations are managed by Alembic and applied by the `job-db-migrate-dev-sdc` Container Apps Job, triggered as part of `deploy.yml` after each deploy.

| Migration | Description |
|---|---|
| 0001–0007 | Core schema: teams, API keys, policies, cost records, sessions, guardrails |
| 0008 | `must_change_password` on developer accounts |
| 0009 | Agentic session classification, achievements, leaderboard opt-in |
| 0010 | Unified identity: `users` + `user_roles` tables; migrates `admin_users` + `developers` |
| 0011 | `user_invitations` + `service_accounts` tables |

To run manually against the deployed environment:

```bash
az containerapp job start --name job-db-migrate-dev-sdc --resource-group rg-aigw-dev-sdc
```
