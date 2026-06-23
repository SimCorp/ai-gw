# Path-Based Permission Model Guide

Deep dive into how permissions work in the AI Gateway. This guide explains the mental model, implementation, and common patterns.

## Core Concepts

### Organization as a Tree

The org structure is a strict tree (no cycles, single parent per node):

```
SimCorp (root)
├── Platform (area)
│   ├── Infrastructure (unit)
│   │   └── Lift (team)
│   │       ├── Alice (engineer)
│   │       └── Bob (reporter)
│   └── DevTools (unit)
│       └── CLI (team)
└── Science (area)
    ├── ML Platform (unit)
    │   └── Training (team)
    └── Data (unit)
        └── Pipelines (team)
```

Each node has a **materialized path** that encodes its ancestry:

```
Platform:           /root-id/platform-id
Infrastructure:     /root-id/platform-id/infra-id
Lift:               /root-id/platform-id/infra-id/lift-id
Training:           /root-id/science-id/ml-id/training-id
```

### Roles and Power Levels

Roles form a **power hierarchy** (higher number = more power):

```
gateway_admin (6) ─── System-wide access
      ↓
area_owner (5)     ─── Manage an area and all descendants
      ↓
unit_lead (4)      ─── Lead a unit
      ↓
team_admin (3)     ─── Administer a team
      ↓
engineer (2)       ─── Engineer access
      ↓
reporter (1)       ─── Read-only
```

A higher power level automatically grants all permissions of lower levels.

### Permission Grants

Permissions are granted via **Entra groups → role → node**:

```
Entra Group                         Role             Node
────────────────────────────────    ──────────────   ────────
platform-admins@simcorp.com    →    gateway_admin   →  /root
area-owners-platform@corp      →    area_owner      →  /root/platform
lift-team-admins@corp          →    team_admin      →  /root/platform/infra/lift
```

When a user logs in via OIDC:
1. Extract their Entra group GUIDs from the ID token
2. Query `role_assignments` for matching entries
3. For each match, build a role entry with node path and name
4. Store all roles in the session payload

---

## Permission Check Algorithm

The fundamental check:

```python
def can_access(user: dict, target_path: str, min_role: str) -> bool:
    """
    Can the user access target_path with at least min_role privilege?
    
    Returns True if ANY of the user's roles:
    1. Has a node_path that is a prefix of target_path, AND
    2. Has role power >= min_role power
    """
    required_power = _ROLE_POWER.get(min_role, 0)
    
    for role_entry in user.get("roles", []):
        node_path = role_entry.get("node_path", "")
        role = role_entry.get("role", "")
        role_power = _ROLE_POWER.get(role, 0)
        
        # Check if this role's node is an ancestor
        if node_path and target_path.startswith(node_path):
            # Check if role power is sufficient
            if role_power >= required_power:
                return True
    
    return False
```

**Key insight:** This is pure Python, no database queries. It runs in microseconds.

---

## Examples

### Example 1: Alice is Area Owner

**Alice's session payload:**
```json
{
  "user_id": "alice-uuid",
  "email": "alice@simcorp.com",
  "roles": [
    {
      "role": "area_owner",
      "node_path": "/root-id/platform-id",
      "node_id": "platform-id",
      "node_name": "Platform"
    }
  ]
}
```

**Alice's effective permissions:**

| Target Path | Check | Min Role | Result |
|-------------|-------|----------|--------|
| `/root-id/platform-id` | area_owner >= team_admin? | team_admin | ✓ Yes |
| `/root-id/platform-id` | area_owner >= reporter? | reporter | ✓ Yes |
| `/root-id/platform-id/infra-id/lift-id` | path matches? → area_owner >= engineer? | engineer | ✓ Yes |
| `/root-id/platform-id/infra-id/lift-id` | path matches? → area_owner >= area_owner? | area_owner | ✓ Yes |
| `/root-id/science-id` | path matches (`/root-id/platform-id` not prefix of `/root-id/science-id`) | reporter | ✗ No |
| `/root-id` | path matches (`/root-id` not prefix of `/root-id/platform-id` but includes it) | gateway_admin | ✗ No |

**Interpretation:**
- Alice can view and manage anything under Platform (area)
- Alice can grant roles up to area_owner (her own power level)
- Alice cannot access Science or Root

---

### Example 2: Bob is Engineer on a Specific Team

**Bob's session payload:**
```json
{
  "user_id": "bob-uuid",
  "email": "bob@simcorp.com",
  "roles": [
    {
      "role": "engineer",
      "node_path": "/root-id/platform-id/infra-id/lift-id",
      "node_id": "lift-id",
      "node_name": "Lift"
    }
  ]
}
```

**Bob's effective permissions:**

| Target Path | Min Role | Result | Why |
|-------------|----------|--------|-----|
| `/root-id/platform-id/infra-id/lift-id` | reporter | ✓ Yes | engineer >= reporter, path matches |
| `/root-id/platform-id/infra-id/lift-id` | engineer | ✓ Yes | engineer >= engineer, path matches |
| `/root-id/platform-id/infra-id/lift-id` | team_admin | ✗ No | engineer < team_admin |
| `/root-id/platform-id/infra-id` | reporter | ✗ No | Path doesn't start with role's node_path |
| `/root-id/platform-id/infra-id/lift-id/sub-team` | engineer | ✓ Yes | Path starts with `/root-id/.../lift-id`, engineer >= engineer |

**Interpretation:**
- Bob can view and access his team (Lift)
- Bob can read anything under Lift (due to hierarchical permissions)
- Bob cannot create teams, manage budget, grant permissions (engineer < team_admin)
- Bob cannot access sibling or parent teams

---

### Example 3: Charlie has Multiple Roles

**Charlie's session payload:**
```json
{
  "user_id": "charlie-uuid",
  "email": "charlie@simcorp.com",
  "roles": [
    {
      "role": "team_admin",
      "node_path": "/root-id/platform-id/infra-id/lift-id",
      "node_id": "lift-id",
      "node_name": "Lift"
    },
    {
      "role": "engineer",
      "node_path": "/root-id/science-id/ml-id/training-id",
      "node_id": "training-id",
      "node_name": "Training"
    }
  ]
}
```

**Charlie's effective permissions:**

| Target Path | Min Role | Result | Which Role Grants It |
|-------------|----------|--------|---------------------|
| `/root-id/platform-id/infra-id/lift-id` | team_admin | ✓ Yes | Lift team_admin |
| `/root-id/science-id/ml-id/training-id` | engineer | ✓ Yes | Training engineer |
| `/root-id/platform-id/infra-id/lift-id` | engineer | ✓ Yes | Lift team_admin (>= engineer) |
| `/root-id/science-id/ml-id/training-id` | team_admin | ✗ No | Only engineer there |
| `/root-id` | reporter | ✗ No | No roles at root |

**Interpretation:**
- Charlie can admin the Lift team
- Charlie can develop on the Training team
- Charlie cannot cross-manage: he's an engineer on Training, not admin
- The check uses `ANY`, so Charlie only needs ONE matching role to succeed

---

## API Usage: Permission Checks

### Creating a Node

**Requirement:** User must have `team_admin` on the parent, or `gateway_admin` at root.

```python
@router.post("/nodes")
async def create_node(
    body: CreateNodeRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if body.parent_id:
        parent = get_node(body.parent_id)
        if not can_access(current_user, parent.path, "team_admin"):
            raise HTTPException(403, "Insufficient permissions to create child node here")
    else:
        if not can_access(current_user, "/", "gateway_admin"):
            raise HTTPException(403, "Only gateway admins can create root-level nodes")
```

**Example Scenario:**
- Alice is area_owner at `/platform` (power 5)
- She wants to create a team under `/platform/infra`
- Check: `can_access(alice, "/platform/infra", "team_admin")`
  - Alice's role: area_owner (5) >= team_admin (3)? YES
  - Path matches: `/platform/infra` starts with `/platform`? YES
  - Result: ✓ Allowed

### Updating Budget

**Requirement:** `area_owner` on the node.

```python
@router.put("/nodes/{node_id}/budget")
async def set_budget(
    node_id: str,
    body: SetBudgetRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    node = get_node(node_id)
    if not can_access(current_user, node.path, "area_owner"):
        raise HTTPException(403, "Insufficient permissions")
```

**Example Scenario:**
- Bob is team_admin at `/platform/infra/lift` (power 3)
- He tries to set budget on the Lift team
- Check: `can_access(bob, "/platform/infra/lift", "area_owner")`
  - Bob's role: team_admin (3) >= area_owner (5)? NO
  - Result: ✗ Forbidden (403)

### Viewing a Node

**Requirement:** `reporter` (anyone with any role on the node or ancestors).

```python
@router.get("/nodes/{node_id}")
async def get_node(
    node_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    node = get_node(node_id)
    if not can_access(current_user, node.path, "reporter"):
        raise HTTPException(403, "Insufficient permissions")
```

**Example Scenario:**
- Carol is engineer at `/platform/infra/lift` (power 2)
- She wants to view the Lift team
- Check: `can_access(carol, "/platform/infra/lift", "reporter")`
  - Carol's role: engineer (2) >= reporter (1)? YES
  - Path matches: YES
  - Result: ✓ Allowed

---

## Common Patterns

### Pattern 1: Granting Permissions

Only `area_owner` or higher can grant roles on a node.

```python
@router.post("/nodes/{node_id}/permissions")
async def add_permission(
    node_id: str,
    body: AddPermissionRequest,
    current_user: dict = Depends(get_current_user),
    ...
):
    node = get_node(node_id)
    if not can_access(current_user, node.path, "area_owner"):
        raise HTTPException(403, "Only area_owner+ can grant permissions")
```

**Implication:** A team_admin cannot grant permissions; they need area_owner.

### Pattern 2: Admin Dashboard with Subtree Rollup

Fetch all descendant nodes and aggregate spend:

```python
# Get all descendants of a node
def get_descendants(node: OrganizationNode) -> List[OrganizationNode]:
    return db.query(OrganizationNode)\
        .filter(OrganizationNode.path.like(node.path + "/%"))\
        .all()

# Frontend renders tree recursively
# API returns subtree spend via:
#   SELECT SUM(cost_usd) FROM cost_records
#   JOIN organization_nodes ON cost_records.node_id = org_nodes.id
#   WHERE org_nodes.path LIKE parent_path || '/%'
```

### Pattern 3: Cross-Team Dashboard (Multiple Roles)

A user with roles on multiple teams sees all of them:

```python
# Session has: roles = [
#   {role: "team_admin", node_path: "/root/platform/infra/lift", ...},
#   {role: "engineer", node_path: "/root/science/ml/training", ...}
# ]

# Frontend query:
GET /nodes/tree
# Backend returns full tree; frontend filters nodes user can access

# In frontend JavaScript:
const canAccessNode = (user, nodePath) => {
  return user.roles.some(r => 
    nodePath.startsWith(r.node_path)
  );
};

const visibleNodes = allNodes.filter(n => canAccessNode(currentUser, n.path));
```

---

## Debugging Permission Issues

### Problem: User Gets 403 Accessing a Node

**Diagnosis:**
```bash
# Get user's session
curl https://dev.aigw.scdom.net/auth/me \
  -H "Authorization: Bearer $TOKEN" | jq '.roles'

# Check the node's path
curl https://dev.aigw.scdom.net/api/admin/nodes/{id} \
  -H "Authorization: Bearer $TOKEN" | jq '.path'

# Manually run the check
node_path = "/root-id/platform-id/infra-id/lift-id"
user_roles = [{role: "engineer", node_path: "/root-id/platform-id"}]

# Does any role match?
user_roles.some(r => node_path.startsWith(r.node_path))
# False! Engineer is at /platform, not /platform/infra/lift
```

**Solution:** User's role is too high in the tree. They need a role closer to the target node.

### Problem: User Can't Grant Permissions

**Diagnosis:**
```bash
# Check user's power level
User has: team_admin (power 3)
Endpoint requires: area_owner (power 5)

# team_admin (3) >= area_owner (5)? FALSE
```

**Solution:** Promote user to area_owner role, or have an area_owner grant the permission.

### Problem: Unexpected Permission Inheritance

**Diagnosis:**
```
Parent node: /root/area (user has area_owner)
Child node: /root/area/unit/team

Can user access /root/area/unit/team with reporter?
YES, because:
  - /root/area/unit/team starts with /root/area
  - area_owner (5) >= reporter (1)
```

**This is correct behavior!** area_owner gets all permissions on descendants.

---

## Migration from Flat Roles to Path-Based

If migrating from a flat role model (everyone is either "admin" or "user"):

1. **Identify scope:** Was each role tied to a resource ID?
   ```
   v1: user_roles = [(alice, "admin", "team", team-123)]
   v2: alice has area_owner at /root/.../team-123
   ```

2. **Map roles to power levels:**
   ```
   v1 "admin" (any scope) → v2 gateway_admin (root)
   v1 "manager" (team scope) → v2 team_admin (node)
   v1 "developer" → v2 engineer (node)
   ```

3. **Test permission checks:**
   ```python
   # Old check
   if user_role == "admin" or user_role == "manager":
       return True
   
   # New check
   return can_access(user, node_path, "team_admin")
   ```

---

## Performance Notes

**can_access() is O(n·m) where:**
- n = number of roles the user has (typically 1-5)
- m = length of target path (typically 3-10 segments)

Since path matching is simple string prefix checking, this is extremely fast (<1µs).

**No database queries!** All data is in the session payload.

---

## Best Practices

1. **Always check permissions at the API level.** Don't rely on frontend-only checks.
2. **Use can_access() for authorization, not for display.** Frontend can use roles for UI hints.
3. **Grant the minimum role needed.** team_admin doesn't need area_owner.
4. **Test cross-team scenarios.** Users often have multiple roles.
5. **Audit permission grants.** Log who granted which role on which node.
6. **Validate role names server-side.** Don't trust client-provided role strings.

---

## Questions

See `docs/api/nodes.md` for endpoint reference and required permissions per operation.
