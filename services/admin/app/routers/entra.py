"""Azure Entra ID group → gateway role mapping management."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.routers.unified_auth import get_current_user, require_platform_admin

router = APIRouter(prefix="/settings/entra", tags=["entra"])


class GroupMappingCreate(BaseModel):
    entra_group_id: str
    entra_group_name: str | None = None
    role: str
    scope_type: str = "global"
    scope_id: str | None = None


_VALID_ROLES = {
    "platform_admin", "area_owner", "unit_lead",
    "team_admin", "developer", "viewer", "service_account",
}
_VALID_SCOPE_TYPES = {"global", "area", "unit", "team"}


@router.get("")
async def list_mappings(
    admin: dict = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_session),
):
    rows = (await session.execute(text("""
        SELECT m.id, m.entra_group_id, m.entra_group_name, m.role, m.scope_type,
               m.scope_id::text, m.created_at,
               u.email AS created_by_email,
               CASE m.scope_type
                   WHEN 'area' THEN (SELECT name FROM areas WHERE id = m.scope_id)
                   WHEN 'unit' THEN (SELECT name FROM units WHERE id = m.scope_id)
                   WHEN 'team' THEN (SELECT name FROM teams WHERE id = m.scope_id)
               END AS scope_name
        FROM entra_group_role_mappings m
        LEFT JOIN users u ON u.id = m.created_by
        ORDER BY m.entra_group_name, m.role
    """))).mappings().all()
    return [dict(r) for r in rows]


@router.post("", status_code=201)
async def create_mapping(
    body: GroupMappingCreate,
    admin: dict = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_session),
):
    if body.role not in _VALID_ROLES:
        raise HTTPException(status_code=422, detail=f"Invalid role: {body.role}")
    if body.scope_type not in _VALID_SCOPE_TYPES:
        raise HTTPException(status_code=422, detail=f"Invalid scope_type: {body.scope_type}")

    row = (await session.execute(text("""
        INSERT INTO entra_group_role_mappings
            (entra_group_id, entra_group_name, role, scope_type, scope_id, created_by)
        VALUES (:gid, :gname, :role, :scope_type, CAST(:scope_id AS uuid), CAST(:by AS uuid))
        ON CONFLICT ON CONSTRAINT entra_group_role_mappings_unique DO UPDATE
            SET entra_group_name = EXCLUDED.entra_group_name
        RETURNING id, entra_group_id, entra_group_name, role, scope_type, scope_id::text, created_at
    """), {
        "gid": body.entra_group_id,
        "gname": body.entra_group_name,
        "role": body.role,
        "scope_type": body.scope_type,
        "scope_id": body.scope_id,
        "by": admin["user_id"],
    })).mappings().one()
    await session.commit()
    return dict(row)


@router.delete("/{mapping_id}", status_code=204)
async def delete_mapping(
    mapping_id: str,
    admin: dict = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        text("DELETE FROM entra_group_role_mappings WHERE id = CAST(:id AS uuid) RETURNING id"),
        {"id": mapping_id},
    )
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Mapping not found")
    await session.commit()
