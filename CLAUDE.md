# AI Gateway — SimCorp Developer Platform

Enterprise AI gateway for ~2000 engineers. FastAPI services sharing managed Azure PaaS (Cache for Redis + Database for PostgreSQL), deployed to **Azure Container Apps** in the SimCorp Landing Zone (Sweden Central). There is no local stack.

## Deploying

```bash
az deployment group create \
  --resource-group rg-aigw-dev-sdc \
  --template-file infra/bicep/environments/dev/main.bicep \
  --parameters infra/bicep/environments/dev/main.bicepparam \
  --parameters imageTag=sha-<git-sha>
```

CI builds and pushes service images; `deploy.yml` deploys them on a `master` push.

## Services

Each service is a Container App named `ca-<service>-dev-sdc` with **internal** ingress
(the ACA environment is `internal: true` — VNet-only, reached over corp VPN). Services
discover each other via the environment's internal DNS (`http://ca-<service>-dev-sdc`).
The `auth` app fronts the inference request path and is exposed on the gateway FQDN
`https://aigw-dev.lab.cloud.scdom.net`.

| Service | Container App | Internal port | Purpose |
|---|---|---|---|
| admin-portal | `ca-admin-portal-dev-sdc` | 3001 | Admin Next.js app |
| portal | `ca-portal-dev-sdc` | 3002 | Developer Next.js app |
| auth | `ca-auth-dev-sdc` | 8001 | JWT / API key validation, rate limiting; inference entry point |
| cache | `ca-cache-dev-sdc` | 8002 | Semantic + exact cache proxy |
| litellm | `ca-litellm-dev-sdc` | 8003 | Provider routing (OpenAI-compatible) |
| observability | `ca-observability-dev-sdc` | 8004 | Async event ingestion |
| admin | `ca-admin-dev-sdc` | 8005 | Team management, API keys, dashboards |
| identity | `ca-identity-dev-sdc` | 8006 | Agent registry — DNS-style resolve, heartbeat TTL |
| agent-relay | `ca-agent-relay-dev-sdc` | 8007 | WebSocket relay bus for agentic workflows |
| librarian | `ca-librarian-dev-sdc` | 8008 | Knowledge ingestion, chunking, semantic search |
| memory | `ca-memory-dev-sdc` | 8009 | Persistent agent memory scoped to user/team |
| league | `ca-league-dev-sdc` | 8010 | AI-League gamified challenge platform |
| scanner | `ca-scanner-dev-sdc` | — | Security scanning worker (background) |
| workflow-worker | `ca-workflow-worker-dev-sdc` | — | Agentic workflow runner (background) |

Managed PaaS (PostgreSQL, Redis, Key Vault, Service Bus) is reached over private
endpoints; connection strings are injected from Key Vault via each app's managed identity.

## Running tests

Fast unit/integration tests run locally. The raw-SQL suites (e.g. `identity`, `admin`)
use `testcontainers[postgres]` and need a running Docker daemon.

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

End-to-end smoke tests run against the deployed Azure environment (see `deploy.yml`).

## Linting

```bash
ruff check services/
ruff format services/
```

## Architecture

See `docs/superpowers/specs/2026-05-05-ai-gateway-design.md` for the service design and
`docs/superpowers/specs/2026-06-08-azure-enterprise-deployment-design.md` for the Azure
deployment design.

Request path: `caller → auth(8001) → cache(8002) → litellm(8003) → provider`

The admin portal (`ca-admin-dev-sdc`, 8005) is a standalone web app sharing the same
PostgreSQL Flexible Server.
