# Design Spec: Generic Org Node + Unified Permission Model
**Date:** 2026-05-28  
**Status:** Approved for implementation

---

## Context

The current admin service models the org hierarchy as three separate tables — `areas`, `units`, `teams` — with fixed 3-level depth. This creates:
- Duplicated router/model/migration code for each level
- No path-based permission inheritance (permissions checked with per-level DB lookups)
- Inability to add intermediate nodes (e.g. `Platform → DevEx → LIFT`)
- Fragmented Entra ID → role mapping living in a separate table

This spec defines a clean-break reimplementation replacing all three tables with a unified `organization_nodes` model using a Materialized Path, and replacing all role/permission tables with a single `role_assignments` table keyed to Entra group IDs.

---

## Decisions

| # | Question | Decision |
|---|----------|----------|
| 1 | Migration strategy | Clean break — drop and reimplement |
| 2 | Schema approach | Materialized Path (`path` column on every node) |
| 3 | Permission principal | Groups only — `role_assignments(entra_group_id, role, node_id)` |
| 4 | Dev/bootstrap access | Bcrypt escape hatch active in `ENVIRONMENT=development` only |
| 5 | Frontend navigation | Page-per-node at `/admin/nodes/{id}` with tab-based detail |
| 6 | Node type field | Free-text label (`TEXT`), no structural depth constraint |
| 7 | Entra import UX | Assign existing Entra group to existing node (no auto-create node) |

---

## 1. Database Schema

### `organization_nodes`

```sql
CREATE TABLE organization_nodes (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                   TEXT NOT NULL,
    slug                   TEXT NOT NULL,
    type                   TEXT NOT NULL DEFAULT 'team',   -- free-form: area|unit|team|squad|…
    parent_id              UUID REFERENCES organization_nodes(id) ON DELETE CASCADE,
    path                   TEXT NOT NULL UNIQUE,            -- /root-id/area-id/unit-id/team-id
    color                  TEXT,
    description            TEXT,
    location               TEXT,
    monthly_budget_usd     NUMERIC(12,2),
    budget_alert_threshold NUMERIC(4,2) DEFAULT 0.80,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(parent_id, slug)
);
CREATE INDEX idx_nodes_path      ON organization_nodes USING btree (path text_pattern_ops);
CREATE INDEX idx_nodes_parent_id ON organization_nodes (parent_id);
```

A single root node (type=`root`, path=`/<root-uuid>`) is auto-inserted on first startup when the table is empty.

### `role_assignments`

```sql
CREATE TABLE role_assignments (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entra_group_id   TEXT NOT NULL,
    entra_group_name TEXT,
    role             TEXT NOT NULL CHECK (role IN (
                         'platform_admin','area_owner','unit_lead',
                         'team_admin','developer','viewer')),
    node_id          UUID NOT NULL REFERENCES organization_nodes(id) ON DELETE CASCADE,
    granted_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    granted_by       UUID REFERENCES users(id) ON DELETE SET NULL,
    UNIQUE(entra_group_id, role, node_id)
);
CREATE INDEX idx_role_assignments_group ON role_assignments (entra_group_id);
CREATE INDEX idx_role_assignments_node  ON role_assignments (node_id);
```

**Replaces:** `user_roles` + `entra_group_role_mappings` (both dropped).

### FK renames

| Table | Old column | New column |
|-------|-----------|-----------|
| `cost_records` | `team_id` | `node_id → organization_nodes(id)` |
| `api_keys` | `team_id` | `node_id → organization_nodes(id)` |
| `team_members` → `node_members` | `team_id` | `node_id → organization_nodes(id)` |
| `users` | `primary_team_id` | `primary_node_id → organization_nodes(id)` |
| `policies` | `team_id` | `node_id → organization_nodes(id)` |
| `access_requests` | `resource_id TEXT` | `node_id UUID → organization_nodes(id)` |

**Dropped tables:** `areas`, `units`, `teams`, `user_roles`, `entra_group_role_mappings`

**Migration:** `0025_organization_nodes.py`

---

## 2. Permission Model

### Session payload (built at login)

```sql
SELECT ra.role, n.path AS node_path, n.id AS node_id, n.name AS node_name
FROM role_assignments ra
JOIN organization_nodes n ON n.id = ra.node_id
WHERE ra.entra_group_id = ANY(:group_ids)
```

Stored in Redis session:
```json
{
  "roles": [{ "role": "area_owner", "node_path": "/root/pt-id", "node_id": "pt-id" }],
  "group_ids": ["ab12cd34-..."]
}
```

### Request-time check (pure Python, zero DB queries)

```python
ROLE_POWER = {"platform_admin":6,"area_owner":5,"unit_lead":4,"team_admin":3,"developer":2,"viewer":1}

def can_access(user: dict, target_path: str, min_role: str) -> bool:
    required = ROLE_POWER.get(min_role, 0)
    for r in user.get("roles", []):
        if target_path.startswith(r["node_path"]):
            if ROLE_POWER.get(r["role"], 0) >= required:
                return True
    return False
```

### FastAPI dependency

```python
def require_node_role(min_role: str = "viewer"):
    async def _dep(node_id: str, current_user=Depends(get_current_user), session=Depends(get_session)):
        node = await _get_node(session, node_id)
        if not can_access(current_user, node.path, min_role):
            raise HTTPException(403)
        return node
    return _dep
```

### Dev escape hatch

`ENVIRONMENT=development` + bcrypt login → synthetic session with `roles=[{"role":"platform_admin","node_path":"/"}]`.  
The `/` prefix matches any path via `startswith`.

---

## 3. API — `/nodes` router

Replaces `/areas`, `/units`, `/teams` entirely.

```
GET    /nodes                         list (params: parent_id, type, search, limit, offset)
GET    /nodes/tree                    full tree JSON for initial org tree load
POST   /nodes                         create (body: name, type, parent_id, color, description, location)
GET    /nodes/{id}                    detail: node + parent + children[] + member_count + spend_mtd
PUT    /nodes/{id}                    update fields
DELETE /nodes/{id}                    delete + cascade descendants

GET    /nodes/{id}/ancestry           [root→node] list for breadcrumb
GET    /nodes/{id}/children           immediate children

GET    /nodes/{id}/members            paginated member list
POST   /nodes/{id}/members            add user (body: user_id)
DELETE /nodes/{id}/members/{user_id}

GET    /nodes/{id}/policy             { explicit: {…}, inherited: [{source_node_id, source_name, rule, value}] }
PUT    /nodes/{id}/policy             set explicit overrides (child overrides take precedence over parent)

GET    /nodes/{id}/budget             { budget_usd, spend_mtd, spend_children_mtd, pct_used, parent_budget }
PUT    /nodes/{id}/budget             set monthly_budget_usd (validated ≤ parent budget)

GET    /nodes/{id}/permissions        list role_assignments on this node
POST   /nodes/{id}/permissions        add (body: entra_group_id, entra_group_name, role)
DELETE /nodes/{id}/permissions/{aid}  remove
```

Budget spend query:
```sql
SELECT SUM(cost_usd) FROM cost_records cr
JOIN organization_nodes n ON n.id = cr.node_id
WHERE n.path LIKE :node_path || '%'
  AND cr.created_at >= date_trunc('month', NOW())
```

---

## 4. Frontend

### Routes

| Route | Purpose |
|-------|---------|
| `/admin/org` | Org tree browse (read-only) |
| `/admin/nodes/[id]` | Node detail — Overview / Policy / Budget / Permissions tabs |
| `/admin/nodes/[id]?tab=policy` | Deep-link to policy tab |

Sidebar Organisation section:
```
Organisation
├── Org tree  → /admin/org
└── Users     → /admin/users
```
Areas / Units / Teams links removed.

### New components

| Component | File | Purpose |
|-----------|------|---------|
| `Breadcrumb` | `_components/Breadcrumb.tsx` | Fetches `/nodes/{id}/ancestry`; renders clickable path |
| `OrgTree` | `_components/OrgTree.tsx` | Extracted from org/page.tsx; accepts `onSelect` for picker mode |
| `ResourceTable` | `_components/ResourceTable.tsx` | Generic child-node table used in Overview tab |
| `NodeDetailPage` | `nodes/[id]/page.tsx` | Tab bar + sub-panels |
| `PolicyPanel` | `nodes/[id]/_components/PolicyPanel.tsx` | Inherited (locked) + explicit (editable) rules |
| `PermissionsPanel` | `nodes/[id]/_components/PermissionsPanel.tsx` | role_assignments + Entra assign modal |
| `BudgetPanel` | `nodes/[id]/_components/BudgetPanel.tsx` | Spend chart + budget set |

### Deleted

`apps/admin/app/admin/areas/`, `units/`, `teams/` directories removed entirely.

---

## 5. Files Changed

**Backend:**
- `services/admin/app/models/org_node.py` — NEW
- `services/admin/app/models/role_assignment.py` — NEW
- `services/admin/app/routers/nodes.py` — NEW
- `services/admin/app/routers/unified_auth.py` — replace `_can_manage_*` with `can_access()` + `require_node_role()`; update session payload
- `services/admin/app/routers/areas.py`, `units.py`, `teams.py` — DELETE
- `services/admin/app/main.py` — swap router imports; add root-node bootstrap in lifespan
- `services/admin/migrations/versions/0025_organization_nodes.py` — NEW

**Frontend:**
- `apps/admin/app/admin/layout.tsx` — remove Areas/Units/Teams nav
- `apps/admin/app/admin/org/page.tsx` — refactor to use `/nodes/tree`
- `apps/admin/app/admin/nodes/[id]/page.tsx` — NEW
- `apps/admin/app/admin/nodes/[id]/_components/` — NEW (3 panel components)
- `apps/admin/app/admin/_components/Breadcrumb.tsx` — NEW
- `apps/admin/app/admin/_components/OrgTree.tsx` — NEW (extracted)
- `apps/admin/app/admin/_components/ResourceTable.tsx` — NEW
- `apps/admin/app/admin/areas/`, `units/`, `teams/` — DELETE

---

## 6. Verification

1. **Arbitrary depth** — Create 5-level hierarchy; breadcrumb shows all ancestors; deleting a middle node cascades all descendants.
2. **Permission inheritance** — User in group with `area_owner` on Platform can manage LIFT (3 levels below) without explicit grant.
3. **Permission boundary** — `team_admin` on LIFT gets 403 on sibling node Hosting.
4. **Budget rollup** — Spend on two child nodes appears in parent's budget panel.
5. **Policy override** — Parent sets `rate_limit_rpm=200`; child overrides to 50; child members see 50.
6. **Entra assign** — Assign group to node; log in as group member via Dex; confirm access to that node and children, blocked on sibling.
7. **Dev escape hatch** — `ENVIRONMENT=development` bcrypt login → platform_admin session. `ENVIRONMENT=production` → no such session.
