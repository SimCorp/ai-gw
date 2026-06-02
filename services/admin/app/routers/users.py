"""
Admin user management router — richer queries for the Users admin page.
Requires admin auth (wired with dependencies=_auth in main.py).
"""

from __future__ import annotations

import json as _json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.routers.admin_auth import get_admin_session

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


@router.get("")
async def list_users(
    search: str | None = Query(default=None),
    role: str | None = Query(default=None),
    status: str | None = Query(default=None),
    team_id: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0),
    auth: dict = Depends(get_admin_session),
    session: AsyncSession = Depends(get_session),
):
    filters = ["1=1"]
    params: dict = {"limit": limit, "offset": offset}

    if search:
        filters.append("(u.email ILIKE :search OR u.display_name ILIKE :search)")
        params["search"] = f"%{search}%"
    if status:
        filters.append("u.status = :status")
        params["status"] = status
    if role:
        # Per-user role table (user_roles) was dropped in migration 0025.
        # Filter on node membership role (admin/member) instead.
        filters.append("""EXISTS (
            SELECT 1 FROM node_members nm2
            WHERE nm2.user_id = u.id::text AND nm2.role = :role
        )""")
        params["role"] = role
    if team_id:
        # team_id is now an organization_nodes id; membership lives in node_members.
        filters.append("""EXISTS (
            SELECT 1 FROM node_members nm3
            WHERE nm3.user_id = u.id::text
              AND nm3.node_id = CAST(:team_id AS uuid)
        )""")
        params["team_id"] = team_id

    where = " AND ".join(filters)

    count_row = (
        await session.execute(
            text(f"SELECT COUNT(DISTINCT u.id) FROM users u WHERE {where}"), params
        )
    ).scalar()
    total = int(count_row or 0)

    rows = (
        (
            await session.execute(
                text(f"""
        SELECT u.id, u.email, u.display_name, u.status, u.must_change_password,
               u.last_login_at, u.created_at,
               COALESCE(
                   json_agg(DISTINCT jsonb_build_object(
                       'role', nm.role, 'scope_type', 'node', 'scope_id', nm.node_id::text
                   )) FILTER (WHERE nm.role IS NOT NULL), '[]'
               ) AS roles
        FROM users u
        LEFT JOIN node_members nm ON nm.user_id = u.id::text
        WHERE {where}
        GROUP BY u.id
        ORDER BY u.created_at DESC
        LIMIT :limit OFFSET :offset
    """),
                params,
            )
        )
        .mappings()
        .all()
    )
    return {
        "total": total,
        "items": [
            {
                **dict(r),
                "id": str(r["id"]),
                "roles": _json.loads(r["roles"]) if isinstance(r["roles"], str) else r["roles"],
            }
            for r in rows
        ],
    }


@router.get("/{user_id}")
async def get_user(
    user_id: str,
    auth: dict = Depends(get_admin_session),
    session: AsyncSession = Depends(get_session),
):
    row = (
        (
            await session.execute(
                text("""
        SELECT u.id, u.email, u.display_name, u.status, u.must_change_password,
               u.last_login_at, u.created_at, u.primary_node_id::text,
               t.name AS team_name,
               COALESCE(
                   json_agg(DISTINCT jsonb_build_object(
                       'role', nm.role, 'scope_type', 'node', 'scope_id', nm.node_id::text
                   )) FILTER (WHERE nm.role IS NOT NULL), '[]'
               ) AS roles
        FROM users u
        LEFT JOIN node_members nm ON nm.user_id = u.id::text
        LEFT JOIN organization_nodes t ON t.id = u.primary_node_id
        WHERE u.id = CAST(:uid AS uuid)
        GROUP BY u.id, t.name
    """),
                {"uid": user_id},
            )
        )
        .mappings()
        .first()
    )

    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        **dict(row),
        "id": str(row["id"]),
        "roles": _json.loads(row["roles"]) if isinstance(row["roles"], str) else row["roles"],
    }
