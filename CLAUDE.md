# AI Gateway — SimCorp Developer Platform

Enterprise AI gateway for ~2000 engineers. FastAPI services running on a single Linux VM via
Docker Compose. Azure Container Apps (ACA) Bicep IaC is in-repo and ready for V2/prod
promotion — CI/CD workflows for ACA are archived in `.github/workflows/_archived/`.

## Current deployment (single-host VM)

| | Value |
|---|---|
| **Host** | `vm-aigw-dev-sdc` — `10.179.231.68` (Sweden Central). RG `RG-SPOKE-PLATFORMAITOOLING-DEV-SDC-001`, NSG `nsg-aigw-vm-dev`, subnet `snet-pe-aigw-dev`, no public IP. (Note: `rg-aigw-dev-sdc` in the ACA/V2 tables below is a *different*, archived RG.) |
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
| graphify | 8012 | Knowledge-graph service — registers repos, builds queryable code graphs, MCP query tools |
| scanner | — | Security scanning worker (background) |
| workflow-worker | — | Agentic workflow runner (background) |
| graphify-worker | — | Graphify build runner (clone + `graphify extract`); isolated so heavy builds can't OOM the query API |

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
  -e "services/agent-relay[dev]" \
  -e "services/graphify[dev]"

pytest services/ -v
```

CI runs the suites per-service (`pytest tests/` inside each `services/<svc>`), which is
also the reliable way to run them locally — a combined `pytest services/` run can collide
on the shared top-level `app` package across services.

## Linting

```bash
ruff check services/
ruff format services/
```

## Observability — use this FIRST when troubleshooting the running stack

A single-host observability layer runs alongside the gateway. When diagnosing a
problem (a service down/erroring, slow, crashing, OOMing), **query it before
guessing** — it has the logs and metrics that `docker ps`/`/health` alone don't.

- **Logs (Loki / LogQL)** and **metrics (Prometheus / PromQL)** for every container.
  From the VM (via `ssh-aigw`), both are on localhost:
  ```bash
  # recent error logs for one service
  curl -s 'http://localhost:3100/loki/api/v1/query_range' \
    --data-urlencode 'query={compose_service="cache"} |= "error"' --data-urlencode 'limit=50'
  # container memory / cpu / restarts (cAdvisor)
  curl -s 'http://localhost:9090/api/v1/query?query=container_memory_usage_bytes{name="ai-gateway-cache-1"}'
  ```
  Logs are structured JSON (`service`, `level`, `request_id`, `session_trace_id`) — grep
  by `request_id` to follow one request across services.
- **Grafana** (humans): `https://dev.aigw.scdom.net/grafana/` (login from `pass aigw/grafana-admin`).
- **In-product DevOps agent**: `POST /api/admin/system`… `/devops-agent/chat` (X-Admin-Token) —
  has `query_logs`, `query_metrics`, `get_container_state` tools that hit Loki/Prometheus.
- **MCP**: `obs-grafana-mcp` (SSE :8013) exposes Grafana query tools to MCP-aware agents
  (see `.vscode/mcp.json`).
- Stack containers: `obs-loki`, `obs-prometheus`, `obs-grafana`, `obs-alloy` (collector,
  tails all container logs + cAdvisor/host metrics), `obs-grafana-mcp`. Config under
  `infra/observability/`. `/metrics` is internal-only (Caddy 404s `/api/<svc>/metrics`).

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
