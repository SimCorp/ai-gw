# AI Gateway — SimCorp Developer Platform

Enterprise AI gateway for ~2000 engineers. FastAPI services running on a single Linux VM via
Docker Compose. Azure Container Apps (ACA) Bicep IaC is in-repo and ready for V2/prod
promotion — CI/CD workflows for ACA are archived in `.github/workflows/_archived/`.

## Current deployment (single-host VM)

| | Value |
|---|---|
| **Host** | `vm-aigw-dev-sdc` — `10.179.231.68` (Sweden Central) |
| **Access** | `dev.aigw.scdom.net` via ZPA (corp VPN) — HTTPS 443, SSH 22 |
| **SSH** | `ssh-aigw` helper (pass key `ssh/dev.aigw.scdom.net`) — see `~/.bashrc` on AZWESU0005 |
| **Compose files** | `/home/azureuser/ai-gw/infra/docker-compose.yml` + `docker-compose.host.yml` on the VM |
| **Deploy** | `git push` to `master` → CI builds + pushes images to GHCR → pull on VM. Routine single-service update: `scripts/update-service.sh <svc>` (static base untouched); full: `scripts/deploy-vm.sh`. Host is intentionally manual, not IaC — see ops-runbook "Host stand-up". |

## Services (Docker Compose)

Services discover each other by container name. The `auth` service fronts the inference
request path and is exposed via Caddy on port 443.

| Service | Port | Purpose |
|---|---|---|
| caddy | 80/443 | TLS termination, reverse proxy |
| admin-portal | 3001 | Admin Next.js app |
| portal | 3002 | Developer Next.js app |
| auth | 8001 | JWT / API key validation, rate limiting; called internally by cache |
| cache | 8002 | Semantic + exact cache proxy; inference entry point after Caddy |
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

Request path: `caller → Caddy:443 → cache(8002) → [cache calls auth(8001) to validate token] → litellm(8003) → provider`

Compose command (always use both files): `docker compose -f docker-compose.yml -f docker-compose.host.yml`

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

## Linting

```bash
ruff check services/
ruff format services/
```

## Architecture

See `docs/superpowers/specs/2026-05-05-ai-gateway-design.md` for the service design and
`docs/superpowers/specs/2026-06-08-azure-enterprise-deployment-design.md` for the Azure
deployment design.

## ACA / V2 (archived)

Full Azure Container Apps IaC lives in `infra/bicep/`. CI/CD workflows are archived in
`.github/workflows/_archived/` and do not run. The ACA setup targets:

| Environment | Gateway FQDN | Trigger | Resource group |
|---|---|---|---|
| **dev** | `aigw-dev.lab.cloud.scdom.net` | `master` push | `rg-aigw-dev-sdc` |
| **test** | `aigw-test.lab.cloud.scdom.net` | `git tag v*` | `rg-aigw-test-sdc` |

See `docs/architecture/environments.md` for the full ACA environment guide.
