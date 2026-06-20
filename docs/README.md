# AI Gateway Documentation

Complete developer documentation for the SimCorp AI Gateway platform serving ~2000 engineers.

## Quick Start

**New to the project?** Start here:

1. [Getting Started Guide](guides/getting-started.md) — Access the deployed gateway at `https://dev.aigw.scdom.net`, run tests, deploy
2. [Permission Model Guide](guides/permission-model.md) — Understand path-based access control
3. [Services Architecture](architecture/services.md) — Overview of all microservices

## API Reference

### Core APIs

- **[Organization Nodes API](api/nodes.md)** — Manage the hierarchical organization tree
  - CRUD operations (create, list, update, delete)
  - Tree traversal (ancestors, children)
  - Member management
  - Policy & budget controls
  - Permission grants

- **[Authentication & Authorization API](api/auth.md)** — User auth, sessions, permissions
  - Login (password & OIDC)
  - Password reset flow
  - Session management
  - Service accounts & API keys
  - User invitations
  - Contractor settings

## Architecture

### System Design

- **[Services Overview](architecture/services.md)** — All microservices and their roles
  - Request path flow (Caddy → Cache → [Cache calls Auth] → LiteLLM → Provider)
  - Data flows and dependencies
  - Service port map
  - Docker Compose topology (deferred ACA/V2 topology in the deployment design)

- **[Organization Model](architecture/org-model.md)** — Deep dive into the org hierarchy
  - Materialized path tree structure
  - Role assignments via Entra groups
  - Permission inheritance algorithm
  - Cost tracking integration
  - Performance considerations

## Developer Guides

### Essential Guides

- **[Getting Started](guides/getting-started.md)**
  - Accessing the deployed gateway at `https://dev.aigw.scdom.net` (corp VPN/ZPA + Entra ID SSO)
  - Inference API endpoints and `sk-*` keys
  - Common tasks (create node, grant role, etc.)
  - Running tests locally and deploying

- **[Permission Model](guides/permission-model.md)**
  - Path-based access control explained
  - Role power hierarchy
  - can_access() algorithm walkthrough
  - Permission check examples
  - Debugging permission issues

- **[Migration from v1](guides/migration-from-v1.md)**
  - Areas/Units/Teams → organization_nodes
  - API endpoint mapping
  - Foreign key updates
  - Role model changes
  - Backward compatibility notes

## Key Concepts

### Organization Tree (organization_nodes)

```
SimCorp (root)
├── Platform (area)
│   ├── Infrastructure (unit)
│   │   └── Lift (team)
│   └── DevTools (unit)
└── Science (area)
    └── ML Platform (unit)
```

- **Materialized Path:** `/root-id/area-id/unit-id/team-id`
- **Single Table:** `organization_nodes(id, name, type, parent_id, path, ...)`
- **Path-Based Permissions:** Role at `/root/area` grants access to all descendants

### Roles & Permissions

```
platform_admin (6) ─ System access
area_owner (5)     ─ Area + descendants
unit_lead (4)      ─ Unit management
team_admin (3)     ─ Team management
developer (2)      ─ Developer access
viewer (1)         ─ Read-only
```

**Permission Check:**
```python
can_access(user, target_path, min_role) → bool
# ✓ if ANY user role has:
#   - node_path that is a prefix of target_path, AND
#   - role power >= min_role power
```

### Session Model

After login, session payload contains:
```json
{
  "user_id": "...",
  "email": "...",
  "roles": [
    {
      "role": "area_owner",
      "node_path": "/root/.../area",
      "node_id": "...",
      "node_name": "..."
    }
  ],
  "primary_node_id": "..."
}
```

All permission checks use path prefixes (memory, no DB).

## Services Map

Each service runs as a container in the Docker Compose stack. Service-to-service traffic uses
container names (`http://<service>:<port>`).

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| **Caddy** | `caddy` | 80/443 | TLS termination, reverse proxy |
| **Admin API** | `admin` | 8005 | Org management backend |
| **Auth** | `auth` | 8001 | Authentication & sessions |
| **Cache** | `cache` | 8002 | Semantic + exact caching |
| **LiteLLM** | `litellm` | 8003 | Model provider routing |
| **Observability** | `observability` | 8004 | Usage tracking & audit |
| **Identity** | `identity` | 8006 | Agent registry |
| **Agent Relay** | `agent-relay` | 8007 | WebSocket relay bus |
| **Librarian** | `librarian` | 8008 | Knowledge & embeddings |
| **Memory** | `memory` | 8009 | Agent memory service |
| **League** | `league` | 8010 | Gamified challenges |
| **Scanner** | `scanner` | — (background) | Security scanning worker |
| **Admin Portal** | `admin-portal` | 3001 | Admin dashboard |
| **Developer Portal** | `portal` | 3002 | Main user interface |

External callers reach inference via the gateway URL (`https://dev.aigw.scdom.net/v1`
and `/anthropic`); the portals are reachable over the corporate VPN with Entra ID SSO.

## Common Tasks

### Create an Organization Node
```bash
curl -X POST http://admin:8005/nodes \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Platform",
    "type": "area",
    "parent_id": null
  }'
```

See [Getting Started](guides/getting-started.md) for examples.

### Grant User Permission
```bash
curl -X POST "http://admin:8005/nodes/{node_id}/permissions" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "entra_group_id": "...",
    "role": "area_owner"
  }'
```

See [Nodes API Reference](api/nodes.md) for all permission endpoints.

### Check User Permissions
```bash
curl http://auth:8001/me \
  -H "Authorization: Bearer $TOKEN" | jq '.roles'
```

See [Permission Model Guide](guides/permission-model.md) for understanding results.

## Testing & Development

The code is developed and tested locally, then deployed to the dev VM as container images
(`git push` master → CI builds + pushes to GHCR → VM pulls).
See [Getting Started](guides/getting-started.md) for access, testing, and deployment.

### Running Tests
```bash
pip install -e "services/admin[dev]"
pytest services/ -v
```

> The raw-SQL suites (`identity`, `admin`) use `testcontainers[postgres]` and need a
> running Docker daemon. End-to-end tests are a standalone `@playwright/test` suite in
> `e2e/`, run against the deployed gateway as a post-deploy quality check (not a CI gate).

### Linting & Formatting
```bash
ruff check services/
ruff format services/
```

### Deploy (dev VM — current)
```bash
scripts/update-service.sh <svc>   # routine single-service update
scripts/deploy-vm.sh              # full stack deploy
```
The Compose stack always uses both files:
`docker compose -f docker-compose.yml -f docker-compose.host.yml`.

### Deploy (ACA / V2 — deferred)
```bash
az deployment group create \
  --resource-group rg-aigw-dev-sdc \
  --template-file infra/bicep/environments/dev/main.bicep \
  --parameters infra/bicep/environments/dev/main.bicepparam \
  --parameters imageTag=sha-<git-sha>
```
Rollback by redeploying the previous `imageTag`. See
[`architecture/environments.md`](architecture/environments.md) for the ACA env guide.

## Database

**PostgreSQL:** Single `aigateway` database shared by all services.

**Key Tables:**
- `organization_nodes` — Org hierarchy with materialized path
- `users` — User accounts
- `role_assignments` — Entra group → role → node mappings
- `cost_records` — Usage tracking for billing
- `audit_log` — Activity records
- `policies` — Cache/rate-limit settings per node
- Plus service-specific tables (league, scanner, etc.)

**Migrations:** Alembic (services/admin/migrations/)

## Related Documentation

### High-Level Design
- [AI Gateway Design Spec](superpowers/specs/2026-05-05-ai-gateway-design.md) — Full system design
- [Org Node Refactor Design](superpowers/specs/2026-05-28-org-node-refactor-design.md) — Migration to unified model

### Feature Specs
- [Security Scanner Design](superpowers/specs/2026-05-28-security-scanner-design.md)
- [AI Champions Community](superpowers/specs/2026-05-28-ai-champions-community-design.md)
- [AI League](superpowers/specs/2026-05-26-ai-league-design.md)
- [IT Tools](superpowers/specs/2026-05-28-it-tools-design.md)

## Support & Contact

- **Issues:** GitHub issues on main repo
- **Slack:** #ai-gateway channel
- **Email:** devops@simcorp.com

## Document Index

| Document | Purpose | Audience |
|----------|---------|----------|
| [Getting Started](guides/getting-started.md) | Local dev setup | New developers |
| [Permission Model](guides/permission-model.md) | Authorization deep dive | All developers |
| [Migration from v1](guides/migration-from-v1.md) | API upgrade path | v1 users |
| [Nodes API Reference](api/nodes.md) | Organization API | API consumers |
| [Auth API Reference](api/auth.md) | Authentication API | API consumers |
| [Services Architecture](architecture/services.md) | Microservice overview | System designers |
| [Organization Model](architecture/org-model.md) | Data model & permissions | Backend developers |

---

**Last Updated:** May 2026
**Version:** 2.0 (Unified Organization Model)
