# AI Gateway — Operations Runbook

**Audience:** Platform engineers and on-call responders  
**System:** Enterprise AI gateway serving ~2,000 SimCorp engineers  
**Last updated:** 2026-06-19

> **Current deployment: single-host VM** — `vm-aigw-dev-sdc` at `10.179.231.68`, reached via `dev.aigw.scdom.net` (ZPA). The ACA sections below are archived reference for the V2/prod promotion path.

---

## Single-host VM operations (current)

### Quick reference

| | |
|---|---|
| Host | `vm-aigw-dev-sdc` · `10.179.231.68` |
| SSH | `ssh-aigw` helper on AZWESU0005 (pass key `ssh/dev.aigw.scdom.net`) |
| Compose dir | `/home/azureuser/ai-gw/infra/` |
| Compose command | `docker compose -f docker-compose.yml -f docker-compose.host.yml` |
| Admin portal | `https://dev.aigw.scdom.net/admin/` |
| Dev portal | `https://dev.aigw.scdom.net/portal/` |
| Inference | `https://dev.aigw.scdom.net/v1/` |

### Check service health

```bash
ssh-aigw
cd ~/ai-gw/infra
docker compose -f docker-compose.yml -f docker-compose.host.yml ps
```

All 18 containers should show `(healthy)`. The two background workers (`workflow-worker`, `scanner`) show `Up` without a healthcheck.

### Restart a service

```bash
cd ~/ai-gw/infra
docker compose -f docker-compose.yml -f docker-compose.host.yml up -d --no-deps <service>
# e.g.: caddy, auth, cache, litellm, admin, portal, admin-portal
```

### View logs

```bash
docker logs ai-gateway-<service>-1 --tail 100 -f
# e.g.: ai-gateway-auth-1, ai-gateway-cache-1, ai-gateway-litellm-1
```

### Deploy a code change

CI builds and pushes all images (incl. the portals, baked with the `dev.aigw.scdom.net`
URL) to GHCR on every `master` push. The VM overlay (`docker-compose.host.yml`) carries
`image:` keys pointing at those GHCR images, so deploying is a pull + restart.

**Preferred — from an in-VNet host (e.g. AZWESU0005):**

```bash
scripts/deploy-vm.sh            # deploy :latest
scripts/deploy-vm.sh sha-abc123 # pin a specific build (rollback / controlled deploy)
```

The script pulls the SSH key and a GHCR read token from `pass`, logs the VM into GHCR,
then runs the pull + restart below. See the script header for env overrides.

**Routine gateway update (one or a few services) — the light path:**

Most changes touch a single gateway service. Update just that service and leave the **static
base** (postgres, redis, dex, caddy) untouched:

```bash
scripts/update-service.sh auth cache          # pull + `up -d --no-deps` for these only
scripts/update-service.sh --tag sha-abc123 admin
```

Use `deploy-vm.sh` (full pull + `up -d`) only for multi-service, base, or compose-file changes —
and even then `up -d` is **convergent**: it recreates only containers whose image/config changed,
so unchanged base containers keep running. The base is effectively static; it is updated only by a
deliberate base/compose change, never as a side effect of a gateway update.

**Manual equivalent — on the VM:**

```bash
cd ~/ai-gw/infra
docker login ghcr.io                 # one-time; GHCR images are private
git pull origin master               # pull source (config files, compose)
docker compose -f docker-compose.yml -f docker-compose.host.yml pull   # pull new images
docker compose -f docker-compose.yml -f docker-compose.host.yml up -d   # rolling restart
# Pin a tag for rollback: prefix both commands with IMAGE_TAG=sha-<sha>
```

> **Portal rebuilds:** Portal `NEXT_PUBLIC_*` URLs are baked correctly by CI, so a URL
> change no longer needs a local rebuild — just redeploy. Only rebuild locally if you are
> testing an uncommitted `Dockerfile.portal` / `Dockerfile.admin` change before it lands:
> ```bash
> docker compose -f docker-compose.yml -f docker-compose.host.yml build portal admin-portal
> docker compose -f docker-compose.yml -f docker-compose.host.yml up -d --no-deps portal admin-portal
> ```

### Secrets and `.env`

All provider API keys live in `/home/azureuser/ai-gw/.env` (gitignored, mode 0600). To update a key, pipe it from `pass` on AZWESU0005 via SSH — never write secrets to disk in plaintext. See `docs/architecture/dev-environment.md` for the exact pattern.

The live `.env` carries ~49 keys. The full set is whatever `infra/docker-compose.yml` references; the
keys that **must** be present (no safe default) are the provider keys + control-plane secrets:

| Group | Keys |
|---|---|
| Providers | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`/`AZURE_API_KEY`+`AZURE_API_BASE`+`AZURE_API_VERSION`, `GEMINI_API_KEY`, `GITHUB_MODELS_API_KEY`, `GITHUB_COPILOT_TOKEN`, `AZURE_AI_FOUNDRY_ENDPOINT`/`_KEY`, `EMBEDDING_API_KEY`/`_BASE_URL`/`_MODEL` |
| Gateway / admin | `LITELLM_MASTER_KEY`, `ADMIN_TOKEN`, `SECRET_KEY`, `IDENTITY_KEY_SECRET`, `RELAY_SECRET` |
| Auth / OIDC | `JWKS_URI`, `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `OIDC_ISSUER`/`OIDC_CLIENT_ID`/`OIDC_CLIENT_SECRET` |
| Infra | `DATABASE_URL`, `REDIS_URL`, `POSTGRES_DB`/`_USER`/`_PASSWORD`, `BUS_PROVIDER` |
| Optional | `SMTP_*` (email), `WORKDAY_*` (org sync), `DEV_BYPASS_AUTH` |

> The service-to-service secrets `AGENT_RELAY_SECRET`, `IDENTITY_SERVICE_TOKEN`,
> `LIBRARIAN_SERVICE_TOKEN`, `SCANNER_WORKER_SECRET`, `INTERNAL_API_KEY`, `ADMIN_INTERNAL_TOKEN`
> fall back to the non-empty dev defaults baked into `docker-compose.yml` (`${VAR:-…}`); set real
> values for any hardening. (See §0.)

### Host stand-up (manual, reproducible)

The VM **host is intentionally not infrastructure-as-code** — for a single dev box, full
Terraform/Bicep-VM would be over-engineering. Provisioning is a manual, reproducible checklist
(VM creation is also classifier-blocked for agents). To rebuild the host from scratch:

1. **VM + NSG (user):** `az vm create` an Ubuntu VM with a static private IP; NSG inbound `443`+`80`
   from the ZPA connector range and `22` from ZPA/mgmt.
2. **IT requests (user):** ① cert `*.aigw.scdom.net` (SimCorp Issuing CA); ② DNS A record
   `dev.aigw.scdom.net` → the VM IP (internal zone); ③ ZPA route + TLS passthrough on 443/80/22.
3. **Docker:** install Docker Engine + the compose plugin.
4. **Repo:** clone to `~/ai-gw` and check out `master`.
5. **Cert:** install `infra/certs/cert.pem` + `key.pem` from the `pass` PFX entry (see
   `docs/architecture/dev-environment.md` for the exact pipe-from-pass commands).
6. **`.env`:** seed `~/ai-gw/.env` (mode 0600) from `pass` — the keys in the table above.
7. **GHCR + bring up:** `docker login ghcr.io` (read-only PAT from `pass api/GHCR PAT aigw`),
   then `scripts/deploy-vm.sh` from an in-VNet host (or `docker compose … pull && up -d` on the VM).

The repo is the source of truth for the compose stack, Caddyfile, dex config, and the deploy model;
the only host-local, gitignored state is `.env` + `infra/certs/` (both sourced from `pass`).

### TLS certificate

Wildcard cert `*.aigw.scdom.net` (SimCorp Issuing CA, valid until 2028). Stored in `pass` as `certificate/wildcard.aigw.scdom.net.pfx.b64`. Installed at `~/ai-gw/infra/certs/cert.pem` + `key.pem` on the VM. See `docs/architecture/dev-environment.md` for the reinstall procedure.

### Common failure modes (single-host)

| Symptom | Likely cause | Fix |
|---|---|---|
| `x-cache: MISS` on every call | Inference is working but not hitting cache | Check Redis: `docker exec ai-gateway-redis-1 redis-cli ping` |
| 401 "Invalid or revoked API key" | sk-* key doesn't exist or was revoked | Verify key hash in DB: `docker exec ai-gateway-postgres-1 psql -U aigateway -d aigateway -c "SELECT name, revoked_at FROM api_keys WHERE key_hash = '$HASH';"` |
| 503 from inference path | litellm unavailable or provider key missing | Check litellm logs; verify `ANTHROPIC_API_KEY` etc. in `.env` |
| Portal "Failed to fetch" on login | Portal built with wrong API URL baked in | Rebuild portal images with correct `--build-arg NEXT_PUBLIC_*` |
| Admin portal stays at `/login` after submit | Admin service unreachable at `/admin/*` | Check caddy is running; check `docker logs ai-gateway-admin-1 --tail 20` |
| `can_access` returns False for platform_admin | Stale code pre-`17e3ab6` — root node UUID path | Pull latest and rebuild admin container |

---

## ACA reference (archived — V2/prod path)

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Deploy, Rollback, and Revisions](#2-deploy-rollback-and-revisions)
3. [Health Monitoring](#3-health-monitoring)
4. [Common Failure Modes](#4-common-failure-modes)
5. [Database Maintenance](#5-database-maintenance)
6. [Adding a New AI Provider](#6-adding-a-new-ai-provider)
7. [Managing Teams and Rate Limits](#7-managing-teams-and-rate-limits)
8. [Log Locations and What to Look For](#8-log-locations-and-what-to-look-for)
9. [Configuration and Secrets Reference](#9-configuration-and-secrets-reference)

---

## 0. Security Configuration

The following secrets must be present for each service. They have no insecure defaults — omitting them disables the corresponding protection or causes the service to refuse to start. In ACA they are stored in **Azure Key Vault** and injected into each Container App as secrets via the app's **managed identity** (see `infra/bicep`).

| Variable | Service(s) | Purpose |
|----------|------------|---------|
| `AGENT_RELAY_SECRET` | `agent-relay`, `workflow-worker` | Shared secret for relay-to-worker authentication. The relay validates this on `POST /register`; the worker sends it as `X-Relay-Secret` on `POST /invoke`. Without this, any process that can reach the relay can register as an agent. |
| `ADMIN_INTERNAL_TOKEN` | `workflow-worker`, `admin` | Bearer token the worker uses for internal calls to the admin service (e.g. sub-workflow spawns via `POST /runs`). The admin service checks `X-Internal-Token`. Without this, any internal service can trigger workflow runs. |
| `IDENTITY_KEY_SECRET` | `identity` | Encryption key for the DID signing key stored in Redis (`identity:signing_key`). Without this, the signing key is stored in plaintext and can be exfiltrated by anyone with Redis access. |
| `IDENTITY_SERVICE_TOKEN` | `identity` | Bearer token that gates the `POST /agents/register` endpoint. Without this, any process on the internal network can register arbitrary agent identities. |
| `LIBRARIAN_SERVICE_TOKEN` | `librarian` | Bearer token that gates the `POST /ingest` and `POST /research/topics` endpoints. Without this, any process on the internal network can inject arbitrary documents into the knowledge base. |

### Rotating secrets

Each value is treated as a credential and lives in Azure Key Vault. To rotate one, update the secret version in Key Vault; the Container App picks up the new value on its next revision. Trigger a new revision by redeploying (see §2). Never store these values in source control or pass them as plaintext deployment parameters.

---

## 1. Architecture Overview

### Deployment topology

All services run as **Azure Container Apps** named `ca-<service>-dev-sdc` in the ACA environment `cae-aigw-dev-sdc` (resource group `rg-aigw-dev-sdc`, Sweden Central). The environment is `internal: true` — VNet-only, reachable from the corporate VPN, not the public internet. It has a static internal IP `10.179.231.6` and an env default domain such as `calmbush-e5f546e4.swedencentral.azurecontainerapps.io`. The developer-facing gateway entry point is **https://aigw-dev.lab.cloud.scdom.net**.

Services reach each other over ACA internal DNS at `http://ca-<service>-dev-sdc`.

### Service Map

```
Caller (developer tool / IDE extension)  →  https://aigw-dev.lab.cloud.scdom.net
    |
    v
auth  (ca-auth-dev-sdc:8001)  — JWT / API key validation, per-team rate limiting (Redis fixed-window)
    |
    v
cache (ca-cache-dev-sdc:8002)  — Semantic + exact cache (Redis), embedding via the gateway (litellm)
    |
    v
litellm (ca-litellm-dev-sdc:8003) — Provider routing, OpenAI-compatible API (Anthropic / OpenAI / Google / GitHub Models)
    |
    v
Provider APIs  (anthropic.com, api.openai.com, generativelanguage.googleapis.com, …)

observability (ca-observability-dev-sdc:8004)  — Async event ingestion, writes cost_records + audit_log to Postgres
admin         (ca-admin-dev-sdc:8005)          — Team management, API keys, provider key config, system health dashboard
```

Background workers run as Container Apps with **no ingress**: `ca-scanner-dev-sdc` (security scanning) and `ca-workflow-worker-dev-sdc`. Portals run as `ca-admin-portal-dev-sdc:3001` and `ca-portal-dev-sdc:3002`.

### Shared Infrastructure (Azure PaaS)

All PaaS services are reached over **private endpoints** in `snet-pe-aigw-dev`. Their secrets/connection strings are stored in Azure Key Vault and injected into each Container App via its managed identity.

| Component | Azure resource | Role |
|-----------|----------------|------|
| PostgreSQL | Azure Database for PostgreSQL Flexible Server (databases `aigateway` + `litellm`) | Teams, API keys, policies, cost records, audit log, developers; LiteLLM state |
| Redis | Azure Cache for Redis Premium P1 | Rate limit counters, semantic cache, admin portal sessions |
| Secrets | Azure Key Vault | All service secrets and connection strings |
| Event bus | Azure Service Bus (queue `observability-events`) | Async observability event delivery |
| Telemetry | Application Insights + Log Analytics workspace `law-aca-dev-sdc` | Metrics, traces, container logs |

### Key Data Flows

- **Authentication:** caller sends `Authorization: Bearer sk-<key>`. Auth service hashes the key, looks it up in `api_keys`, loads the team's policy from `policies`, checks the Redis rate limit counter at `ratelimit:{team_id}:{model}`, then forwards with `X-Litellm-Master-Key` injected.
- **Caching:** cache service computes a semantic embedding of the request and checks Redis for a similar past response. Hits skip litellm entirely. Misses are forwarded and the response is stored.
- **Observability:** after each completion, a structured event is posted to `:8004/events`. The service writes a `cost_records` row, updates (or creates) a `sessions` row keyed on `session_trace_id`, and for notable events writes an `audit_log` row. Streaming responses include token counts extracted from the final SSE chunk, so cost_records entries are accurate for both streaming and non-streaming requests.
- **Session tracking:** the `sessions` table aggregates per-session signals (model used, repos, intent classifications, quality score 1–5) for the developer productivity reports. Sessions are keyed by the `X-Session-Trace-Id` request header; requests without this header are bucketed under an anonymous session for that API key.
- **Budget alert loop:** the admin service runs a background task that periodically checks each team's MTD spend against its budget threshold. When a threshold is crossed, an HTTP POST is fired to the team's configured Slack-compatible webhook URL (stored in `org_notifications`). A Redis dedup key (`budget_alert:{team_id}:{window}`) prevents duplicate notifications within the same alert window.
- **GitHub webhook background task:** `POST /webhooks/github` is handled by a background task that correlates GitHub push and PR events with developer sessions by matching commit authors to developer records. Requires the `GITHUB_WEBHOOK_SECRET` env var for HMAC signature validation.
- **Provider keys:** stored in the `provider_keys` table. On save, the admin portal calls `PATCH /model/update` on LiteLLM to inject the key at runtime — no restart required.

---

## 2. Deploy, Rollback, and Revisions

Deployments are driven by Bicep against the dev resource group. Each deploy builds an immutable
revision per Container App; rollback is a redeploy of a previous image tag. Run these commands from
a VNet-connected host (corp VPN) authenticated to the SimCorp Landing Zone.

### Deploy

```bash
az deployment group create \
  --resource-group rg-aigw-dev-sdc \
  --template-file infra/bicep/environments/dev/main.bicep \
  --parameters infra/bicep/environments/dev/main.bicepparam \
  --parameters imageTag=sha-<git-sha>
```

`imageTag` is the short git SHA of the built images. CI (`deploy.yml`) normally runs this on merge;
the manual form above is for ad-hoc or recovery deploys.

### Run database migrations

Migrations run as an ACA job, not inline in a service. Trigger it explicitly:

```bash
az containerapp job start \
  --name job-db-migrate-dev-sdc \
  --resource-group rg-aigw-dev-sdc
```

The job applies all Alembic migrations (0001 → latest). Migrations 0025–0030 are safe for fresh
databases — conditional checks (e.g. renaming columns that may not exist) guard against errors on a
clean database.

### Inspect revisions

```bash
az containerapp revision list -n ca-<service>-dev-sdc -g rg-aigw-dev-sdc
```

Each ACA revision is atomic: it is created with a specific image tag and either becomes active or
not. There is no partial/in-place mutation of a running revision.

### Rollback

Redeploy with the previous `imageTag`:

```bash
az deployment group create \
  --resource-group rg-aigw-dev-sdc \
  --template-file infra/bicep/environments/dev/main.bicep \
  --parameters infra/bicep/environments/dev/main.bicepparam \
  --parameters imageTag=sha-<previous-git-sha>
```

Because revisions are atomic per revision, this cleanly reverts the affected apps to the prior
image. Confirm with `az containerapp revision list` that the expected revision is active.

### Inspect the environment

```bash
az containerapp env show -n cae-aigw-dev-sdc -g rg-aigw-dev-sdc
```

### First login (admin portal)

The default admin account is seeded automatically on first boot when `ENVIRONMENT=development`:

| Field | Value |
|-------|-------|
| URL | https://aigw-dev.lab.cloud.scdom.net/admin/ |
| Email | `admin@simcorp.com` |
| Password | set by the `_default_hash` in `services/admin/app/main.py` |

The plaintext password is not stored in the repo. If you don't know it (e.g. on a freshly
provisioned environment), reset it directly against the Flexible Server from a VNet-connected host:

```bash
python3 - <<'EOF'
import bcrypt, subprocess
NEW_PASSWORD = "SimCorp1!"   # change to whatever you want
h = bcrypt.hashpw(NEW_PASSWORD.encode(), bcrypt.gensalt(12)).decode()
sql = f"UPDATE users SET password_hash = '{h}', must_change_password = false WHERE email = 'admin@simcorp.com';"
subprocess.run(["psql", "-h", "<flexible-server-fqdn>", "-U", "aigateway", "-d", "aigateway", "-c", sql])
print(f"Password reset to: {NEW_PASSWORD}")
EOF
```

### Seed the SimCorp org structure

On a freshly provisioned environment the areas/units/teams tables are empty. Populate the real org
hierarchy:

```bash
# 1. Log in at https://aigw-dev.lab.cloud.scdom.net/admin/, then in the browser console:
#    sessionStorage.getItem('admin_session_token')
# 2. Copy the token and run (from a VNet-connected host):
ADMIN_TOKEN=<token> python3 scripts/seed_simcorp_org.py
```

The script is idempotent — safe to run again if partially applied.

### Restart a single service

A Container App is restarted by creating a fresh revision — redeploy that app's image tag (see
Deploy). Confirm the new revision is active with `az containerapp revision list`.

---

## 3. Health Monitoring

### System Health Dashboard

The admin portal exposes a built-in health dashboard (reachable over the corp VPN via the gateway FQDN):

| URL | Format | Notes |
|-----|--------|-------|
| `https://aigw-dev.lab.cloud.scdom.net/admin/dashboard` | HTML | Auto-refreshes every 10 seconds |
| `https://aigw-dev.lab.cloud.scdom.net/api/admin/system/health` | JSON | Suitable for external monitoring/alerting |

**Visual dashboard:** The JSON endpoint is also rendered as a rich visual dashboard at the admin-portal dashboard URL above. It polls every 10 seconds and shows: service status dots with latency bars, Redis memory, Postgres active connections, LiteLLM model count, gateway requests/minute, cache hit rate, and recent error events.

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

Each service exposes `/health`, `/ready`, and `/liveliness`. These are reachable internally
(`http://ca-<service>-dev-sdc/...`) and via the gateway FQDN over the corp VPN. ACA also uses these
as the apps' configured liveness/readiness probes.

```
GET http://ca-auth-dev-sdc/health           — auth
GET http://ca-cache-dev-sdc/health           — cache
GET http://ca-litellm-dev-sdc/health/liveliness — litellm
GET http://ca-observability-dev-sdc/health   — observability
GET http://ca-admin-dev-sdc/health           — admin
```

### Redis Health Check

From a VNet-connected host, against the Azure Cache for Redis Premium endpoint:

```bash
redis-cli -h <redis-premium-host> --tls ping
# Expected: PONG

redis-cli -h <redis-premium-host> --tls info memory | grep used_memory_human
redis-cli -h <redis-premium-host> --tls info clients | grep connected_clients
```

### PostgreSQL Health Check

From a VNet-connected host, against the Flexible Server:

```bash
psql -h <flexible-server-fqdn> -U aigateway -d aigateway \
  -c "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';"
```

### Key Metrics to Watch

Metrics and traces are in Application Insights; the gateway dashboard surfaces the same signals.

| Metric | Where | Alert threshold (suggested) |
|--------|-------|-----------------------------|
| Service status != ok | `/system/health` | Any service unreachable |
| Redis used_memory_mb | `/system/health` > redis | > 80% of `maxmemory` setting |
| Postgres active_connections | `/system/health` > postgres | > 80 (default max is 100) |
| requests_last_60s | `/system/health` > gateway | Sudden drop to 0 during business hours |
| cache_hit_rate_last_60s | `/system/health` > gateway | Sustained drop below 0.20 |
| models_available | `/system/health` > litellm | 0 models available |

### Configured Alerts

These fire from `infra/bicep/.../monitoring.bicep` and post to a Microsoft Teams webhook:

| Alert | Condition |
|-------|-----------|
| Gateway latency | p99 > 500ms over 5 min |
| Error rate | > 5% over 5 min |
| Redis evictions | Eviction events on the Redis cache |
| PostgreSQL CPU | > 80% over 5 min |
| Container App restarts | > 3 restarts over 5 min |

---

## 3a. Tests

**Fast tests (local, no deployed environment):**

```bash
pytest services/ -v
```

The `identity` and `admin` suites use `testcontainers[postgres]` and need a running Docker daemon
on the developer's machine; the rest run without it.

**End-to-end smoke tests** run against the deployed dev environment from a VNet-connected CI runner
as part of `deploy.yml` after a successful deploy. They exercise the gateway FQDN and confirm each
service responds on `/health` and that the auth → cache → litellm path works end-to-end.

### Quality tests (browser E2E walkthrough)

`e2e/` is a standalone Playwright (`@playwright/test`) project that logs into the **dev + admin
portals** and walks every route, asserting **no client-side crashes** (uncaught page errors) and
**no failed backend calls** (HTTP ≥ 400, benign noise filtered). It catches exactly the class of
breakage that unit tests miss — e.g. a page that renders but whose data fetch 401s/CSP-blocks, or an
`x.map is not a function` crash. The full walk is fast (~25s; both portals run in parallel). Set
**`E2E_CLICK=1`** for the thorough pass that also clicks every **non-destructive** button (deny-list
skips delete/revoke/rotate/etc.; native confirms auto-cancel) — slower, off by default.

It targets a **deployed** environment (reachable only in-VNet / over ZPA) and is **NOT a CI merge
gate** — gating PR merges on a live-env test would validate the *old* deployment, not the PR, and
add flake. Run it on demand or as a post-deploy smoke.

```bash
# On-demand, from an in-VNet host (creds pulled from pass; never written to disk):
scripts/e2e-quality.sh                       # walk both portals on dev.aigw.scdom.net (~25s)
scripts/e2e-quality.sh --project dev-portal  # one portal
E2E_CLICK=1 scripts/e2e-quality.sh           # thorough: also click every safe button (slower)
E2E_BASE_URL=https://aigw-test.lab.cloud.scdom.net scripts/e2e-quality.sh

# Post-deploy smoke (deploy, then fail if the walkthrough fails):
SMOKE=1 scripts/deploy-vm.sh

# View the HTML report / traces afterwards:
pnpm --prefix e2e exec playwright show-report
```

**Where results land:** the terminal `list` reporter prints each route live; a rich **HTML
report** (with a screenshot + trace for any failure) is written to `e2e/playwright-report/`; and a
**machine-readable `e2e/results.json`** (for dashboards/alerts) is emitted. In CI both are uploaded
as the `playwright-report` artifact.

**Known-benign signals** (allow-listed in `e2e/lib/walk.ts`, not failures): the Radix
`DialogContent requires a DialogTitle` a11y advisory; the `403 …/developers/{id}/teams` for a test
account with no team. **Automation:** `.github/workflows/e2e-quality.yml` runs it on
`workflow_dispatch` + nightly schedule, **non-gating**, on a `vnet-aigw-dev` self-hosted runner —
dormant until that runner exists and the repo variable `E2E_ENABLED=true` is set. A true hermetic
PR gate (spin up the full stack in CI and run Playwright against `localhost`) is a planned
follow-up.

---

## 4. Common Failure Modes

### 4.1 Service Unreachable

**Symptoms:** Health dashboard shows `unreachable` for one or more services. Calls to that service via the gateway return 5xx or time out.

**Diagnosis:**

```bash
# Check the app's revisions and which is active
az containerapp revision list -n ca-auth-dev-sdc -g rg-aigw-dev-sdc

# Stream recent logs for the failing service
az containerapp logs show -n ca-auth-dev-sdc -g rg-aigw-dev-sdc --follow
az containerapp logs show -n ca-cache-dev-sdc -g rg-aigw-dev-sdc --follow
az containerapp logs show -n ca-litellm-dev-sdc -g rg-aigw-dev-sdc --follow
```

For history beyond the live stream, query Log Analytics (`law-aca-dev-sdc`) with KQL over
`ContainerAppConsoleLogs_CL` (application stdout/stderr) and `ContainerAppSystemLogs_CL` (platform
events such as scaling and restarts).

**Common causes and fixes:**

| Cause | Fix |
|-------|-----|
| Revision in crash loop | Check `ContainerAppConsoleLogs_CL` for a Python traceback. Fix the root cause and redeploy; if it was a bad image, roll back to the previous `imageTag` (§2). |
| Dependency not ready (e.g. litellm before migrations) | Confirm the `job-db-migrate-dev-sdc` job completed successfully before app revisions started. |
| Restart storm | `ContainerAppSystemLogs_CL` shows restart events; the ">3 restarts/5min" alert fires to Teams. |
| Bad config / missing secret | A missing Key Vault secret blocks startup — confirm the app's managed identity has access and the secret exists. |

---

### 4.2 Auth Failures (HTTP 401)

**Symptoms:** Callers receive `401 Unauthorized`. Admin portal returns `401 Invalid admin token`.

**Diagnosis:**

- For **gateway callers** (`sk-` keys): the key may be revoked, expired, or the team may not exist.

```sql
-- Check key status in Postgres (psql from a VNet-connected host)
psql -h <flexible-server-fqdn> -U aigateway -d aigateway -c "
    SELECT ak.name, ak.created_at, ak.revoked_at, t.name AS team
    FROM api_keys ak JOIN teams t ON ak.team_id = t.id
    WHERE ak.revoked_at IS NOT NULL
    ORDER BY ak.revoked_at DESC LIMIT 10;"
```

- For **admin portal** (`X-Admin-Token` header): confirm the `ADMIN_TOKEN` secret is set and matches what the client is sending. Inspect the admin app's effective config via its logs (`az containerapp logs show -n ca-admin-dev-sdc -g rg-aigw-dev-sdc`).

**Common causes and fixes:**

| Cause | Fix |
|-------|-----|
| API key revoked | Issue a new key via Admin > Teams > API Keys |
| `ADMIN_TOKEN` not set | Admin will return 500 — set the `ADMIN_TOKEN` secret in Key Vault and redeploy the admin app |
| Entra ID JWT expired | Re-authenticate through the OIDC flow |

---

### 4.3 Rate Limit Hit (HTTP 429)

**Symptoms:** Callers receive `429 Rate limit exceeded` with header `Retry-After: 60`.

**How it works:** Auth uses a fixed 60-second window. The Redis key `ratelimit:{team_id}:{model}` is incremented on each request and expires after 60 seconds. When the count exceeds the team's `rate_limit_rpm` policy, subsequent requests in the window are rejected.

**Diagnosis:**

```bash
# Check current counter for a team+model combination (redis-cli from a VNet-connected host)
redis-cli -h <redis-premium-host> --tls get "ratelimit:<team_id>:<model>"

# See all active rate limit keys
redis-cli -h <redis-premium-host> --tls keys "ratelimit:*"

# Check the team's configured limit (psql from a VNet-connected host)
psql -h <flexible-server-fqdn> -U aigateway -d aigateway -c "
    SELECT t.name, p.rate_limit_rpm
    FROM policies p JOIN teams t ON p.team_id = t.id;"
```

**Fix options:**

1. **Wait:** the window resets automatically after 60 seconds.
2. **Increase limit:** Admin portal > Teams > select team > Policies > raise `rate_limit_rpm`.
3. **Clear the counter manually (emergency only):**

```bash
redis-cli -h <redis-premium-host> --tls del "ratelimit:<team_id>:<model>"
```

---

### 4.4 Provider API Key Missing

**Symptoms:** LiteLLM returns `AuthenticationError` or `APIError`. The system health dashboard shows `models_available: 0` or a low count. The settings page on the admin portal shows a provider as "not configured".

**Diagnosis:**

```bash
# Check what keys are stored in the database (psql from a VNet-connected host)
psql -h <flexible-server-fqdn> -U aigateway -d aigateway -c "
    SELECT env_var, updated_at FROM provider_keys;"

# Check LiteLLM model list (should list configured models), via the gateway over VPN
curl -s -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  https://aigw-dev.lab.cloud.scdom.net/api/litellm/v1/models | python3 -m json.tool
```

**Fix:**

1. Open the admin portal settings page at `https://aigw-dev.lab.cloud.scdom.net/admin/dashboard`.
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

Run redis-cli from a VNet-connected host against the Azure Cache for Redis Premium endpoint:

```bash
# Ping
redis-cli -h <redis-premium-host> --tls ping

# Memory info
redis-cli -h <redis-premium-host> --tls info memory

# Key count and type breakdown
redis-cli -h <redis-premium-host> --tls dbsize
redis-cli -h <redis-premium-host> --tls info keyspace
```

**Redis unreachable — fix:** Azure Cache for Redis is a managed PaaS resource. Check its health in
the Azure portal / Application Insights; raise a platform ticket if the instance itself is degraded.
Services reconnect automatically once it recovers. Rate limit windows will reset (acceptable as a
recovery side-effect).

**Redis memory full — fix options:**

1. **Flush semantic cache only** (safe, cache will rebuild on demand):

```bash
# Semantic cache keys typically follow a pattern — inspect first
redis-cli -h <redis-premium-host> --tls keys "cache:*"
# Then delete matching keys
redis-cli -h <redis-premium-host> --tls --scan --pattern "cache:*" \
  | xargs redis-cli -h <redis-premium-host> --tls del
```

2. **Flush portal sessions** (users will need to re-login):

```bash
redis-cli -h <redis-premium-host> --tls --scan --pattern "portal_session:*" \
  | xargs redis-cli -h <redis-premium-host> --tls del
```

3. **Review the `maxmemory` / eviction policy** on the Premium P1 instance to ensure automatic
   eviction is enabled. The "Redis evictions" alert (§3) fires when eviction events occur.

---

### 4.6 PostgreSQL Connection Exhausted

**Symptoms:** Services log `FATAL: remaining connection slots are reserved`. System health shows `active_connections` near 100 (the PostgreSQL default). New requests fail with 500.

**Diagnosis:**

```bash
psql -h <flexible-server-fqdn> -U aigateway -d aigateway -c "
    SELECT state, count(*) FROM pg_stat_activity
    GROUP BY state ORDER BY count DESC;"

psql -h <flexible-server-fqdn> -U aigateway -d aigateway -c "
    SELECT pid, state, application_name, query_start, query
    FROM pg_stat_activity
    WHERE state != 'idle'
    ORDER BY query_start;"
```

**Fix options:**

1. **Terminate idle connections** (safe):

```bash
psql -h <flexible-server-fqdn> -U aigateway -d aigateway -c "
    SELECT pg_terminate_backend(pid)
    FROM pg_stat_activity
    WHERE state = 'idle'
      AND query_start < NOW() - INTERVAL '10 minutes';"
```

2. **Restart the service with the leak** (redeploy that app, §2) if a specific service is holding too many connections.

3. **Longer term:** add `pool_size` and `max_overflow` settings to each service's SQLAlchemy engine configuration, or front the Flexible Server with PgBouncer.

---

## 5. Database Maintenance

### Tables That Grow Over Time

| Table | Growth driver | Retention strategy |
|-------|--------------|-------------------|
| `cost_records` | One row per AI completion | Archive or delete rows older than 90 days |
| `audit_log` | One row per notable event | Archive or delete rows older than 90 days |
| `sessions` | One row per session_trace_id; updated on each request in the session | Archive or delete rows older than 90 days |
| `api_keys` | Accumulates revoked keys | Safe to delete rows where `revoked_at < NOW() - INTERVAL '1 year'` |
| `developers` | Self-service portal users (email, PBKDF2 password hash, linked team_id) | Retain; remove only on explicit account deletion |

### Check Table Sizes

```sql
SELECT
    relname AS table_name,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
    pg_size_pretty(pg_relation_size(relid)) AS data_size
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC;
```

Run via (psql from a VNet-connected host):

```bash
psql -h <flexible-server-fqdn> -U aigateway -d aigateway -c "<SQL above>"
```

### Prune cost_records (older than 90 days)

```bash
psql -h <flexible-server-fqdn> -U aigateway -d aigateway -c "
    DELETE FROM cost_records
    WHERE created_at < NOW() - INTERVAL '90 days';"
```

### Prune audit_log (older than 90 days)

```bash
psql -h <flexible-server-fqdn> -U aigateway -d aigateway -c "
    DELETE FROM audit_log
    WHERE timestamp < NOW() - INTERVAL '90 days';"
```

### Prune revoked API keys (older than 1 year)

```bash
psql -h <flexible-server-fqdn> -U aigateway -d aigateway -c "
    DELETE FROM api_keys
    WHERE revoked_at IS NOT NULL
      AND revoked_at < NOW() - INTERVAL '1 year';"
```

### Vacuum After Large Deletes

```bash
psql -h <flexible-server-fqdn> -U aigateway -d aigateway \
  -c "VACUUM ANALYZE cost_records; VACUUM ANALYZE audit_log;"
```

### Back Up the Database

Azure Database for PostgreSQL Flexible Server takes automated backups; use point-in-time restore in
the Azure portal for routine recovery. For an ad-hoc logical dump from a VNet-connected host:

```bash
pg_dump -h <flexible-server-fqdn> -U aigateway aigateway | gzip > aigateway-$(date +%Y%m%d).sql.gz
```

---

## 6. Adding a New AI Provider

### Via the Admin UI (preferred)

1. Open the admin portal at `https://aigw-dev.lab.cloud.scdom.net/admin/dashboard`.
2. Navigate to **Settings** (or go directly to the dashboard URL above).
3. Find the provider row (Anthropic, OpenAI, Google, or GitHub Models).
4. Enter the API key in the text field for that provider.
5. Click **Save**. The portal:
   - Stores the key in the `provider_keys` table.
   - Sets the env var in the admin process immediately (`os.environ[env_var] = key`).
   - Calls `PATCH /model/update` on LiteLLM for each model belonging to that provider, injecting the key into LiteLLM's in-memory config. No restart required.
6. Click **Test** on the provider row to fire a 1-token test completion. The response shows pass/fail and latency.

### Verify LiteLLM Received the Key

```bash
curl -s -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  https://aigw-dev.lab.cloud.scdom.net/api/litellm/v1/models | python3 -c "
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
4. Build new images, then redeploy the admin and litellm apps with the new `imageTag` (§2).

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

Or via SQL (emergency revocation, from a VNet-connected host):

```bash
psql -h <flexible-server-fqdn> -U aigateway -d aigateway -c "
    UPDATE api_keys SET revoked_at = NOW()
    WHERE name = '<key name>';"
```

### Adjust Rate Limits

1. Admin portal > **Teams** > select team > **Policies**.
2. Modify `rate_limit_rpm` (requests per minute per model, fixed 60-second window).
3. Save. The change takes effect on the next rate limit window (up to 60 seconds).

Or via SQL (from a VNet-connected host):

```bash
psql -h <flexible-server-fqdn> -U aigateway -d aigateway -c "
    UPDATE policies SET rate_limit_rpm = 2000, updated_at = NOW()
    WHERE team_id = (SELECT id FROM teams WHERE slug = '<team-slug>');"
```

### Restrict a Team to Specific Models

In the `policies` table, `allowed_models` is a `TEXT[]` column. An empty array means all models are allowed.

```bash
psql -h <flexible-server-fqdn> -U aigateway -d aigateway -c "
    UPDATE policies
    SET allowed_models = ARRAY['gpt-4o-mini', 'claude-haiku-4-5'], updated_at = NOW()
    WHERE team_id = (SELECT id FROM teams WHERE slug = '<team-slug>');"
```

### View Cost Data for a Team

```bash
psql -h <flexible-server-fqdn> -U aigateway -d aigateway -c "
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

Stream live logs for a single Container App:

```bash
az containerapp logs show -n ca-auth-dev-sdc -g rg-aigw-dev-sdc --follow
az containerapp logs show -n ca-cache-dev-sdc -g rg-aigw-dev-sdc --follow
az containerapp logs show -n ca-litellm-dev-sdc -g rg-aigw-dev-sdc --follow
az containerapp logs show -n ca-observability-dev-sdc -g rg-aigw-dev-sdc --follow
az containerapp logs show -n ca-admin-dev-sdc -g rg-aigw-dev-sdc --follow
```

For historical search, cross-service correlation, or alerting, query Log Analytics workspace
`law-aca-dev-sdc` with KQL:

- `ContainerAppConsoleLogs_CL` — application stdout/stderr (filter by container app name)
- `ContainerAppSystemLogs_CL` — platform events (scaling, restarts, probe failures)

Metrics and distributed traces are in Application Insights.

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
| `embedding` error | Embedding endpoint (via litellm) unreachable — cache bypassed, still functional |
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
psql -h <flexible-server-fqdn> -U aigateway -d aigateway -c "
    SELECT timestamp, actor, action, resource_type, resource_id
    FROM audit_log
    ORDER BY timestamp DESC
    LIMIT 20;"
```

---

## 9. Configuration and Secrets Reference

Configuration is delivered to each Container App as environment variables and secrets. Secrets and
connection strings are stored in Azure Key Vault and injected via each app's managed identity; the
PaaS endpoints below are reached over private endpoints in `snet-pe-aigw-dev`. The "Value / source"
column describes what each variable points at in the dev environment.

### Infrastructure

| Variable | Value / source | Used by | Description |
|----------|----------------|---------|-------------|
| `DATABASE_URL` | Flexible Server, database `aigateway` (from Key Vault) | auth, observability, admin | SQLAlchemy async connection string (`postgresql+asyncpg://...`). LiteLLM uses a separate `postgresql://` (no `+asyncpg`) form pointing at the `litellm` database. |
| `REDIS_URL` | Azure Cache for Redis Premium P1 (from Key Vault) | auth, cache, admin | Redis connection string (TLS) |

### Auth Service (`ca-auth-dev-sdc`, :8001)

| Variable | Value / source | Description |
|----------|----------------|-------------|
| `REDIS_URL` | Redis Premium (from Key Vault) | Redis for rate limit counters |
| `DATABASE_URL` | see above | Postgres for API key lookup |
| `JWKS_URI` | Entra ID JWKS endpoint | OIDC public key endpoint for JWT validation |
| `ENTRA_TENANT_ID` | SimCorp Entra tenant ID | Azure Entra tenant ID |
| `ENTRA_CLIENT_ID` | app registration client ID | Expected `aud` claim in JWTs |
| `RATE_LIMIT_DEFAULT_RPM` | `1000` | Fallback RPM when no policy row exists for a team |

### Cache Service (`ca-cache-dev-sdc`, :8002)

| Variable | Value / source | Description |
|----------|----------------|-------------|
| `REDIS_URL` | Redis Premium (from Key Vault) | Redis for semantic cache storage |
| `LITELLM_URL` | `http://ca-litellm-dev-sdc:8003` | Upstream for cache misses |
| `LITELLM_MASTER_KEY` | from Key Vault | Bearer token for LiteLLM API |
| `AUTH_URL` | `http://ca-auth-dev-sdc:8001` | Auth service for upstream validation |
| `OBSERVABILITY_URL` | `http://ca-observability-dev-sdc:8004` | Async event posting |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Model used for semantic similarity |
| `EMBEDDING_API_KEY` | from Key Vault | API key for embedding calls |
| `EMBEDDING_BASE_URL` | `http://ca-litellm-dev-sdc:8003/v1` | Base URL for embedding API (embeddings go via the gateway / litellm) |
| `DEFAULT_SIMILARITY_THRESHOLD` | `0.95` | Cosine similarity threshold for cache hits |
| `DEFAULT_TTL_SECONDS` | `3600` | Cache entry TTL (1 hour) |

### Observability Service (`ca-observability-dev-sdc`, :8004)

| Variable | Value / source | Description |
|----------|----------------|-------------|
| `DATABASE_URL` | see above | Postgres for cost_records and audit_log writes |
| `BUS_PROVIDER` | `servicebus` | Event bus provider (Azure Service Bus in ACA; `memory` for local) |
| `AZURE_SERVICE_BUS_CONNECTION_STRING` | from Key Vault | Service Bus connection string |
| `AZURE_SERVICE_BUS_TOPIC` | `observability-events` | Service Bus entity name (the dev environment provisions the queue `observability-events`) |
| `AZURE_SERVICE_BUS_SUBSCRIPTION` | `gateway-workers` | Subscription name |
| `APPINSIGHTS_CONNECTION_STRING` | from Key Vault | Application Insights connection string |

### Admin Portal (`ca-admin-dev-sdc`, :8005)

| Variable | Value / source | Description |
|----------|----------------|-------------|
| `DATABASE_URL` | see above | Postgres for all admin data |
| `REDIS_URL` | Redis Premium (from Key Vault) | Redis for portal sessions (`portal_session:{token}`) |
| `SECRET_KEY` | from Key Vault | Session signing key |
| `ADMIN_TOKEN` | from Key Vault | Required `X-Admin-Token` header value for admin/automation requests (always enforced) |
| `OIDC_ISSUER` | Entra ID issuer URL | OIDC issuer URL for admin portal login |
| `OIDC_CLIENT_ID` | app registration client ID | OIDC client ID |
| `OIDC_CLIENT_SECRET` | from Key Vault | OIDC client secret |
| `LITELLM_MASTER_KEY` | from Key Vault | Bearer token for LiteLLM management API |
| `AUTH_URL` | `http://ca-auth-dev-sdc:8001` | Auth service URL (for health checks) |
| `CACHE_URL` | `http://ca-cache-dev-sdc:8002` | Cache service URL (for health checks) |
| `LITELLM_URL` | `http://ca-litellm-dev-sdc:8003` | LiteLLM URL (for health checks and key push) |
| `OBSERVABILITY_URL` | `http://ca-observability-dev-sdc:8004` | Observability service URL (for health checks) |
| `GITHUB_WEBHOOK_SECRET` | from Key Vault | HMAC secret for validating `X-Hub-Signature-256` on `POST /webhooks/github`. Set to match the secret configured in your GitHub repository or organisation webhook settings. Required for GitHub commit-to-session attribution. |

### Provider API Keys (stored in DB, also readable from env)

| Variable | Provider |
|----------|----------|
| `ANTHROPIC_API_KEY` | Anthropic (Claude Opus, Sonnet, Haiku) |
| `OPENAI_API_KEY` | OpenAI (GPT-4o, GPT-4o Mini) |
| `GEMINI_API_KEY` | Google (Gemini 1.5 Pro, Flash) |
| `GITHUB_MODELS_API_KEY` | GitHub Models (GPT-4o via GitHub) |
