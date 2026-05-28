# Organization Node Architecture

Design document for the unified hierarchical organization model. Replaces the legacy Areas/Units/Teams three-table structure with a single materialized-path tree and Entra-group-based role assignment.

## Data Model

### organization_nodes Table

The primary table for the org tree. Uses materialized path for efficient range queries and breadcrumb lookups.

```sql
CREATE TABLE organization_nodes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  slug TEXT NOT NULL,
  type TEXT NOT NULL DEFAULT 'team',
  parent_id UUID REFERENCES organization_nodes(id) ON DELETE CASCADE,
  path TEXT NOT NULL UNIQUE,
  color TEXT,
  description TEXT,
  location TEXT,
  monthly_budget_usd NUMERIC(12, 2),
  budget_alert_threshold NUMERIC(4, 2) DEFAULT 0.80,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX idx_nodes_path ON organization_nodes USING BTREE (path text_pattern_ops);
CREATE INDEX idx_nodes_parent_id ON organization_nodes(parent_id);
CREATE UNIQUE INDEX org_nodes_parent_slug_key ON organization_nodes(parent_id, slug);
```

**Fields:**
- `id`: UUID primary key; generated server-side
- `name`: Human-readable node name (e.g., "Platform Engineering", "Lift")
- `slug`: URL-safe identifier, auto-generated from name via `slugify(name.lower())`
- `type`: Node type; e.g., `root`, `area`, `unit`, `team` (user-defined, not constrained)
- `parent_id`: Self-referencing foreign key; NULL for root nodes
- `path`: Materialized path; format: `/{root-id}/{area-id}/{unit-id}/{team-id}`
  - Includes all ancestor UUIDs and the node's own UUID
  - Used for permission inheritance and range queries
  - Uniqueness prevents cycles
- `color`: Optional hex color for UI rendering
- `description`: Optional node description
- `location`: Optional physical location
- `monthly_budget_usd`: Optional monthly budget cap
- `budget_alert_threshold`: Percentage (0-1) at which to alert (default 0.80)
- `created_at`: Node creation timestamp

**Key Constraint:** Unique index on `(parent_id, slug)` — no duplicate names under the same parent

---

### role_assignments Table

Maps Entra groups to roles on specific nodes. Replaces the legacy user_roles table for OIDC-based access control.

```sql
CREATE TABLE role_assignments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entra_group_id TEXT NOT NULL,
  entra_group_name TEXT,
  role TEXT NOT NULL,
  node_id UUID NOT NULL REFERENCES organization_nodes(id) ON DELETE CASCADE,
  granted_at TIMESTAMPTZ DEFAULT NOW(),
  granted_by UUID REFERENCES users(id) ON DELETE SET NULL,
  UNIQUE (entra_group_id, role, node_id)
);

CREATE INDEX idx_role_assignments_group ON role_assignments(entra_group_id);
CREATE INDEX idx_role_assignments_node ON role_assignments(node_id);
```

**Fields:**
- `id`: UUID primary key
- `entra_group_id`: Azure AD / Entra ID group GUID (e.g., `12345678-1234-1234-1234-123456789012`)
- `entra_group_name`: Display name for the group (e.g., `platform-admins@simcorp.com`)
- `role`: Authorization level; valid values: `platform_admin`, `area_owner`, `unit_lead`, `team_admin`, `developer`, `viewer`
- `node_id`: Target organization node
- `granted_at`: When the assignment was created
- `granted_by`: User who made the assignment (for audit)

**Unique Constraint:** Prevents duplicate (entra_group_id, role, node_id) tuples

**Access Flow:**
1. User authenticates via OIDC (Dex / Entra ID)
2. ID token contains `groups` claim (list of Entra group GUIDs)
3. Server loads role_assignments for all user's groups
4. Session payload stores roles as array: `[{role, node_path, node_id, node_name}, ...]`
5. Permission check: `can_access(user, target_path, min_role)` matches path prefix and role power

---

## Materialized Path

The `path` field stores the entire ancestor chain as a slash-delimited string of UUIDs.

**Format:** `/{root-uuid}/{area-uuid}/{unit-uuid}/{team-uuid}`

**Properties:**
- **Prefix-based inheritance**: A path `/root/area/unit/team` starts with `/root`, `/root/area`, `/root/area/unit`
  - Role at `/root/area` applies to all descendants under that path
- **Efficient queries**: `WHERE path LIKE '/root/area/%'` finds all descendants in O(1) with index
- **Breadcrumb generation**: Split path by `/`, query all UUIDs to reconstruct ancestry
- **Uniqueness**: Prevents cycles and allows efficient parent-child relationships

**Example:**

```
Root: SimCorp
  path = /550e8400-e29b-41d4-a716-446655440000

Area: Platform
  path = /550e8400-e29b-41d4-a716-446655440000/550e8400-e29b-41d4-a716-446655440001

Unit: Infrastructure
  path = /550e8400-e29b-41d4-a716-446655440000/550e8400-e29b-41d4-a716-446655440001/550e8400-e29b-41d4-a716-446655440002

Team: Lift
  path = /550e8400-e29b-41d4-a716-446655440000/550e8400-e29b-41d4-a716-446655440001/550e8400-e29b-41d4-a716-446655440002/550e8400-e29b-41d4-a716-446655440003
```

---

## Permission Inheritance

### Role Power Hierarchy

Roles are ranked by power level:

```python
_ROLE_POWER = {
    "platform_admin": 6,    # System-wide access
    "area_owner": 5,        # Manage an area and all descendants
    "unit_lead": 4,         # Lead a unit
    "team_admin": 3,        # Administer a team
    "developer": 2,         # Developer access
    "viewer": 1,            # Read-only
}
```

A higher power level subsumes all lower roles. For example, `area_owner` (5) can perform all actions that `team_admin` (3) can.

### can_access() Algorithm

```python
def can_access(user: dict, target_path: str, min_role: str) -> bool:
    """
    Return True if user has at least min_role on target_path.
    
    Checks all roles in user.roles; if any role's node_path is a prefix of
    target_path AND role power >= min_role power, return True.
    """
    required = _ROLE_POWER.get(min_role, 0)
    
    for role_entry in user.get("roles", []):
        node_path = role_entry.get("node_path", "")
        role = role_entry.get("role", "")
        
        # Check if this role's node is an ancestor of target
        if node_path and target_path.startswith(node_path):
            # Check if role power is sufficient
            if _ROLE_POWER.get(role, 0) >= required:
                return True
    
    return False
```

**Example:**

User Alice has roles:
```json
{
  "roles": [
    {
      "role": "area_owner",
      "node_path": "/root-id/area-id",
      "node_id": "area-id",
      "node_name": "Platform"
    }
  ]
}
```

Permission checks:
- `can_access(alice, "/root-id/area-id", "viewer")` → True (area_owner >= viewer)
- `can_access(alice, "/root-id/area-id/unit-id", "team_admin")` → True (area_owner >= team_admin, path matches)
- `can_access(alice, "/root-id/other-area", "viewer")` → False (path doesn't start with `/root-id/area-id`)
- `can_access(alice, "/root-id/area-id", "platform_admin")` → False (area_owner < platform_admin)

---

## Access Control Examples

### Creating a Node

User must have `team_admin` at the parent path, or `platform_admin` at `/` for root-level.

```python
if body.parent_id:
    parent = get_node(body.parent_id)
    if not can_access(user, parent.path, "team_admin"):
        raise Forbidden("Cannot create child node here")
else:
    # Creating a root-level node requires platform_admin
    if not can_access(user, "/", "platform_admin"):
        raise Forbidden("Only platform admins can create root nodes")
```

### Updating Budget

Requires `area_owner` at the node. Only `area_owner` or higher can set budgets.

```python
node = get_node(node_id)
if not can_access(user, node.path, "area_owner"):
    raise Forbidden("Insufficient permissions to set budget")
```

### Setting Policy

Requires `team_admin` at the node.

```python
node = get_node(node_id)
if not can_access(user, node.path, "team_admin"):
    raise Forbidden("Insufficient permissions to set policy")
```

---

## Development Escape Hatch

In development mode (`ENVIRONMENT=development`), bcrypt-authenticated users (password login) are issued a synthetic `platform_admin` role:

```python
if _env in ("development", "test", "ci"):
    roles = [{"role": "platform_admin", "node_path": "/", "node_id": None, "node_name": "root"}]
else:
    # Production: bcrypt users have no roles until Entra-assigned
    roles = []
```

This allows local development without setting up Entra groups. In production, only OIDC users (logged in via Entra) have roles from group assignments.

---

## Migration from v1 (Areas/Units/Teams)

The legacy API used three separate tables:
- `areas`: Top-level organizational divisions
- `units`: Sub-divisions within areas
- `teams`: Leaf nodes (actual team units)

### Table Mapping

| v1 Entity | v1 Columns | → | v2 Model | v2 Columns |
|-----------|------------|---|----------|-----------|
| area | `id, name, slug, parent_id, ...` | → | organization_nodes | `id, name, slug, type='area', parent_id, path, ...` |
| unit | `id, name, slug, area_id, ...` | → | organization_nodes | `id, name, slug, type='unit', parent_id (= area_id), path, ...` |
| team | `id, name, slug, unit_id, ...` | → | organization_nodes | `id, name, slug, type='team', parent_id (= unit_id), path, ...` |

### API Endpoint Changes

| v1 Endpoint | v1 Purpose | → | v2 Endpoint |
|------------|-----------|---|-------------|
| `GET /areas` | List areas | → | `GET /nodes?type=area` |
| `POST /areas` | Create area | → | `POST /nodes` (with `type='area'`, no parent) |
| `GET /areas/{id}` | Get area | → | `GET /nodes/{id}` |
| `PUT /areas/{id}` | Update area | → | `PUT /nodes/{id}` |
| `DELETE /areas/{id}` | Delete area | → | `DELETE /nodes/{id}` |
| `GET /units` | List units | → | `GET /nodes?type=unit` |
| `POST /units` | Create unit | → | `POST /nodes` (with `type='unit'`, `parent_id=area_id`) |
| `GET /teams` | List teams | → | `GET /nodes?type=team` |
| `POST /teams` | Create team | → | `POST /nodes` (with `type='team'`, `parent_id=unit_id`) |

### Foreign Key Updates in Dependent Tables

Services that referenced `area_id`, `unit_id`, or `team_id` now reference `node_id`:

| Table | v1 Column | → | v2 Column |
|-------|-----------|---|-----------|
| `cost_records` | `team_id` (FK) | → | `node_id` (FK to organization_nodes) |
| `api_keys` | `team_id` (FK) | → | `node_id` (FK to organization_nodes) |
| `node_members` | — | → | `node_id` (FK to organization_nodes) |
| `policies` | `team_id` (FK) | → | `node_id` (FK to organization_nodes) |

### Role Model Changes

v1 used `user_roles` table with flat `scope_type` / `scope_id`:
```sql
user_roles: (user_id, role, scope_type, scope_id)
-- scope_type: 'global' or 'team'
-- scope_id: team_id or NULL
```

v2 uses `role_assignments` based on Entra groups:
```sql
role_assignments: (entra_group_id, role, node_id)
-- Maps Entra group → role → node (with path-based inheritance)
```

**User Roles Flow:**
1. User authenticates via OIDC
2. ID token includes `groups` claim (Entra group GUIDs)
3. Query `role_assignments` for all user's groups
4. Build roles array with node paths from organization_nodes
5. Store in session payload; use for permission checks

---

## Cost Records Integration

Cost records (from litellm / observability) are tagged with a `node_id`:

```sql
CREATE TABLE cost_records (
  id UUID PRIMARY KEY,
  node_id UUID NOT NULL REFERENCES organization_nodes(id),
  cost_usd NUMERIC(12, 2),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  ...
);
```

**Budget Queries:**
```sql
-- Spend for a node and all descendants (subtree)
SELECT COALESCE(SUM(cost_usd), 0)
FROM cost_records
JOIN organization_nodes n ON n.id = cost_records.node_id
WHERE n.path LIKE '/root/area/%'
  AND created_at >= date_trunc('month', NOW());

-- Spend for a node only (not descendants)
SELECT COALESCE(SUM(cost_usd), 0)
FROM cost_records
WHERE node_id = ?
  AND created_at >= date_trunc('month', NOW());
```

---

## Bootstrap Process

On first service startup, the root node is created:

```python
async def ensure_root_node(session: AsyncSession) -> dict:
    # Check if root exists (parent_id IS NULL)
    row = (await session.execute(
        text("SELECT id, path FROM organization_nodes WHERE parent_id IS NULL LIMIT 1")
    )).first()
    
    if row:
        return {"id": str(row[0]), "path": row[1]}
    
    # Create root: SimCorp
    root_id = str(uuid.uuid4())
    path = f"/{root_id}"
    await session.execute(
        text("""
            INSERT INTO organization_nodes (id, name, slug, type, path)
            VALUES (?, 'SimCorp', 'root', 'root', ?)
        """),
        (root_id, path),
    )
    await session.commit()
    return {"id": root_id, "path": path}
```

---

## Performance Considerations

### Indexes

- **`path` (text_pattern_ops)**: Enables efficient `LIKE` queries for subtree membership
- **`parent_id`**: Enables fast child lookups
- **`(parent_id, slug)`**: Enforces unique sibling names

### Query Patterns

1. **Get node by UUID**: Direct primary key lookup
2. **Find all descendants**: `WHERE path LIKE parent_path || '%'`
3. **Get breadcrumb**: Split path string, query all UUIDs
4. **Check ancestry**: `startswith()` on path strings (memory, no DB)
5. **Subtree spend**: Join cost_records, group by node

### Scaling Notes

- Materialized path works well for trees with depth < 20
- For very large organizations (100k+ nodes), consider additional denormalization (e.g., ancestry tables or nested set model)
- Redis caching of role_assignments by group_id recommended for OIDC on every request
