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
        filters.append("EXISTS (SELECT 1 FROM user_roles r2 WHERE r2.user_id = u.id AND r2.role = :role)")
        params["role"] = role
    if team_id:
        filters.append("""EXISTS (
            SELECT 1 FROM user_roles r3
            WHERE r3.user_id = u.id
              AND r3.scope_type = 'team'
              AND r3.scope_id = CAST(:team_id AS uuid)
        )""")
        params["team_id"] = team_id

    where = " AND ".join(filters)

    count_row = (await session.execute(
        text(f"SELECT COUNT(DISTINCT u.id) FROM users u WHERE {where}"), params
    )).scalar()
    total = int(count_row or 0)

    rows = (await session.execute(text(f"""
        SELECT u.id, u.email, u.display_name, u.status, u.must_change_password,
               u.last_login_at, u.created_at,
               COALESCE(
                   json_agg(json_build_object(
                       'role', r.role, 'scope_type', r.scope_type, 'scope_id', r.scope_id::text
                   )) FILTER (WHERE r.role IS NOT NULL), '[]'
               ) AS roles
        FROM users u
        LEFT JOIN user_roles r ON r.user_id = u.id
        WHERE {where}
        GROUP BY u.id
        ORDER BY u.created_at DESC
        LIMIT :limit OFFSET :offset
    """), params)).mappings().all()
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
    row = (await session.execute(text("""
        SELECT u.id, u.email, u.display_name, u.status, u.must_change_password,
               u.last_login_at, u.created_at, u.primary_team_id::text,
               t.name AS team_name,
               COALESCE(
                   json_agg(json_build_object(
                       'role', r.role, 'scope_type', r.scope_type, 'scope_id', r.scope_id::text
                   )) FILTER (WHERE r.role IS NOT NULL), '[]'
               ) AS roles
        FROM users u
        LEFT JOIN user_roles r ON r.user_id = u.id
        LEFT JOIN teams t ON t.id = u.primary_team_id
        WHERE u.id = CAST(:uid AS uuid)
        GROUP BY u.id, t.name
    """), {"uid": user_id})).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        **dict(row),
        "id": str(row["id"]),
        "roles": _json.loads(row["roles"]) if isinstance(row["roles"], str) else row["roles"],
    }
