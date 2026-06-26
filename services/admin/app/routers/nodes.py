"""
Unified organization nodes router.

Replaces /areas, /units, /teams with a single /nodes surface backed by the
organization_nodes materialized-path tree.

All endpoints require a valid session (supplied via the _auth dependency at
include_router call-site in main.py). Permission checks use can_access() /
require_node_role() from unified_auth.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.routers.unified_auth import (
    _ROLE_POWER,
    can_access,
    get_current_user,
    max_role_power,
)

router = APIRouter(prefix="/nodes", tags=["nodes"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


async def _get_node_row(session: AsyncSession, node_id: str) -> Any:
    row = (
        (
            await session.execute(
                text(
                    "SELECT id, name, slug, type, parent_id, path, color, description, location, "
                    "monthly_budget_usd, budget_alert_threshold, created_at "
                    "FROM organization_nodes WHERE id = CAST(:nid AS uuid)"
                ),
                {"nid": node_id},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise HTTPException(404, "Node not found")
    return row


def _node_to_dict(row: Any) -> dict:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "slug": row["slug"],
        "type": row["type"],
        "parent_id": str(row["parent_id"]) if row["parent_id"] else None,
        "path": row["path"],
        "color": row["color"],
        "description": row["description"],
        "location": row["location"],
        "monthly_budget_usd": (
            float(row["monthly_budget_usd"]) if row["monthly_budget_usd"] is not None else None
        ),
        "budget_alert_threshold": (
            float(row["budget_alert_threshold"])
            if row["budget_alert_threshold"] is not None
            else None
        ),
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


# ---------------------------------------------------------------------------
# Root node bootstrap (called from lifespan in main.py)
# ---------------------------------------------------------------------------


async def ensure_root_node(session: AsyncSession) -> dict:
    row = (
        await session.execute(
            text("SELECT id, path FROM organization_nodes WHERE parent_id IS NULL LIMIT 1")
        )
    ).first()
    if row:
        return {"id": str(row[0]), "path": row[1]}
    root_id = str(uuid.uuid4())
    path = f"/{root_id}"
    await session.execute(
        text("""
            INSERT INTO organization_nodes (id, name, slug, type, path)
            VALUES (CAST(:id AS uuid), 'SimCorp', 'root', 'root', :path)
        """),
        {"id": root_id, "path": path},
    )
    await session.commit()
    result = (
        await session.execute(
            text("SELECT id, path FROM organization_nodes WHERE id = CAST(:id AS uuid)"),
            {"id": root_id},
        )
    ).first()
    return {"id": str(result[0]), "path": result[1]}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CreateNodeRequest(BaseModel):
    name: str
    type: str = "team"
    parent_id: str | None = None
    color: str | None = None
    description: str | None = None
    location: str | None = None


class UpdateNodeRequest(BaseModel):
    name: str | None = None
    type: str | None = None
    color: str | None = None
    description: str | None = None
    location: str | None = None


class AddMemberRequest(BaseModel):
    user_id: str


class SetPolicyRequest(BaseModel):
    cache_ttl_seconds: int | None = None
    cache_similarity_threshold: float | None = None
    cache_opt_out: bool | None = None
    embedding_model: str | None = None
    rate_limit_rpm: int | None = None
    allowed_models: list[str] | None = None


class SetBudgetRequest(BaseModel):
    monthly_budget_usd: float | None = None
    budget_alert_threshold: float | None = None


class AddPermissionRequest(BaseModel):
    entra_group_id: str | None = None
    entra_group_name: str | None = None
    user_id: str | None = None
    role: str


# ---------------------------------------------------------------------------
# List / search
# ---------------------------------------------------------------------------


@router.get("")
async def list_nodes(
    parent_id: str | None = Query(default=None),
    type: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    conditions = ["1=1"]
    params: dict = {"limit": limit, "offset": offset}

    if parent_id:
        conditions.append("parent_id = CAST(:parent_id AS uuid)")
        params["parent_id"] = parent_id
    if type:
        conditions.append("type = :type")
        params["type"] = type
    if search:
        conditions.append("(name ILIKE :search OR slug ILIKE :search)")
        params["search"] = f"%{search}%"

    where = " AND ".join(conditions)
    rows = (
        (
            await session.execute(
                text(f"""
            SELECT id, name, slug, type, parent_id, path, color, description, location,
                   monthly_budget_usd, budget_alert_threshold, created_at
            FROM organization_nodes
            WHERE {where}
            ORDER BY path
            LIMIT :limit OFFSET :offset
        """),
                params,
            )
        )
        .mappings()
        .all()
    )
    return [_node_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Tree
# ---------------------------------------------------------------------------


@router.get("/tree")
async def get_tree(
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Return full org tree as nested JSON, ordered by path."""
    rows = (
        (
            await session.execute(
                text("""
            SELECT id, name, slug, type, parent_id, path, color, description, location,
                   monthly_budget_usd, budget_alert_threshold, created_at
            FROM organization_nodes
            ORDER BY path
        """)
            )
        )
        .mappings()
        .all()
    )

    # Build nested tree from flat path-ordered list
    nodes_by_id: dict[str, dict] = {}
    roots: list[dict] = []

    for row in rows:
        node = _node_to_dict(row)
        node["children"] = []
        nodes_by_id[node["id"]] = node

    for row in rows:
        node = nodes_by_id[str(row["id"])]
        if row["parent_id"] is None:
            roots.append(node)
        else:
            parent = nodes_by_id.get(str(row["parent_id"]))
            if parent:
                parent["children"].append(node)

    return roots


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
async def create_node(
    body: CreateNodeRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    # Determine parent path for permission check
    if body.parent_id:
        parent_row = (
            await session.execute(
                text("SELECT id, path FROM organization_nodes WHERE id = CAST(:pid AS uuid)"),
                {"pid": body.parent_id},
            )
        ).first()
        if not parent_row:
            raise HTTPException(404, "Parent node not found")
        parent_path = parent_row[1]
        if not can_access(current_user, parent_path, "team_admin"):
            raise HTTPException(403, "Insufficient permissions to create child node here")
    else:
        # Creating a root-level node requires platform_admin
        if not can_access(current_user, "/", "platform_admin"):
            raise HTTPException(403, "Only platform admins can create root-level nodes")

    slug = _slugify(body.name)
    node_id = str(uuid.uuid4())

    if body.parent_id:
        path = f"{parent_path}/{node_id}"
    else:
        path = f"/{node_id}"

    await session.execute(
        text("""
            INSERT INTO organization_nodes
                (id, name, slug, type, parent_id, path, color, description, location)
            VALUES
                (CAST(:id AS uuid), :name, :slug, :type,
                 CAST(:parent_id AS uuid), :path, :color, :description, :location)
        """),
        {
            "id": node_id,
            "name": body.name,
            "slug": slug,
            "type": body.type,
            "parent_id": body.parent_id,
            "path": path,
            "color": body.color,
            "description": body.description,
            "location": body.location,
        },
    )
    from app import audit

    await audit.record(
        session,
        request,
        "create_node",
        "node",
        resource_id=node_id,
        details={"name": body.name, "type": body.type, "parent_id": body.parent_id},
    )
    await session.commit()
    row = await _get_node_row(session, node_id)
    return _node_to_dict(row)


# ---------------------------------------------------------------------------
# Get detail
# ---------------------------------------------------------------------------


@router.get("/{node_id}")
async def get_node(
    node_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await _get_node_row(session, node_id)

    if not can_access(current_user, row["path"], "viewer"):
        raise HTTPException(403, "Insufficient permissions")

    children = (
        (
            await session.execute(
                text("""
            SELECT id, name, slug, type, parent_id, path, color, description, location,
                   monthly_budget_usd, budget_alert_threshold, created_at
            FROM organization_nodes WHERE parent_id = CAST(:nid AS uuid)
            ORDER BY name
        """),
                {"nid": node_id},
            )
        )
        .mappings()
        .all()
    )

    parent = None
    if row["parent_id"]:
        parent_row = (
            (
                await session.execute(
                    text(
                        "SELECT id, name, slug, type, parent_id, path, color, description, location, "
                        "monthly_budget_usd, budget_alert_threshold, created_at "
                        "FROM organization_nodes WHERE id = CAST(:pid AS uuid)"
                    ),
                    {"pid": str(row["parent_id"])},
                )
            )
            .mappings()
            .first()
        )
        if parent_row:
            parent = _node_to_dict(parent_row)

    member_count = (
        await session.execute(
            text("SELECT COUNT(*) FROM node_members WHERE node_id = CAST(:nid AS uuid)"),
            {"nid": node_id},
        )
    ).scalar() or 0

    # MTD spend for this node only (not subtree)
    spend_mtd = (
        await session.execute(
            text("""
            SELECT COALESCE(SUM(cost_usd), 0)
            FROM cost_records
            WHERE node_id = CAST(:nid AS uuid)
              AND created_at >= date_trunc('month', NOW())
        """),
            {"nid": node_id},
        )
    ).scalar() or 0

    # Direct user role assignments on this node (for node admin / contact display)
    direct_admins_rows = (
        (
            await session.execute(
                text("""
            SELECT u.id, u.email, u.display_name, ra.role
            FROM role_assignments ra
            JOIN users u ON u.id = ra.user_id
            WHERE ra.node_id = CAST(:nid AS uuid) AND ra.user_id IS NOT NULL
            ORDER BY u.display_name, u.email
        """),
                {"nid": node_id},
            )
        )
        .mappings()
        .all()
    )

    # Inherited admins: first direct-admin on the parent node (display hint only)
    parent_direct_admins: list[dict] = []
    if row["parent_id"] and not direct_admins_rows:
        parent_da_rows = (
            (
                await session.execute(
                    text("""
                SELECT u.id, u.email, u.display_name, ra.role, pn.name AS source_node_name
                FROM role_assignments ra
                JOIN users u ON u.id = ra.user_id
                JOIN organization_nodes pn ON pn.id = ra.node_id
                WHERE ra.node_id = CAST(:pid AS uuid) AND ra.user_id IS NOT NULL
                ORDER BY u.display_name, u.email
            """),
                    {"pid": str(row["parent_id"])},
                )
            )
            .mappings()
            .all()
        )
        parent_direct_admins = [
            {
                "id": str(r["id"]),
                "email": r["email"],
                "display_name": r["display_name"] or "",
                "role": r["role"],
                "source_node_name": r["source_node_name"],
            }
            for r in parent_da_rows
        ]

    result = _node_to_dict(row)
    result["parent"] = parent
    result["children"] = [_node_to_dict(c) for c in children]
    result["member_count"] = member_count
    result["spend_mtd"] = float(spend_mtd)
    result["direct_admins"] = [
        {
            "id": str(r["id"]),
            "email": r["email"],
            "display_name": r["display_name"] or "",
            "role": r["role"],
        }
        for r in direct_admins_rows
    ]
    result["parent_direct_admins"] = parent_direct_admins
    return result


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


@router.put("/{node_id}")
async def update_node(
    node_id: str,
    body: UpdateNodeRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await _get_node_row(session, node_id)
    if not can_access(current_user, row["path"], "team_admin"):
        raise HTTPException(403, "Insufficient permissions")

    updates: dict = {}
    if body.name is not None:
        updates["name"] = body.name
        updates["slug"] = _slugify(body.name)
    if body.type is not None:
        updates["type"] = body.type
    if body.color is not None:
        updates["color"] = body.color
    if body.description is not None:
        updates["description"] = body.description
    if body.location is not None:
        updates["location"] = body.location

    if not updates:
        raise HTTPException(422, "No fields to update")

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["nid"] = node_id
    await session.execute(
        text(f"UPDATE organization_nodes SET {set_clause} WHERE id = CAST(:nid AS uuid)"),
        updates,
    )
    await session.commit()
    row = await _get_node_row(session, node_id)
    return _node_to_dict(row)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@router.delete("/{node_id}", status_code=204)
async def delete_node(
    node_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await _get_node_row(session, node_id)
    if not can_access(current_user, row["path"], "area_owner"):
        raise HTTPException(403, "Insufficient permissions")
    if row["parent_id"] is None:
        raise HTTPException(400, "Cannot delete root node")
    # CASCADE on FK handles descendants
    await session.execute(
        text("DELETE FROM organization_nodes WHERE id = CAST(:nid AS uuid)"),
        {"nid": node_id},
    )
    await session.commit()


# ---------------------------------------------------------------------------
# Ancestry (breadcrumb)
# ---------------------------------------------------------------------------


@router.get("/{node_id}/ancestry")
async def get_ancestry(
    node_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await _get_node_row(session, node_id)
    if not can_access(current_user, row["path"], "viewer"):
        raise HTTPException(403, "Insufficient permissions")

    # Extract ancestor UUIDs from path (all segments)
    parts = [p for p in row["path"].strip("/").split("/") if p]

    if not parts:
        return []

    rows = (
        (
            await session.execute(
                text("""
            SELECT id, name, slug, type, parent_id, path, color, description, location,
                   monthly_budget_usd, budget_alert_threshold, created_at
            FROM organization_nodes
            WHERE id = ANY(CAST(:ids AS uuid[]))
            ORDER BY path
        """),
                {"ids": parts},
            )
        )
        .mappings()
        .all()
    )

    return [_node_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Children
# ---------------------------------------------------------------------------


@router.get("/{node_id}/children")
async def get_children(
    node_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await _get_node_row(session, node_id)
    if not can_access(current_user, row["path"], "viewer"):
        raise HTTPException(403, "Insufficient permissions")

    children = (
        (
            await session.execute(
                text("""
            SELECT id, name, slug, type, parent_id, path, color, description, location,
                   monthly_budget_usd, budget_alert_threshold, created_at
            FROM organization_nodes
            WHERE parent_id = CAST(:nid AS uuid)
            ORDER BY name
        """),
                {"nid": node_id},
            )
        )
        .mappings()
        .all()
    )

    return [_node_to_dict(c) for c in children]


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


@router.get("/{node_id}/members")
async def list_members(
    node_id: str,
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await _get_node_row(session, node_id)
    if not can_access(current_user, row["path"], "viewer"):
        raise HTTPException(403, "Insufficient permissions")

    members = (
        (
            await session.execute(
                text("""
            SELECT nm.id, nm.node_id, nm.user_id, nm.role, nm.created_at,
                   u.email, u.display_name
            FROM node_members nm
            LEFT JOIN users u ON u.id::text = nm.user_id
            WHERE nm.node_id = CAST(:nid AS uuid)
            ORDER BY u.display_name, u.email
            LIMIT :limit OFFSET :offset
        """),
                {"nid": node_id, "limit": limit, "offset": offset},
            )
        )
        .mappings()
        .all()
    )

    return [
        {
            "id": str(m["id"]),
            "node_id": str(m["node_id"]),
            "user_id": str(m["user_id"]) if m["user_id"] else None,
            "role": m["role"],
            "email": m["email"],
            "display_name": m["display_name"],
            "created_at": m["created_at"].isoformat() if m["created_at"] else None,
        }
        for m in members
    ]


@router.post("/{node_id}/members", status_code=201)
async def add_member(
    node_id: str,
    body: AddMemberRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await _get_node_row(session, node_id)
    if not can_access(current_user, row["path"], "team_admin"):
        raise HTTPException(403, "Insufficient permissions")

    await session.execute(
        text("""
            INSERT INTO node_members (node_id, user_id)
            VALUES (CAST(:nid AS uuid), :uid)
            ON CONFLICT (node_id, user_id) DO NOTHING
        """),
        {"nid": node_id, "uid": body.user_id},
    )
    await session.commit()
    return {"ok": True}


@router.delete("/{node_id}/members/{user_id}", status_code=204)
async def remove_member(
    node_id: str,
    user_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await _get_node_row(session, node_id)
    if not can_access(current_user, row["path"], "team_admin"):
        raise HTTPException(403, "Insufficient permissions")

    await session.execute(
        text("""
            DELETE FROM node_members
            WHERE node_id = CAST(:nid AS uuid) AND user_id = :uid
        """),
        {"nid": node_id, "uid": user_id},
    )
    await session.commit()


# ---------------------------------------------------------------------------
# Policy (inherited + explicit)
# ---------------------------------------------------------------------------


@router.get("/{node_id}/policy")
async def get_policy(
    node_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await _get_node_row(session, node_id)
    if not can_access(current_user, row["path"], "viewer"):
        raise HTTPException(403, "Insufficient permissions")

    # Get all ancestor node IDs (ordered root→current by path length)
    parts = [p for p in row["path"].strip("/").split("/") if p]

    # Fetch policies for all ancestors + current node in path order
    all_ids = parts  # root first (all UUIDs from path, including current)
    policies_raw = (
        (
            await session.execute(
                text("""
            SELECT p.*, n.path AS node_path, n.name AS node_name, n.id AS node_id_col
            FROM policies p
            JOIN organization_nodes n ON n.id = p.node_id
            WHERE p.node_id = ANY(CAST(:ids AS uuid[]))
              AND p.project_id IS NULL
            ORDER BY length(n.path)
        """),
                {"ids": all_ids},
            )
        )
        .mappings()
        .all()
    )

    # Build inherited (ancestors) and explicit (current node)
    policy_fields = [
        "cache_ttl_seconds",
        "cache_similarity_threshold",
        "cache_opt_out",
        "embedding_model",
        "rate_limit_rpm",
        "allowed_models",
    ]

    inherited = []
    explicit: dict = {}

    for p in policies_raw:
        p_node_id = str(p["node_id_col"])
        is_current = p_node_id == node_id

        if is_current:
            for f in policy_fields:
                explicit[f] = p[f]
        else:
            entry: dict = {
                "source_node_id": p_node_id,
                "source_name": p["node_name"],
            }
            for f in policy_fields:
                entry[f] = p[f]
            inherited.append(entry)

    return {"explicit": explicit, "inherited": inherited}


@router.put("/{node_id}/policy")
async def set_policy(
    node_id: str,
    body: SetPolicyRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await _get_node_row(session, node_id)
    if not can_access(current_user, row["path"], "team_admin"):
        raise HTTPException(403, "Insufficient permissions")

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(422, "No fields to update")

    # Upsert policy row
    fields = list(updates.keys())
    col_list = ", ".join(fields)
    val_list = ", ".join(f":{f}" for f in fields)
    update_clause = ", ".join(f"{f} = EXCLUDED.{f}" for f in fields)

    params = {**updates, "nid": node_id}

    await session.execute(
        text(f"""
            INSERT INTO policies (node_id, {col_list}, updated_at)
            VALUES (CAST(:nid AS uuid), {val_list}, NOW())
            ON CONFLICT (node_id) WHERE project_id IS NULL
            DO UPDATE SET {update_clause}, updated_at = NOW()
        """),
        params,
    )
    await session.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------


@router.get("/{node_id}/budget")
async def get_budget(
    node_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await _get_node_row(session, node_id)
    if not can_access(current_user, row["path"], "viewer"):
        raise HTTPException(403, "Insufficient permissions")

    # Spend for this node subtree (all descendants via path LIKE)
    spend_subtree = (
        await session.execute(
            text("""
            SELECT COALESCE(SUM(cr.cost_usd), 0)
            FROM cost_records cr
            JOIN organization_nodes n ON n.id = cr.node_id
            WHERE n.path LIKE :path_prefix || '%'
              AND cr.created_at >= date_trunc('month', NOW())
        """),
            {"path_prefix": row["path"]},
        )
    ).scalar() or 0

    # Spend for direct children only (excluding current node)
    spend_children = (
        await session.execute(
            text("""
            SELECT COALESCE(SUM(cr.cost_usd), 0)
            FROM cost_records cr
            JOIN organization_nodes n ON n.id = cr.node_id
            WHERE n.path LIKE :path_prefix || '/%'
              AND cr.created_at >= date_trunc('month', NOW())
        """),
            {"path_prefix": row["path"]},
        )
    ).scalar() or 0

    # Own spend (not counting children)
    spend_own = float(spend_subtree) - float(spend_children)

    budget = float(row["monthly_budget_usd"]) if row["monthly_budget_usd"] is not None else None
    pct_used = float(spend_subtree) / budget if budget and budget > 0 else None

    # Parent budget
    parent_budget = None
    if row["parent_id"]:
        parent_budget_row = (
            await session.execute(
                text(
                    "SELECT monthly_budget_usd FROM organization_nodes WHERE id = CAST(:pid AS uuid)"
                ),
                {"pid": str(row["parent_id"])},
            )
        ).first()
        if parent_budget_row and parent_budget_row[0] is not None:
            parent_budget = float(parent_budget_row[0])

    return {
        "node_id": node_id,
        "budget_usd": budget,
        "spend_mtd": float(spend_subtree),
        "spend_own_mtd": spend_own,
        "spend_children_mtd": float(spend_children),
        "pct_used": pct_used,
        "parent_budget": parent_budget,
        "alert_threshold": (
            float(row["budget_alert_threshold"])
            if row["budget_alert_threshold"] is not None
            else 0.80
        ),
    }


@router.put("/{node_id}/budget")
async def set_budget(
    node_id: str,
    body: SetBudgetRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await _get_node_row(session, node_id)
    if not can_access(current_user, row["path"], "area_owner"):
        raise HTTPException(403, "Insufficient permissions")

    # Validate: budget must not exceed parent's budget
    if body.monthly_budget_usd is not None and row["parent_id"]:
        parent_budget_row = (
            await session.execute(
                text(
                    "SELECT monthly_budget_usd FROM organization_nodes WHERE id = CAST(:pid AS uuid)"
                ),
                {"pid": str(row["parent_id"])},
            )
        ).first()
        if (
            parent_budget_row
            and parent_budget_row[0] is not None
            and body.monthly_budget_usd > float(parent_budget_row[0])
        ):
            raise HTTPException(422, "Budget cannot exceed parent node's budget")

    updates: dict = {}
    if body.monthly_budget_usd is not None:
        updates["monthly_budget_usd"] = body.monthly_budget_usd
    if body.budget_alert_threshold is not None:
        updates["budget_alert_threshold"] = body.budget_alert_threshold

    if not updates:
        raise HTTPException(422, "No fields to update")

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["nid"] = node_id
    await session.execute(
        text(f"UPDATE organization_nodes SET {set_clause} WHERE id = CAST(:nid AS uuid)"),
        updates,
    )
    await session.commit()

    # Write-through to the budget-enforcement key the auth service reads
    # (budget_limit:team:{node_id} — auth aliases node_id as team_id). Without
    # this, a node budget set here would never be enforced at request time.
    redis = getattr(request.app.state, "redis", None)
    if redis is not None:
        final = (
            (
                await session.execute(
                    text(
                        "SELECT monthly_budget_usd, budget_alert_threshold "
                        "FROM organization_nodes WHERE id = CAST(:nid AS uuid)"
                    ),
                    {"nid": node_id},
                )
            )
            .mappings()
            .first()
        )
        key = f"budget_limit:team:{node_id}"
        if final and final["monthly_budget_usd"] is not None:
            threshold = final["budget_alert_threshold"]
            await redis.set(
                key,
                json.dumps(
                    {
                        "limit": float(final["monthly_budget_usd"]),
                        "action": "alert",
                        "alert_pct": float(threshold) if threshold is not None else 0.8,
                    }
                ),
            )
        else:
            await redis.delete(key)

    return {"ok": True}


# ---------------------------------------------------------------------------
# Permissions (role_assignments)
# ---------------------------------------------------------------------------


@router.get("/{node_id}/permissions")
async def list_permissions(
    node_id: str,
    include_inherited: bool = Query(default=False),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await _get_node_row(session, node_id)
    if not can_access(current_user, row["path"], "team_admin"):
        raise HTTPException(403, "Insufficient permissions")

    def _fmt(a: Any, inherited: bool = False, source_node_name: str | None = None) -> dict:
        is_user = a["user_id"] is not None
        return {
            "id": str(a["id"]),
            "subject": "user" if is_user else "group",
            "user_id": str(a["user_id"]) if is_user else None,
            "user_email": a.get("user_email"),
            "user_display_name": a.get("user_display_name"),
            "entra_group_id": a["entra_group_id"],
            "entra_group_name": a["entra_group_name"],
            "role": a["role"],
            "node_id": str(a["node_id"]),
            "granted_at": a["granted_at"].isoformat() if a["granted_at"] else None,
            "granted_by": str(a["granted_by"]) if a["granted_by"] else None,
            "granted_by_email": a.get("granted_by_email"),
            "inherited": inherited,
            "source_node_name": source_node_name,
        }

    # Direct assignments on this node
    direct_rows = (
        (
            await session.execute(
                text("""
            SELECT ra.id, ra.entra_group_id, ra.entra_group_name, ra.role,
                   ra.node_id, ra.granted_at, ra.granted_by, ra.user_id,
                   u.email AS granted_by_email,
                   su.email AS user_email, su.display_name AS user_display_name
            FROM role_assignments ra
            LEFT JOIN users u ON u.id = ra.granted_by
            LEFT JOIN users su ON su.id = ra.user_id
            WHERE ra.node_id = CAST(:nid AS uuid)
            ORDER BY ra.granted_at DESC
        """),
                {"nid": node_id},
            )
        )
        .mappings()
        .all()
    )

    result = [_fmt(a) for a in direct_rows]

    if include_inherited:
        # Ancestor node IDs from the path (excludes current node)
        parts = [p for p in row["path"].strip("/").split("/") if p and p != node_id]
        if parts:
            ancestor_rows = (
                (
                    await session.execute(
                        text("""
                    SELECT ra.id, ra.entra_group_id, ra.entra_group_name, ra.role,
                           ra.node_id, ra.granted_at, ra.granted_by, ra.user_id,
                           u.email AS granted_by_email,
                           su.email AS user_email, su.display_name AS user_display_name,
                           n.name AS source_node_name
                    FROM role_assignments ra
                    LEFT JOIN users u ON u.id = ra.granted_by
                    LEFT JOIN users su ON su.id = ra.user_id
                    JOIN organization_nodes n ON n.id = ra.node_id
                    WHERE ra.node_id = ANY(CAST(:ids AS uuid[]))
                    ORDER BY length(n.path), ra.granted_at DESC
                """),
                        {"ids": parts},
                    )
                )
                .mappings()
                .all()
            )
            result.extend(
                _fmt(a, inherited=True, source_node_name=a["source_node_name"])
                for a in ancestor_rows
            )

    return result


@router.post("/{node_id}/permissions", status_code=201)
async def add_permission(
    node_id: str,
    body: AddPermissionRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await _get_node_row(session, node_id)
    if not can_access(current_user, row["path"], "area_owner"):
        raise HTTPException(403, "Insufficient permissions")

    valid_roles = {"gateway_admin", "area_owner", "unit_lead", "team_admin", "engineer", "reporter"}
    if body.role not in valid_roles:
        raise HTTPException(422, f"role must be one of {sorted(valid_roles)}")

    if not body.entra_group_id and not body.user_id:
        raise HTTPException(422, "Either entra_group_id or user_id is required")
    if body.entra_group_id and body.user_id:
        raise HTTPException(422, "Only one of entra_group_id or user_id may be specified")

    # Privilege-amplification guard: a grantor may not assign a role more
    # powerful than the one they themselves hold on this node.
    if _ROLE_POWER.get(body.role, 0) > max_role_power(current_user, row["path"]):
        raise HTTPException(403, "Cannot grant a role above your own on this node")

    assignment_id = str(uuid.uuid4())
    if body.user_id:
        await session.execute(
            text("""
                INSERT INTO role_assignments
                    (id, user_id, role, node_id, granted_by)
                VALUES
                    (CAST(:id AS uuid), CAST(:uid AS uuid), :role,
                     CAST(:nid AS uuid), CAST(:by AS uuid))
                ON CONFLICT DO NOTHING
            """),
            {
                "id": assignment_id,
                "uid": body.user_id,
                "role": body.role,
                "nid": node_id,
                "by": current_user["user_id"],
            },
        )
    else:
        await session.execute(
            text("""
                INSERT INTO role_assignments
                    (id, entra_group_id, entra_group_name, role, node_id, granted_by)
                VALUES
                    (CAST(:id AS uuid), :group_id, :group_name, :role,
                     CAST(:nid AS uuid), CAST(:by AS uuid))
                ON CONFLICT (entra_group_id, role, node_id) DO NOTHING
            """),
            {
                "id": assignment_id,
                "group_id": body.entra_group_id,
                "group_name": body.entra_group_name,
                "role": body.role,
                "nid": node_id,
                "by": current_user["user_id"],
            },
        )
    await session.commit()
    return {"ok": True, "id": assignment_id}


@router.get("/{node_id}/training-capture")
async def get_training_capture(
    node_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await _get_node_row(session, node_id)
    if not can_access(current_user, row["path"], "viewer"):
        raise HTTPException(403, "Insufficient permissions")

    result = (
        await session.execute(
            text(
                "SELECT training_capture_enabled FROM organization_nodes WHERE id = CAST(:nid AS uuid)"
            ),
            {"nid": node_id},
        )
    ).first()
    enabled = bool(result[0]) if result else False

    count = (
        await session.execute(
            text(
                "SELECT COUNT(*) FROM training_candidates WHERE team_id = :nid AND exported_at IS NULL"
            ),
            {"nid": node_id},
        )
    ).scalar() or 0

    return {"training_capture_enabled": enabled, "pending_candidates": int(count)}


class _TrainingCaptureUpdate(BaseModel):
    training_capture_enabled: bool


@router.put("/{node_id}/training-capture")
async def set_training_capture(
    node_id: str,
    body: _TrainingCaptureUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await _get_node_row(session, node_id)
    if not can_access(current_user, row["path"], "area_owner"):
        raise HTTPException(403, "Requires area_owner or above")

    enabled = body.training_capture_enabled
    await session.execute(
        text(
            "UPDATE organization_nodes SET training_capture_enabled = :enabled "
            "WHERE id = CAST(:nid AS uuid)"
        ),
        {"enabled": enabled, "nid": node_id},
    )
    from app import audit

    await audit.record(
        session,
        request,
        "set_training_capture",
        "node",
        resource_id=node_id,
        details={"training_capture_enabled": enabled},
    )
    await session.commit()
    return {"training_capture_enabled": enabled}


@router.delete("/{node_id}/training-data", status_code=200)
async def erase_training_data(
    node_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """GDPR Art. 17 right-to-erasure — delete all unexported training candidates for this node."""
    row = await _get_node_row(session, node_id)
    if not can_access(current_user, row["path"], "area_owner"):
        raise HTTPException(403, "Requires area_owner or above")

    result = await session.execute(
        text("DELETE FROM training_candidates WHERE team_id = :nid AND exported_at IS NULL"),
        {"nid": node_id},
    )
    deleted_count = result.rowcount

    from app import audit

    await audit.record(
        session,
        request,
        "erase_training_data",
        "node",
        resource_id=node_id,
        details={"deleted_count": deleted_count},
    )
    await session.commit()
    return {"deleted": deleted_count}


@router.delete("/{node_id}/permissions/{assignment_id}", status_code=204)
async def remove_permission(
    node_id: str,
    assignment_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await _get_node_row(session, node_id)
    if not can_access(current_user, row["path"], "area_owner"):
        raise HTTPException(403, "Insufficient permissions")

    await session.execute(
        text("""
            DELETE FROM role_assignments
            WHERE id = CAST(:aid AS uuid) AND node_id = CAST(:nid AS uuid)
        """),
        {"aid": assignment_id, "nid": node_id},
    )
    await session.commit()
