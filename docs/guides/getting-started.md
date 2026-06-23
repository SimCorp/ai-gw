# Getting Started Guide

Welcome to the AI Gateway platform. This guide explains how to access and use the
deployed gateway, run the test suite on your machine, and ship changes.

The platform runs as a **Docker Compose stack on a single Linux VM** in the SimCorp dev
landing zone (Sweden Central), fronted by **Caddy** for TLS termination on port 443.
The gateway is reached at `https://dev.aigw.scdom.net` over the **corporate VPN (ZPA)**.
Services discover each other by container name on the internal Compose network.

## Prerequisites

- **Corporate VPN (ZPA)** access (the gateway is reachable only over the corporate network)
- A **SimCorp Entra ID** account (SSO is the only sign-in method for the portals)
- An `sk-*` **API key** for programmatic / inference access (issued via the admin portal)
- Python 3.11+ — to run the test suite locally
- **Docker** — only for the testcontainers-based suites (`identity`, `admin`)
- Git

## Accessing the Deployed Platform

The dev environment is reachable over the VPN at:

```
https://dev.aigw.scdom.net
```

### Portals

The developer portal is served at the root (`/`) and the admin portal at `/admin`. Sign
in with **Entra ID SSO** — there is no local/password login.

| Interface | URL |
|-----------|-----|
| **Developer Portal** | `https://dev.aigw.scdom.net/` |
| **Admin Portal** | `https://dev.aigw.scdom.net/admin` |

### SSO (Azure Entra ID)

Authentication is **Azure Entra ID only** (tenant `aa81b43f-3969-4fd4-80c9-84c411508d82`).

- **Issuer:** `https://login.microsoftonline.com/aa81b43f-3969-4fd4-80c9-84c411508d82/v2.0`
- **Redirect URI:** `https://dev.aigw.scdom.net/auth/oidc/callback`

After signing in you have no assigned roles by default; ask a `gateway_admin` to
grant permissions on the org nodes you need.

### Inference API

The OpenAI-compatible and Anthropic-compatible inference endpoints are exposed on the
gateway FQDN. Authenticate with your `sk-*` API key as a Bearer token.

| API | Base URL |
|-----|----------|
| OpenAI-compatible | `https://dev.aigw.scdom.net/v1` |
| Anthropic-compatible | `https://dev.aigw.scdom.net/anthropic` |

**Test chat completions:**

```bash
curl -X POST https://dev.aigw.scdom.net/v1/chat/completions \
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

Each service is a Compose service reached by its container name on the internal Compose
network (`http://<service>:<port>`). Only Caddy is published to the host; all other
services are internal. External callers use the gateway FQDN for inference and the
portals for the UI.

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| **Admin API** | `admin` | 8005 | Organization & user management |
| **Auth** | `auth` | 8001 | Login, sessions, permissions |
| **Cache** | `cache` | 8002 | Semantic + exact caching |
| **LiteLLM** | `litellm` | 8003 | Model provider routing |
| **Observability** | `observability` | 8004 | Usage tracking, audit logs |
| **Identity** | `identity` | 8006 | Agent registry, discovery |
| **Agent Relay** | `agent-relay` | 8007 | WebSocket relay for agents |
| **Librarian** | `librarian` | 8008 | Knowledge, embeddings, RAG |
| **Memory** | `memory` | 8009 | Agent conversation memory |
| **League** | `league` | 8010 | Gamified challenges |
| **Scanner** | `scanner` | — (no port) | Security scanning worker |
| **Admin Portal** | `admin-portal` | 3001 | Admin dashboard (Next.js) |
| **Developer Portal** | `portal` | 3002 | Main user interface (Next.js) |

Scanner and the workflow worker run as background workers with no exposed port.
PostgreSQL and Redis run as containers in the same Compose stack.

---

## Common Tasks

These calls go through the gateway under the `/api/<svc>/*` prefix (Caddy strips the
`/api/<svc>` segment before forwarding to the service). Reach them over the VPN at
`https://dev.aigw.scdom.net`. Replace `$TOKEN` with a valid session token.

### Create a New Organization Node

```bash
TOKEN="your-session-token"

# Create an area under root
curl -X POST https://dev.aigw.scdom.net/api/admin/nodes \
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
curl https://dev.aigw.scdom.net/api/admin/nodes/tree \
  -H "Authorization: Bearer $TOKEN" | jq '.'
```

### Grant User Permission

Use the Entra group GUID for the group you want to grant:

```bash
curl -X POST "https://dev.aigw.scdom.net/api/admin/nodes/{node_id}/permissions" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "entra_group_id": "12345678-1234-1234-1234-123456789012",
    "entra_group_name": "platform-admins@simcorp.com",
    "role": "gateway_admin"
  }'
```

### View Audit Log

```bash
curl https://dev.aigw.scdom.net/api/observability/audit-log \
  -H "Authorization: Bearer $TOKEN" | jq '.'
```

### Check User Permissions

```bash
curl https://dev.aigw.scdom.net/auth/me \
  -H "Authorization: Bearer $TOKEN" | jq '.roles'
```

---

## Development Workflow

The code is developed and tested locally, then deployed to the VM via container images
built and pushed by CI.

### Running Tests

Fast unit and integration tests run **locally**:

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

**End-to-end smoke tests** run against the deployed gateway at `dev.aigw.scdom.net`
over the VPN, not from a developer machine.

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

Migrations are applied on the VM by a dedicated one-off migration container (see
Deployment below), not on service startup.

---

## Deployment

Deployment is pull-based. Push to `master` → CI builds and pushes images to GHCR → the
VM pulls them. From the VM (`vm-aigw-dev-sdc`), in `/home/azureuser/ai-gw`:

```bash
# Routine single-service update (static base untouched)
scripts/update-service.sh <service>

# Full stack deploy
scripts/deploy-vm.sh
```

Both wrap `docker compose -f docker-compose.yml -f docker-compose.host.yml` under
`infra/`. **Rollback:** redeploy the previous image tag.

### Database Migrations

Migrations run on the VM via a one-off migration container against the Compose Postgres
service (see `scripts/deploy-vm.sh`), not on service startup.

---

## Key Concepts

### Configuration & Secrets

Configuration is supplied to the Compose stack via environment variables (sourced from
the VM's deploy-time secrets, not committed in plaintext). Services **fail fast** when a
required environment variable is missing — there are no local defaults.

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

**Cause:** The gateway is reachable only over the corporate VPN (ZPA).

**Solution:** Confirm you are connected to the corporate VPN. The gateway FQDN
(`https://dev.aigw.scdom.net`) and the portals are only resolvable and reachable from
inside the corporate network.

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
