"""Local groups — unmanaged (local-account) identity groups.

Local groups let admins bundle local-account users and assign them roles on org
nodes via role_assignments (entra_group_id = lcl-<uuid> or via the group's TEXT id).
Schema created in migration 0033.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.routers.unified_auth import can_access, get_current_user

router = APIRouter(prefix="/admin/local-groups", tags=["local-groups"])


class CreateGroupRequest(BaseModel):
    name: str


class AddMemberRequest(BaseModel):
    user_id: str


@router.get("")
async def list_groups(
    search: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not can_access(current_user, "/", "team_admin"):
        raise HTTPException(403, "Insufficient permissions")

    conditions = ["1=1"]
    params: dict = {"limit": limit, "offset": offset}
    if search:
        conditions.append("lg.name ILIKE :search")
        params["search"] = f"%{search}%"

    where = " AND ".join(conditions)
    rows = (
        (
            await session.execute(
                text(f"""
            SELECT lg.id, lg.name, lg.created_at,
                   COUNT(DISTINCT lgm.user_id) AS member_count
            FROM local_groups lg
            LEFT JOIN local_group_members lgm ON lgm.group_id = lg.id
            WHERE {where}
            GROUP BY lg.id, lg.name, lg.created_at
            ORDER BY lg.name
            LIMIT :limit OFFSET :offset
        """),
                params,
            )
        )
        .mappings()
        .all()
    )
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "member_count": r["member_count"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]


@router.post("", status_code=201)
async def create_group(
    body: CreateGroupRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not can_access(current_user, "/", "team_admin"):
        raise HTTPException(403, "Insufficient permissions")

    group_id = f"lcl-{uuid.uuid4()}"
    await session.execute(
        text("INSERT INTO local_groups (id, name) VALUES (:id, :name)"),
        {"id": group_id, "name": body.name.strip()},
    )
    await session.commit()
    return {"id": group_id, "name": body.name.strip()}


@router.delete("/{group_id}", status_code=204)
async def delete_group(
    group_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not can_access(current_user, "/", "area_owner"):
        raise HTTPException(403, "Insufficient permissions")

    # CASCADE on local_group_members handled by FK; also delete role_assignments
    await session.execute(
        text("DELETE FROM role_assignments WHERE entra_group_id = :gid"),
        {"gid": group_id},
    )
    await session.execute(
        text("DELETE FROM local_groups WHERE id = :gid"),
        {"gid": group_id},
    )
    await session.commit()


@router.get("/{group_id}/members")
async def list_members(
    group_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not can_access(current_user, "/", "team_admin"):
        raise HTTPException(403, "Insufficient permissions")

    rows = (
        (
            await session.execute(
                text("""
            SELECT u.id, u.email, u.display_name, lgm.group_id
            FROM local_group_members lgm
            JOIN users u ON u.id = lgm.user_id
            WHERE lgm.group_id = :gid
            ORDER BY u.display_name, u.email
        """),
                {"gid": group_id},
            )
        )
        .mappings()
        .all()
    )
    return [
        {
            "id": str(r["id"]),
            "email": r["email"],
            "display_name": r["display_name"] or "",
        }
        for r in rows
    ]


@router.post("/{group_id}/members", status_code=201)
async def add_member(
    group_id: str,
    body: AddMemberRequest,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not can_access(current_user, "/", "team_admin"):
        raise HTTPException(403, "Insufficient permissions")

    group = (
        await session.execute(
            text("SELECT id FROM local_groups WHERE id = :gid"),
            {"gid": group_id},
        )
    ).first()
    if not group:
        raise HTTPException(404, "Group not found")

    await session.execute(
        text("""
            INSERT INTO local_group_members (group_id, user_id)
            VALUES (:gid, CAST(:uid AS uuid))
            ON CONFLICT DO NOTHING
        """),
        {"gid": group_id, "uid": body.user_id},
    )
    await session.commit()
    return {"ok": True}


@router.delete("/{group_id}/members/{user_id}", status_code=204)
async def remove_member(
    group_id: str,
    user_id: str,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not can_access(current_user, "/", "team_admin"):
        raise HTTPException(403, "Insufficient permissions")

    await session.execute(
        text("""
            DELETE FROM local_group_members
            WHERE group_id = :gid AND user_id = CAST(:uid AS uuid)
        """),
        {"gid": group_id, "uid": user_id},
    )
    await session.commit()
