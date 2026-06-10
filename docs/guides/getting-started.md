# Getting Started Guide

Welcome to the AI Gateway platform. This guide explains how to access and use the
deployed gateway, run the test suite on your machine, and ship changes to Azure.

The platform runs on **Azure Container Apps (ACA)** in the SimCorp Landing Zone
(Sweden Central). There is no local stack — every service is a Container App with
**internal ingress**, and the environment has no public IP. Access requires the
**corporate VPN**.

## Prerequisites

- **Corporate VPN** access (the ACA environment is internal-only, no public IP)
- A **SimCorp Entra ID** account (SSO is the only sign-in method)
- An `sk-*` **API key** for programmatic / inference access (issued via the admin portal)
- Python 3.11+ — to run the test suite locally
- **Docker** — only for the testcontainers-based suites (`identity`, `admin`)
- **Azure CLI** (`az`) — only if you deploy or run migration jobs
- Git

## Accessing the Deployed Platform

The dev environment is reachable over the VPN at:

```
https://aigw-dev.lab.cloud.scdom.net
```

### Portals

The admin and developer portals are reachable over the VPN. Sign in with **Entra ID
SSO** — there is no local/password login.

| Interface | How to access |
|-----------|---------------|
| **Admin Portal** | Reachable over VPN; sign in with Entra ID SSO |
| **Developer Portal** | Reachable over VPN; sign in with Entra ID SSO |

### SSO (Azure Entra ID)

Authentication is **Azure Entra ID only** (tenant `aa81b43f-3969-4fd4-80c9-84c411508d82`).

- **Issuer:** `https://login.microsoftonline.com/aa81b43f-3969-4fd4-80c9-84c411508d82/v2.0`
- **Redirect URI:** `https://aigw-dev.lab.cloud.scdom.net/auth/oidc/callback`

After signing in you have no assigned roles by default; ask a `platform_admin` to
grant permissions on the org nodes you need.

### Inference API

The OpenAI-compatible and Anthropic-compatible inference endpoints are exposed on the
gateway FQDN. Authenticate with your `sk-*` API key as a Bearer token.

| API | Base URL |
|-----|----------|
| OpenAI-compatible | `https://aigw-dev.lab.cloud.scdom.net/v1` |
| Anthropic-compatible | `https://aigw-dev.lab.cloud.scdom.net/anthropic` |

**Test chat completions:**

```bash
curl -X POST https://aigw-dev.lab.cloud.scdom.net/v1/chat/completions \
  -H "Authorization: Bearer sk-YOUR-API-KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-3.5-turbo",
    "messages": [
      {"role": "user", "content": "Hello!"}
    ]
  }'
```

---

## Service Topology

Each service is a Container App named `ca-<service>-dev-sdc` with **internal ingress**.
Service-to-service traffic uses internal DNS (`http://ca-<service>-dev-sdc`). These
hosts are only reachable from within the VNet; external callers use the gateway FQDN
for inference and the portals for the UI.

| Service | Container App | Internal Port | Purpose |
|---------|---------------|---------------|---------|
| **Admin API** | `ca-admin-dev-sdc` | 8005 | Organization & user management |
| **Auth** | `ca-auth-dev-sdc` | 8001 | Login, sessions, permissions |
| **Cache** | `ca-cache-dev-sdc` | 8002 | Semantic + exact caching |
| **LiteLLM** | `ca-litellm-dev-sdc` | 8003 | Model provider routing |
| **Observability** | `ca-observability-dev-sdc` | 8004 | Usage tracking, audit logs |
| **Identity** | `ca-identity-dev-sdc` | 8006 | Agent registry, discovery |
| **Agent Relay** | `ca-agent-relay-dev-sdc` | 8007 | WebSocket relay for agents |
| **Librarian** | `ca-librarian-dev-sdc` | 8008 | Knowledge, embeddings, RAG |
| **Memory** | `ca-memory-dev-sdc` | 8009 | Agent conversation memory |
| **League** | `ca-league-dev-sdc` | 8010 | Gamified challenges |
| **Scanner** | `ca-scanner-dev-sdc` | — (no ingress) | Security scanning worker |
| **Admin Portal** | `ca-admin-portal-dev-sdc` | 3001 | Admin dashboard (Next.js) |
| **Developer Portal** | `ca-portal-dev-sdc` | 3002 | Main user interface (Next.js) |

Scanner and the workflow worker run without ingress (background workers). PostgreSQL
and Redis are managed Azure resources, not Container Apps.

---

## Common Tasks

These calls hit internal service ingress and must originate from inside the VNet (e.g.
a VNet-connected runner or a bastion). Replace `$TOKEN` with a valid session token.

### Create a New Organization Node

```bash
TOKEN="your-session-token"

# Create an area under root
curl -X POST http://ca-admin-dev-sdc/nodes \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Platform Engineering",
    "type": "area",
    "parent_id": null,
    "description": "Core platform infrastructure",
    "color": "#FF5733"
  }'
```

### Get Organization Tree

```bash
curl http://ca-admin-dev-sdc/nodes/tree \
  -H "Authorization: Bearer $TOKEN" | jq '.'
```

### Grant User Permission

Use the Entra group GUID for the group you want to grant:

```bash
curl -X POST "http://ca-admin-dev-sdc/nodes/{node_id}/permissions" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "entra_group_id": "12345678-1234-1234-1234-123456789012",
    "entra_group_name": "platform-admins@simcorp.com",
    "role": "platform_admin"
  }'
```

### View Audit Log

```bash
curl http://ca-observability-dev-sdc/audit-log \
  -H "Authorization: Bearer $TOKEN" | jq '.'
```

### Check User Permissions

```bash
curl http://ca-auth-dev-sdc/me \
  -H "Authorization: Bearer $TOKEN" | jq '.roles'
```

---

## Development Workflow

The code is developed and tested locally, then deployed to Azure via container images.

### Running Tests

Fast unit and integration tests run **locally** without Azure:

```bash
# Install test dependencies
pip install -e "services/admin[dev]"
pip install -e "services/cache[dev]"
pip install -e "services/observability[dev]"

# Run all tests
pytest services/ -v

# Run specific service tests
pytest services/admin/tests/ -v --cov
```

> **Docker note:** The raw-SQL suites (`identity`, `admin`) use
> `testcontainers[postgres]` and require a running Docker daemon. The rest of the
> test suite runs without Docker.

**End-to-end smoke tests** run against the deployed Azure environment from a
VNet-connected runner (see `deploy.yml`), not from a developer machine.

### Code Quality

```bash
# Lint
ruff check services/

# Format
ruff format services/

# Type check (if mypy configured)
mypy services/
```

### Authoring a Database Migration

```bash
cd services/admin

# Create new migration file
alembic revision --autogenerate -m "describe your change"

# Review and edit migrations/versions/xxxx_description.py
```

Migrations are applied in Azure by a dedicated Container Apps job (see Deployment
below), not on service startup.

---

## Deployment

Deployments are driven by Bicep templates and are idempotent. Build a container image,
then deploy by pinning its tag.

```bash
az deployment group create \
  --resource-group rg-aigw-dev-sdc \
  --template-file infra/bicep/environments/dev/main.bicep \
  --parameters infra/bicep/environments/dev/main.bicepparam \
  --parameters imageTag=sha-<git-sha>
```

**Rollback:** redeploy the previous `imageTag`.

### Database Migrations

Run migrations against the deployed database via the migration job:

```bash
az containerapp job start \
  --name job-db-migrate-dev-sdc \
  --resource-group rg-aigw-dev-sdc
```

---

## Key Concepts

### Configuration & Secrets

Configuration comes from **Azure Key Vault**, surfaced through ACA native secret
references using the service's managed identity. Services **fail fast** when a required
environment variable is missing — there are no local defaults.

### Path-Based Permissions

Users have roles on org nodes. Permission checks use path prefixes:
- User with `area_owner` at `/root/area` can access `/root/area`, `/root/area/unit`, `/root/area/unit/team`
- User with `team_admin` at `/root/area/unit/team` can only access that team

See `docs/guides/permission-model.md` for detailed examples.

### Session Token

After login, the response includes a `token` field. This token:
- Is a URL-safe string
- Is stored in Redis with a TTL (7 days for sessions, 8h for admin)
- Contains user info, roles, and node assignments
- Is validated on every request via `Authorization: Bearer {token}`

### Cost Tracking

Every AI API call is logged to `cost_records`:
- Model name, token counts, cost in USD
- Associated node_id (for billing/budget rollup)
- Timestamp for MTD (month-to-date) calculations

Budget alerts trigger when spend exceeds `budget_alert_threshold` (default 0.80 = 80%).

---

## Troubleshooting

### Cannot reach the gateway or portals

**Cause:** The ACA environment is internal-only (no public IP).

**Solution:** Confirm you are connected to the corporate VPN. The gateway FQDN
(`https://aigw-dev.lab.cloud.scdom.net`) and the portals are only resolvable and
reachable from inside the corporate network.

### "Session expired or invalid" after login

**Cause:** Token not found in Redis or sign-in did not complete.

**Solution:** Sign in again via Entra ID SSO. If the problem persists, the session
store may be unhealthy — escalate in #ai-gateway.

---

## Next Steps

1. **Explore the API:** Read `docs/api/nodes.md` for organization endpoints
2. **Understand Permissions:** See `docs/guides/permission-model.md`
3. **Review Architecture:** Check `docs/architecture/services.md` for service overview
4. **Try the Portal:** Sign in over VPN with Entra ID SSO and explore the admin dashboard
5. **Write Tests:** See `services/admin/tests/` for examples

---

## Documentation Map

| Document | Purpose |
|----------|---------|
| `docs/api/nodes.md` | Organization nodes API reference |
| `docs/api/auth.md` | Authentication, sessions, OIDC |
| `docs/architecture/services.md` | Service overview and request paths |
| `docs/architecture/org-model.md` | Data model, materialized path, permissions |
| `docs/guides/permission-model.md` | Path-based access control in detail |
| `docs/guides/migration-from-v1.md` | Upgrading from Areas/Units/Teams |
| `README.md` (root) | Project overview and quick start |

---

## Support

- **Issues:** Create an issue on GitHub
- **Questions:** Slack #ai-gateway or email devops@simcorp.com
- **Code Review:** Submit PR to master branch; CI will run tests
