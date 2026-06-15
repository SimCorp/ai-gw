# AI Gateway — SimCorp Developer Platform

Enterprise AI gateway for ~2000 engineers. FastAPI services deployed as Docker Compose on a VM in the SimCorp Landing Zone (Sweden Central).

## Deploying

The gateway runs as Docker Compose on `vm-aigw-dev-sdc` in the PlatformAITooling Dev spoke VNet
(Sweden Central), reachable from the SimCorp VPN at `http://aigw-dev.lab.cloud.scdom.net:8080`.

CI (`.github/workflows/deploy.yml`) deploys automatically on every `master` push via a
self-hosted GitHub Actions runner (`vnet-aigw-dev` label) registered on the VM:

```bash
# On the VM — CI does this automatically
IMAGE_TAG=sha-<git-sha> docker compose -f infra/docker-compose.yml pull
IMAGE_TAG=sha-<git-sha> docker compose -f infra/docker-compose.yml up -d
docker compose -f infra/docker-compose.yml run --rm db-migrate
```

**First-time VM setup:** Run `infra/vm/bootstrap.sh` on the VM, then fill in `/opt/aigw/.env`
with real API keys, then register the GitHub Actions runner (see instructions in
`infra/vm/bootstrap.sh`).

**Local dev:** `./gw up` starts all services via the same compose stack.

## Services

| Service | Port | Purpose |
|---|---|---|
| admin-portal | 3001 | Admin Next.js app |
| portal | 3002 | Developer Next.js app |
| auth | 8001 | JWT / API key validation, rate limiting; inference entry point |
| cache | 8002 | Semantic + exact cache proxy |
| litellm | 8003 | Provider routing (OpenAI-compatible) |
| observability | 8004 | Async event ingestion |
| admin | 8005 | Team management, API keys, dashboards |
| identity | 8006 | Agent registry — DNS-style resolve, heartbeat TTL |
| agent-relay | 8007 | WebSocket relay bus for agentic workflows |
| librarian | 8008 | Knowledge ingestion, chunking, semantic search |
| memory | 8009 | Persistent agent memory scoped to user/team |
| league | 8010 | AI-League gamified challenge platform |
| scanner | — | Security scanning worker (background) |
| workflow-worker | — | Agentic workflow runner (background) |

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
