"""Azure Entra ID group → gateway role mapping management.

Backed by the unified ``role_assignments`` table (entra_group_id, role, node_id)
introduced in the organization-nodes refactor (migration 0025). The old
``entra_group_role_mappings`` table and its scope_type/scope_id model were
dropped — a mapping's scope is now simply the organization node it targets:

  * ``scope_type = 'global'`` → the root node (grants apply to the whole tree
    via path-prefix inheritance in ``unified_auth.can_access``)
  * ``scope_type = 'area' | 'unit' | 'team'`` → a node of that ``type``

The legacy request/response shape (scope_type + scope_id + scope_name) is kept
for backwards compatibility with the admin UI; it is derived from the node row.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.routers.unified_auth import require_platform_admin

router = APIRouter(prefix="/settings/entra", tags=["entra"])


class GroupMappingCreate(BaseModel):
    entra_group_id: str
    entra_group_name: str | None = None
    role: str
    scope_type: str = "global"
    scope_id: str | None = None


_VALID_ROLES = {
    "platform_admin",
    "area_owner",
    "unit_lead",
    "team_admin",
    "developer",
    "viewer",
}
_VALID_SCOPE_TYPES = {"global", "area", "unit", "team"}


async def _root_node_id(session: AsyncSession) -> str:
    row = (
        (
            await session.execute(
                text(
                    "SELECT id::text AS id FROM organization_nodes "
                    "WHERE type = 'root' ORDER BY created_at LIMIT 1"
                )
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise HTTPException(status_code=500, detail="Root organization node missing")
    return row["id"]


@router.get("")
async def list_mappings(
    admin: dict = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_session),
):
    rows = (
        (
            await session.execute(
                text("""
        SELECT ra.id, ra.entra_group_id, ra.entra_group_name, ra.role,
               ra.node_id::text AS scope_id, ra.granted_at AS created_at,
               CASE WHEN n.type = 'root' THEN 'global' ELSE n.type END AS scope_type,
               CASE WHEN n.type = 'root' THEN NULL ELSE n.name END AS scope_name,
               u.email AS created_by_email
        FROM role_assignments ra
        JOIN organization_nodes n ON n.id = ra.node_id
        LEFT JOIN users u ON u.id = ra.granted_by
        ORDER BY ra.entra_group_name, ra.role
    """)
            )
        )
        .mappings()
        .all()
    )
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

    # Resolve the scope to a concrete node: global → root, otherwise the given node.
    if body.scope_type == "global":
        node_id = await _root_node_id(session)
    else:
        if not body.scope_id:
            raise HTTPException(
                status_code=422,
                detail=f"scope_id is required for scope_type '{body.scope_type}'",
            )
        node_id = body.scope_id

    row = (
        (
            await session.execute(
                text("""
        INSERT INTO role_assignments
            (entra_group_id, entra_group_name, role, node_id, granted_by)
        VALUES (:gid, :gname, :role, CAST(:nid AS uuid), CAST(:by AS uuid))
        ON CONFLICT (entra_group_id, role, node_id) DO UPDATE
            SET entra_group_name = EXCLUDED.entra_group_name
        RETURNING id, entra_group_id, entra_group_name, role,
                  node_id::text AS scope_id, granted_at AS created_at
    """),
                {
                    "gid": body.entra_group_id,
                    "gname": body.entra_group_name,
                    "role": body.role,
                    "nid": node_id,
                    "by": admin["user_id"],
                },
            )
        )
        .mappings()
        .one()
    )
    await session.commit()
    return dict(row)


@router.delete("/{mapping_id}", status_code=204)
async def delete_mapping(
    mapping_id: str,
    admin: dict = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        text("DELETE FROM role_assignments WHERE id = CAST(:id AS uuid) RETURNING id"),
        {"id": mapping_id},
    )
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Mapping not found")
    await session.commit()
