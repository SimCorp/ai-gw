# Organization Nodes API Reference

Enterprise-grade API for managing the hierarchical organization structure. All requests require Bearer token authentication via the `Authorization` header.

## Overview

The Nodes API replaces the legacy Areas/Units/Teams endpoints with a unified, path-based tree structure. Each node represents an organizational unit (root, area, unit, team, etc.) and can have budget controls, policy settings, member management, and fine-grained role-based access.

## Authentication & Authorization

All endpoints require:
- **Header**: `Authorization: Bearer {session_token}`
- **Permission Model**: `can_access(user, node_path, min_role)`

The user's access is determined by their roles on ancestor nodes. A user with `area_owner` role at path `/root-id/area-id/` automatically has access to all descendants like `/root-id/area-id/unit-id/team-id`.

## Endpoints

### List Nodes

```
GET /nodes
```

List organization nodes with optional filtering.

**Query Parameters:**
- `parent_id` (string, optional): Filter by parent node ID
- `type` (string, optional): Filter by node type (e.g., `area`, `unit`, `team`)
- `search` (string, optional): Search by name or slug (case-insensitive substring match)
- `limit` (integer, default=50, max=500): Pagination limit
- `offset` (integer, default=0): Pagination offset

**Response:** Array of node objects
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Platform Engineering",
    "slug": "platform-engineering",
    "type": "area",
    "parent_id": "550e8400-e29b-41d4-a716-446655440001",
    "path": "/550e8400-e29b-41d4-a716-446655440001/550e8400-e29b-41d4-a716-446655440000",
    "color": "#FF5733",
    "description": "Core platform infrastructure team",
    "location": "San Francisco, CA",
    "monthly_budget_usd": 50000.00,
    "budget_alert_threshold": 0.80,
    "created_at": "2024-01-15T10:30:00Z"
  }
]
```

**Required Permission:** `reporter` (any role) on the node or ancestor

---

### Get Organization Tree

```
GET /nodes/tree
```

Retrieve the full organization tree as nested JSON, ordered by materialized path.

**Response:** Array of root nodes with nested children
```json
[
  {
    "id": "root-uuid",
    "name": "SimCorp",
    "slug": "root",
    "type": "root",
    "parent_id": null,
    "path": "/root-uuid",
    "color": null,
    "description": null,
    "location": null,
    "monthly_budget_usd": null,
    "budget_alert_threshold": null,
    "created_at": "2024-01-01T00:00:00Z",
    "children": [
      {
        "id": "area-uuid",
        "name": "Platform",
        "slug": "platform",
        "type": "area",
        "parent_id": "root-uuid",
        "path": "/root-uuid/area-uuid",
        "children": [
          {
            "id": "unit-uuid",
            "name": "Infrastructure",
            "slug": "infrastructure",
            "type": "unit",
            "parent_id": "area-uuid",
            "path": "/root-uuid/area-uuid/unit-uuid",
            "children": []
          }
        ]
      }
    ]
  }
]
```

**Required Permission:** `reporter` (any role)

---

### Create Node

```
POST /nodes
```

Create a new organization node. Root-level nodes require `gateway_admin`; child nodes require `team_admin` on the parent.

**Request Body:**
```json
{
  "name": "Platform Lift",
  "type": "team",
  "parent_id": "area-uuid",
  "color": "#FF5733",
  "description": "Vertical scaling for core platform",
  "location": "San Francisco, CA"
}
```

**Request Fields:**
- `name` (string, required): Node name
- `type` (string, optional, default=`team`): Node type (e.g., `area`, `unit`, `team`)
- `parent_id` (string, optional): Parent node UUID (omit for root-level)
- `color` (string, optional): Hex color code for UI
- `description` (string, optional): Node description
- `location` (string, optional): Physical location

**Response:** Node object (see List Nodes example)

**Status Code:** 201 Created

**Required Permission:**
- `gateway_admin` at `/` for root-level nodes
- `team_admin` on the parent node for child nodes

---

### Get Node Detail

```
GET /nodes/{node_id}
```

Retrieve a single node with parent, children, member count, and month-to-date spend.

**Path Parameters:**
- `node_id` (string, required): Node UUID

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Platform Engineering",
  "slug": "platform-engineering",
  "type": "area",
  "parent_id": "550e8400-e29b-41d4-a716-446655440001",
  "path": "/550e8400-e29b-41d4-a716-446655440001/550e8400-e29b-41d4-a716-446655440000",
  "color": "#FF5733",
  "description": "Core platform infrastructure",
  "location": "San Francisco, CA",
  "monthly_budget_usd": 50000.00,
  "budget_alert_threshold": 0.80,
  "created_at": "2024-01-15T10:30:00Z",
  "parent": {
    "id": "550e8400-e29b-41d4-a716-446655440001",
    "name": "Root",
    "slug": "root",
    "type": "root",
    "parent_id": null,
    "path": "/550e8400-e29b-41d4-a716-446655440001"
  },
  "children": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440002",
      "name": "Lift",
      "slug": "lift",
      "type": "team",
      "parent_id": "550e8400-e29b-41d4-a716-446655440000",
      "path": "/550e8400-e29b-41d4-a716-446655440001/550e8400-e29b-41d4-a716-446655440000/550e8400-e29b-41d4-a716-446655440002"
    }
  ],
  "member_count": 12,
  "spend_mtd": 35421.67
}
```

**Required Permission:** `reporter` on the node

---

### Update Node

```
PUT /nodes/{node_id}
```

Update node metadata. Does not modify budget, policy, or permissions.

**Path Parameters:**
- `node_id` (string, required): Node UUID

**Request Body:**
```json
{
  "name": "Platform Engineering (Updated)",
  "type": "area",
  "color": "#00FF00",
  "description": "Updated description",
  "location": "New York, NY"
}
```

**Request Fields:** All optional
- `name` (string): Update node name (slug auto-generated)
- `type` (string): Update node type
- `color` (string): Update color
- `description` (string): Update description
- `location` (string): Update location

**Response:** Updated node object

**Status Code:** 200 OK

**Required Permission:** `team_admin` on the node

---

### Delete Node

```
DELETE /nodes/{node_id}
```

Delete a node and all descendants. Root nodes cannot be deleted.

**Path Parameters:**
- `node_id` (string, required): Node UUID

**Status Code:** 204 No Content

**Required Permission:** `area_owner` on the node

---

### Get Node Ancestry

```
GET /nodes/{node_id}/ancestry
```

Retrieve the breadcrumb path (all ancestors) for a node, ordered root-first.

**Path Parameters:**
- `node_id` (string, required): Node UUID

**Response:** Ordered array of ancestor nodes
```json
[
  {
    "id": "root-uuid",
    "name": "SimCorp",
    "slug": "root",
    "type": "root",
    "path": "/root-uuid"
  },
  {
    "id": "area-uuid",
    "name": "Platform",
    "slug": "platform",
    "type": "area",
    "path": "/root-uuid/area-uuid"
  },
  {
    "id": "unit-uuid",
    "name": "Infrastructure",
    "slug": "infrastructure",
    "type": "unit",
    "path": "/root-uuid/area-uuid/unit-uuid"
  }
]
```

**Required Permission:** `reporter` on the node

---

### Get Node Children

```
GET /nodes/{node_id}/children
```

List direct children of a node.

**Path Parameters:**
- `node_id` (string, required): Node UUID

**Response:** Array of child nodes (same schema as List Nodes)

**Required Permission:** `reporter` on the node

---

## Members

### List Node Members

```
GET /nodes/{node_id}/members
```

List all team members directly assigned to this node.

**Path Parameters:**
- `node_id` (string, required): Node UUID

**Query Parameters:**
- `limit` (integer, default=50, max=500): Pagination limit
- `offset` (integer, default=0): Pagination offset

**Response:**
```json
[
  {
    "id": "member-uuid",
    "node_id": "node-uuid",
    "user_id": "user-uuid",
    "role": "team_admin",
    "email": "alice@simcorp.com",
    "display_name": "Alice Smith",
    "created_at": "2024-01-15T10:30:00Z"
  }
]
```

**Required Permission:** `reporter` on the node

---

### Add Node Member

```
POST /nodes/{node_id}/members
```

Add a user to the node's member list.

**Path Parameters:**
- `node_id` (string, required): Node UUID

**Request Body:**
```json
{
  "user_id": "user-uuid"
}
```

**Response:**
```json
{
  "ok": true
}
```

**Status Code:** 201 Created

**Required Permission:** `team_admin` on the node

---

### Remove Node Member

```
DELETE /nodes/{node_id}/members/{user_id}
```

Remove a user from the node's member list.

**Path Parameters:**
- `node_id` (string, required): Node UUID
- `user_id` (string, required): User UUID

**Status Code:** 204 No Content

**Required Permission:** `team_admin` on the node

---

## Policy

### Get Node Policy

```
GET /nodes/{node_id}/policy
```

Retrieve the node's policy settings, including inherited values from ancestors.

**Path Parameters:**
- `node_id` (string, required): Node UUID

**Response:**
```json
{
  "explicit": {
    "cache_ttl_seconds": 3600,
    "cache_similarity_threshold": 0.85,
    "cache_opt_out": false,
    "embedding_model": "text-embedding-3-small",
    "rate_limit_rpm": 600,
    "allowed_models": ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"]
  },
  "inherited": [
    {
      "source_node_id": "area-uuid",
      "source_name": "Platform",
      "cache_ttl_seconds": 7200,
      "cache_similarity_threshold": 0.80,
      "cache_opt_out": null,
      "embedding_model": null,
      "rate_limit_rpm": 1000,
      "allowed_models": null
    }
  ]
}
```

**Required Permission:** `reporter` on the node

---

### Set Node Policy

```
PUT /nodes/{node_id}/policy
```

Update the node's explicit policy settings. Unset fields revert to inheritance.

**Path Parameters:**
- `node_id` (string, required): Node UUID

**Request Body:**
```json
{
  "cache_ttl_seconds": 3600,
  "cache_similarity_threshold": 0.85,
  "cache_opt_out": false,
  "embedding_model": "text-embedding-3-small",
  "rate_limit_rpm": 600,
  "allowed_models": ["gpt-4", "gpt-3.5-turbo"]
}
```

**Request Fields:** All optional
- `cache_ttl_seconds` (integer): Cache TTL in seconds
- `cache_similarity_threshold` (float 0-1): Semantic cache threshold
- `cache_opt_out` (boolean): Disable caching for this node
- `embedding_model` (string): Embedding model ID
- `rate_limit_rpm` (integer): Requests per minute limit
- `allowed_models` (array of strings): Whitelisted model IDs

**Response:**
```json
{
  "ok": true
}
```

**Status Code:** 200 OK

**Required Permission:** `team_admin` on the node

---

## Budget

### Get Node Budget

```
GET /nodes/{node_id}/budget
```

Retrieve budget allocation and spend tracking for the node and its subtree.

**Path Parameters:**
- `node_id` (string, required): Node UUID

**Response:**
```json
{
  "node_id": "node-uuid",
  "budget_usd": 50000.00,
  "spend_mtd": 35421.67,
  "spend_own_mtd": 12345.67,
  "spend_children_mtd": 23076.00,
  "pct_used": 0.7084,
  "parent_budget": 100000.00,
  "alert_threshold": 0.80
}
```

**Response Fields:**
- `budget_usd`: Monthly budget allocated to this node
- `spend_mtd`: Total month-to-date spend (node + all descendants)
- `spend_own_mtd`: Spend attributed directly to this node (not children)
- `spend_children_mtd`: Spend from all child nodes
- `pct_used`: Percentage of budget spent (spend_mtd / budget_usd)
- `parent_budget`: Parent node's budget (for comparison)
- `alert_threshold`: Threshold at which to alert (default 0.80 = 80%)

**Required Permission:** `reporter` on the node

---

### Set Node Budget

```
PUT /nodes/{node_id}/budget
```

Update the node's monthly budget allocation and alert threshold.

**Path Parameters:**
- `node_id` (string, required): Node UUID

**Request Body:**
```json
{
  "monthly_budget_usd": 75000.00,
  "budget_alert_threshold": 0.85
}
```

**Request Fields:** Both optional
- `monthly_budget_usd` (float): New monthly budget
- `budget_alert_threshold` (float 0-1): Alert threshold (e.g., 0.80 for 80%)

**Validation:**
- Child node budget cannot exceed parent budget
- Threshold should be 0-1 (0% to 100%)

**Response:**
```json
{
  "ok": true
}
```

**Status Code:** 200 OK

**Required Permission:** `area_owner` on the node

---

## Permissions

### List Node Permissions

```
GET /nodes/{node_id}/permissions
```

List all Entra groups and their role assignments on this node.

**Path Parameters:**
- `node_id` (string, required): Node UUID

**Response:**
```json
[
  {
    "id": "assignment-uuid",
    "entra_group_id": "12345678-1234-1234-1234-123456789012",
    "entra_group_name": "platform-admins@simcorp.com",
    "role": "area_owner",
    "node_id": "node-uuid",
    "granted_at": "2024-01-15T10:30:00Z",
    "granted_by": "admin-user-uuid",
    "granted_by_email": "admin@simcorp.com"
  }
]
```

**Required Permission:** `team_admin` on the node

---

### Add Permission

```
POST /nodes/{node_id}/permissions
```

Grant a role on this node to **either** an Entra/local group **or** a single user.

**Path Parameters:**
- `node_id` (string, required): Node UUID

**Request Body (group grant):**
```json
{
  "entra_group_id": "12345678-1234-1234-1234-123456789012",
  "entra_group_name": "platform-admins@simcorp.com",
  "role": "area_owner"
}
```

**Request Body (direct user grant):**
```json
{
  "user_id": "00000000-0000-0000-0000-000000000001",
  "role": "engineer"
}
```

**Request Fields:**
- `entra_group_id` (string): Entra/local group id (a local group's id is `lcl-<uuid>`)
- `entra_group_name` (string, optional): Human-readable group name
- `user_id` (string): User UUID, for a direct (non-group) grant
- `role` (string, required): One of: `gateway_admin`, `area_owner`, `unit_lead`, `team_admin`, `engineer`, `reporter`

Exactly **one** of `entra_group_id` or `user_id` must be supplied — providing both, or
neither, returns **422**.

**Response:**
```json
{
  "ok": true,
  "id": "assignment-uuid"
}
```

**Status Code:** 201 Created

**Required Permission:** `area_owner` on the node

---

### Remove Permission

```
DELETE /nodes/{node_id}/permissions/{assignment_id}
```

Revoke a role assignment from this node.

**Path Parameters:**
- `node_id` (string, required): Node UUID
- `assignment_id` (string, required): Role assignment UUID

**Status Code:** 204 No Content

**Required Permission:** `area_owner` on the node

---

## Error Responses

All error responses follow this format:

```json
{
  "detail": "Error message"
}
```

**Common Status Codes:**
- `400 Bad Request`: Invalid parameters or constraint violation
- `401 Unauthorized`: Missing or invalid authentication token
- `403 Forbidden`: User lacks required permissions
- `404 Not Found`: Resource not found
- `409 Conflict`: Resource already exists
- `422 Unprocessable Entity`: Validation error
- `429 Too Many Requests`: Rate limited
- `500 Internal Server Error`: Server error
