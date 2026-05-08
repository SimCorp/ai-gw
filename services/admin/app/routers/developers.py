from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session

router = APIRouter(prefix="/developers", tags=["developers"])


@router.get("")
async def list_developers(session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(text("""
        SELECT d.id, d.email, d.display_name, d.status, d.created_at,
               d.team_id, t.name AS team_name
        FROM developers d
        LEFT JOIN teams t ON t.id = d.team_id
        ORDER BY d.created_at DESC
    """))).mappings().all()
    return [
        {
            "id": str(r["id"]),
            "email": r["email"],
            "display_name": r["display_name"],
            "status": r["status"],
            "team_id": str(r["team_id"]) if r["team_id"] else None,
            "team_name": r["team_name"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]


@router.get("/{developer_id}")
async def get_developer(developer_id: UUID, session: AsyncSession = Depends(get_session)):
    row = (await session.execute(
        text("""
            SELECT d.id, d.email, d.display_name, d.status, d.created_at,
                   d.team_id, t.name AS team_name, a.name AS area_name, a.color AS area_color
            FROM developers d
            LEFT JOIN teams t ON t.id = d.team_id
            LEFT JOIN areas a ON a.id = t.area_id
            WHERE d.id = :id
        """),
        {"id": developer_id},
    )).mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Developer not found")
    return {
        "id": str(row["id"]),
        "email": row["email"],
        "display_name": row["display_name"],
        "status": row["status"],
        "team_id": str(row["team_id"]) if row["team_id"] else None,
        "team_name": row["team_name"],
        "area_name": row["area_name"],
        "area_color": row["area_color"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }
