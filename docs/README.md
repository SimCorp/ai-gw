# AI Gateway Documentation

Complete developer documentation for the SimCorp AI Gateway platform serving ~2000 engineers.

## Quick Start

**New to the project?** Start here:

1. [Getting Started Guide](guides/getting-started.md) — Local dev setup in 10 minutes
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
  - Request path flow (Auth → Cache → LiteLLM → Provider)
  - Data flows and dependencies
  - Service port map
  - Development topology

- **[Organization Model](architecture/org-model.md)** — Deep dive into the org hierarchy
  - Materialized path tree structure
  - Role assignments via Entra groups
  - Permission inheritance algorithm
  - Cost tracking integration
  - Performance considerations

## Developer Guides

### Essential Guides

- **[Getting Started](guides/getting-started.md)**
  - Local setup with Docker Compose
  - Accessing the platform
  - Common tasks (create node, grant role, etc.)
  - Debugging and troubleshooting

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

| Service | Port | Purpose |
|---------|------|---------|
| **Admin API** | 8005 | Org management backend |
| **Auth** | 8001 | Authentication & sessions |
| **Cache** | 8002 | Semantic + exact caching |
| **LiteLLM** | 8003 | Model provider routing |
| **Observability** | 8004 | Usage tracking & audit |
| **Identity** | 8006 | Agent registry |
| **Agent Relay** | 8007 | WebSocket relay bus |
| **Librarian** | 8008 | Knowledge & embeddings |
| **Memory** | 8009 | Agent memory service |
| **League** | 8010 | Gamified challenges |
| **Scanner** | 8011 | Security scanning |
| **Admin Portal** | 3001 | Admin dashboard |
| **Developer Portal** | 3002 | Main user interface |

Access all via **Nginx hub at port 8080** (recommended for local dev).

## Common Tasks

### Create an Organization Node
```bash
curl -X POST http://localhost:8080/admin/nodes \
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
curl -X POST "http://localhost:8080/admin/nodes/{node_id}/permissions" \
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
curl http://localhost:8080/auth/me \
  -H "Authorization: Bearer $TOKEN" | jq '.roles'
```

See [Permission Model Guide](guides/permission-model.md) for understanding results.

## Testing & Development

### Local Setup
```bash
docker compose -f infra/docker-compose.yml up --build
```

See [Getting Started](guides/getting-started.md) for full instructions.

### Running Tests
```bash
pip install -e "services/admin[dev]"
pytest services/ -v
```

### Linting & Formatting
```bash
ruff check services/
ruff format services/
```

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
