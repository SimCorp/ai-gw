# Migration Guide: v1 Areas/Units/Teams → v2 Organization Nodes

This guide helps developers and API consumers transition from the legacy three-table hierarchy (Areas, Units, Teams) to the unified `organization_nodes` model with path-based permissions.

## Overview of Changes

| Aspect | v1 | v2 |
|--------|----|----|
| **Table Structure** | 3 tables (areas, units, teams) | 1 table (organization_nodes) with type field |
| **Tree Representation** | Parent-child via area_id/unit_id | Materialized path: `/root-id/area-id/unit-id/team-id` |
| **Hierarchy Depth** | Fixed 3 levels | Unlimited depth |
| **Permissions** | user_roles (scope_type, scope_id) | role_assignments (entra_group_id, node_id) |
| **Permission Source** | Local user_roles table | Entra groups (OIDC integration) |
| **Permission Check** | Manual scope matching | Automatic path-based inheritance |

---

## Table & API Migration

### Creating Nodes

**v1 Approach:**
```python
# Create area
POST /areas
{
  "name": "Platform",
  "description": "Platform infrastructure"
}
# Returns: {id: "area-uuid", ...}

# Create unit under area
POST /units
{
  "name": "Infrastructure",
  "area_id": "area-uuid"
}
# Returns: {id: "unit-uuid", ...}

# Create team under unit
POST /teams
{
  "name": "Lift",
  "unit_id": "unit-uuid"
}
# Returns: {id: "team-uuid", ...}
```

**v2 Approach:**
```python
# Create area (top-level)
POST /nodes
{
  "name": "Platform",
  "type": "area",
  "parent_id": null,
  "description": "Platform infrastructure"
}
# Returns: {id: "area-uuid", path: "/root-uuid/area-uuid", ...}

# Create unit (under area)
POST /nodes
{
  "name": "Infrastructure",
  "type": "unit",
  "parent_id": "area-uuid",
  "description": "..."
}
# Returns: {id: "unit-uuid", path: "/root-uuid/area-uuid/unit-uuid", ...}

# Create team (under unit)
POST /nodes
{
  "name": "Lift",
  "type": "team",
  "parent_id": "unit-uuid"
}
# Returns: {id: "team-uuid", path: "/root-uuid/area-uuid/unit-uuid/team-uuid", ...}
```

**Key Differences:**
- `parent_id` is explicit; no type-specific FK
- `type` is a string, not determined by table
- `path` is auto-generated from ancestors
- No dedicated endpoints per type (everything goes through `/nodes`)

---

### Listing Nodes

**v1:**
```python
GET /areas  # → [area objects]
GET /units  # → [unit objects]
GET /teams  # → [team objects]
```

**v2:**
```python
# List all nodes
GET /nodes

# Filter by type
GET /nodes?type=area
GET /nodes?type=unit
GET /nodes?type=team

# Filter by parent
GET /nodes?parent_id=area-uuid

# Search by name or slug
GET /nodes?search=platform

# Get full tree
GET /nodes/tree  # Returns nested JSON
```

---

### Getting a Specific Node

**v1:**
```python
GET /areas/{id}
GET /units/{id}
GET /teams/{id}
```

**v2:**
```python
GET /nodes/{id}  # Works for any node type
```

**v2 Response includes:**
- `parent` — parent node object
- `children` — array of direct child nodes
- `member_count` — number of team members
- `spend_mtd` — month-to-date spend

---

### Updating & Deleting

**v1:**
```python
PUT /areas/{id}
PUT /units/{id}
PUT /teams/{id}
DELETE /areas/{id}
DELETE /units/{id}
DELETE /teams/{id}
```

**v2:**
```python
PUT /nodes/{id}
DELETE /nodes/{id}
```

---

## Foreign Key Migration in Dependent Tables

Services using `area_id`, `unit_id`, or `team_id` must update FK columns to `node_id`.

### cost_records

**v1 Schema:**
```sql
CREATE TABLE cost_records (
  id UUID,
  team_id UUID REFERENCES teams(id),
  model TEXT,
  tokens INTEGER,
  cost_usd NUMERIC(12, 2),
  ...
);
```

**v2 Schema:**
```sql
CREATE TABLE cost_records (
  id UUID,
  node_id UUID REFERENCES organization_nodes(id),
  model TEXT,
  tokens INTEGER,
  cost_usd NUMERIC(12, 2),
  ...
);
```

**Migration Script:**
```sql
-- Add new column
ALTER TABLE cost_records ADD COLUMN node_id UUID;

-- Migrate data: map team_id → team node in organization_nodes
UPDATE cost_records cr
SET node_id = (
  SELECT id FROM organization_nodes
  WHERE legacy_team_id = cr.team_id  -- Assumes temp legacy_team_id column
)
WHERE node_id IS NULL;

-- Drop old column
ALTER TABLE cost_records DROP COLUMN team_id;
ALTER TABLE cost_records ALTER COLUMN node_id SET NOT NULL;
ALTER TABLE cost_records ADD CONSTRAINT fk_cost_records_node
  FOREIGN KEY (node_id) REFERENCES organization_nodes(id);
```

### api_keys

**v1:**
```sql
team_id UUID REFERENCES teams(id)
```

**v2:**
```sql
node_id UUID REFERENCES organization_nodes(id)
```

**Same migration approach as cost_records.**

### policies

**v1:**
```sql
team_id UUID REFERENCES teams(id)
```

**v2:**
```sql
node_id UUID REFERENCES organization_nodes(id)
```

---

## Permission Model Migration

### v1: user_roles Table

```sql
CREATE TABLE user_roles (
  user_id UUID,
  role TEXT,  -- 'admin', 'manager', 'developer', 'viewer'
  scope_type TEXT,  -- 'global' or 'team'
  scope_id UUID,  -- team_id or NULL for global
  ...
);
```

Example:
```
user_id: alice-uuid
role: 'team_admin'
scope_type: 'team'
scope_id: team-uuid-123  -- Alice can manage this specific team
```

### v2: role_assignments Table

```sql
CREATE TABLE role_assignments (
  entra_group_id TEXT,  -- Azure AD group GUID
  entra_group_name TEXT,
  role TEXT,  -- 'platform_admin', 'area_owner', 'team_admin', 'developer', 'viewer'
  node_id UUID REFERENCES organization_nodes(id),
  ...
);
```

Example:
```
entra_group_id: '12345678-1234-1234-1234-123456789012'
entra_group_name: 'platform-admins@simcorp.com'
role: 'platform_admin'
node_id: root-uuid  -- This group is platform admin everywhere
```

### Role Mapping

| v1 Role | v1 Scope | → | v2 Role | v2 Assignment |
|---------|----------|---|---------|---------------|
| admin (global) | global | → | platform_admin | node_id = root |
| manager (area scope) | area_id | → | area_owner | node_id = area |
| manager (team scope) | team_id | → | team_admin | node_id = team |
| developer | team_id | → | developer | node_id = team |
| viewer | team_id | → | viewer | node_id = team |

### Migration Process

1. **Create Entra groups** (if not exist) for each v1 permission level
   - `platform-admins@simcorp.com`
   - `area-owners@simcorp.com`
   - `team-admins@simcorp.com`
   - etc.

2. **Populate role_assignments from user_roles:**
   ```sql
   INSERT INTO role_assignments (entra_group_id, entra_group_name, role, node_id)
   SELECT
     -- Map user → entra_group_id (requires external mapping)
     entra_group_id,
     entra_group_name,
     -- Map v1 role to v2 role
     CASE WHEN scope_type = 'global' AND role = 'admin' THEN 'platform_admin'
          WHEN scope_type = 'area' THEN 'area_owner'
          WHEN role = 'team_admin' THEN 'team_admin'
          ELSE role
     END,
     -- Map scope_id to node_id
     COALESCE(
       (SELECT id FROM organization_nodes WHERE legacy_team_id = user_roles.scope_id),
       (SELECT id FROM organization_nodes WHERE legacy_area_id = user_roles.scope_id),
       (SELECT id FROM organization_nodes WHERE type = 'root')
     )
   FROM user_roles;
   ```

3. **Verify permissions** via test login (OIDC) and check session payload

---

## Permission Checks: v1 vs v2

### v1 Permission Check

```python
def can_manage_team(user: dict, team_id: str) -> bool:
    """Check if user has team_admin or higher on this team."""
    for role in user.get("roles", []):
        if role["scope_type"] == "global" and role["role"] == "admin":
            return True  # Global admin can manage any team
        if role["scope_type"] == "team" and role["scope_id"] == team_id:
            if role["role"] in ("admin", "manager"):
                return True
    return False
```

### v2 Permission Check

```python
def can_manage_team(user: dict, team_id: str, session: AsyncSession) -> bool:
    """Check if user has team_admin+ on this team."""
    # Get team's path
    team = await session.execute(
        text("SELECT path FROM organization_nodes WHERE id = ?"),
        (team_id,)
    ).scalar()
    
    # Use path-based check (memory-only, no DB)
    return can_access(user, team.path, "team_admin")
```

**Key Advantage:** v2 check is O(1) memory operation; no DB query needed.

---

## Portal Migration

### Admin Portal

**v1 Organization Page:**
```
Areas
  ├─ Area 1
  │   ├─ Units
  │   │   ├─ Unit 1.1
  │   │   │   ├─ Teams
  │   │   │   │   └─ Team 1.1.1
```

**v2 Organization Page:**
```
Organization Tree (fully recursive)
  ├─ Node 1 (any type)
  │   ├─ Node 1.1
  │   │   ├─ Node 1.1.1
  │   │   └─ Node 1.1.2
  │   └─ Node 1.2
```

**API Updates:**
- Use `GET /nodes/tree` to fetch hierarchy
- Use `POST /nodes`, `PUT /nodes/{id}`, `DELETE /nodes/{id}` for CRUD
- All nodes use same endpoints (no type-specific routes)

### Developer Portal

No major changes to end-user experience. Internally:
- Org context is still retrieved from `organization_nodes`
- User's primary team is now `primary_node_id` instead of `primary_team_id`
- Spend/budget queries use path-based subtree search

---

## Backward Compatibility

### Deprecation Timeline

- **Phase 1 (Current):** v2 API live; v1 endpoints deprecated but functional
- **Phase 2 (6 months):** v1 endpoints return 410 Gone; force migration of clients
- **Phase 3:** v1 tables removed from schema

### Legacy Endpoint Stubs

For a short transition period, v1 routes may be re-implemented as shims:

```python
@app.get("/areas")
async def list_areas_v1_compat(session: AsyncSession):
    """Deprecated: use GET /nodes?type=area instead."""
    nodes = await session.execute(
        text("SELECT * FROM organization_nodes WHERE type = 'area'")
    ).mappings().all()
    return nodes
```

---

## Common Migration Patterns

### Pattern 1: Updating Cost Queries

**v1:**
```python
# Get team spend
spend = db.query(CostRecord)\
  .filter(CostRecord.team_id == team_id)\
  .sum(CostRecord.cost_usd)
```

**v2:**
```python
# Get team spend (direct)
spend = db.query(CostRecord)\
  .filter(CostRecord.node_id == team_id)\
  .sum(CostRecord.cost_usd)

# Get team + descendants spend (subtree)
team_path = db.query(OrganizationNode.path)\
  .filter(OrganizationNode.id == team_id).scalar()
spend_subtree = db.query(CostRecord)\
  .join(OrganizationNode)\
  .filter(OrganizationNode.path.like(team_path + '/%'))\
  .sum(CostRecord.cost_usd)
```

### Pattern 2: Permission Checks in Frontend

**v1:**
```javascript
// Admin portal checks user's roles locally
const isTeamAdmin = user.roles.some(
  r => r.role === 'team_admin' && r.scope_id === teamId
);
```

**v2:**
```javascript
// Still checks roles locally, but path-based
const canAccessTeam = (user, teamPath) => {
  const roles = user.roles || [];
  return roles.some(r => {
    const nodePath = r.node_path || "";
    return teamPath.startsWith(nodePath) &&
           ROLE_POWER[r.role] >= ROLE_POWER["team_admin"];
  });
};
```

### Pattern 3: Bulk Operations

**v1: Update all teams in an area**
```python
db.query(Team)\
  .filter(Team.unit.area_id == area_id)\
  .update({"budget": new_budget})
```

**v2: Update all descendants of a node**
```python
area_path = db.query(OrganizationNode.path)\
  .filter(OrganizationNode.id == area_id).scalar()

db.query(OrganizationNode)\
  .filter(OrganizationNode.path.like(area_path + '/%'))\
  .update({"monthly_budget_usd": new_budget})
```

---

## Troubleshooting

### Issue: "Node not found" after migration

**Cause:** Foreign key still pointing to old team_id instead of node_id.

**Solution:**
```sql
-- Check for orphaned records
SELECT * FROM cost_records WHERE node_id IS NULL;

-- Re-run migration script to populate node_id
```

### Issue: Permissions denied after OIDC login

**Cause:** role_assignments not populated or Entra group GUIDs don't match.

**Solution:**
1. Check session payload: `GET /auth/me` should include roles array
2. Verify Entra group GUIDs in role_assignments table
3. Confirm OIDC claims include groups: `id_token` must have `groups` claim

### Issue: Budget queries showing wrong amounts

**Cause:** Mixing direct spend (node_id) with subtree spend (path LIKE).

**Solution:**
- Direct node spend: `WHERE node_id = ?`
- Subtree spend: `WHERE path LIKE ? || '/%'` (includes all descendants)
- Make the intent explicit in query comments

---

## Migration Checklist

- [ ] Alembic migration created and tested locally
- [ ] New organization_nodes table populated from areas/units/teams
- [ ] Foreign keys updated in cost_records, api_keys, policies
- [ ] role_assignments populated from user_roles + Entra groups
- [ ] Entra groups created and verified
- [ ] v1 API endpoints deprecated (marked 410 or redirected)
- [ ] Frontend updated to use /nodes endpoints
- [ ] Permission checks refactored to use can_access()
- [ ] Admin and developer portals tested end-to-end
- [ ] v1 tables removed (after deprecation period)

---

## Questions & Support

For migration help:
- Review `docs/api/nodes.md` for v2 API reference
- Check `docs/architecture/org-model.md` for data model details
- See `docs/guides/permission-model.md` for permission logic
