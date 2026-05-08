from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.db import get_session

router = APIRouter(prefix="/areas", tags=["areas"])


class AreaCreate(BaseModel):
    name: str
    slug: str
    description: str | None = None
    color: str | None = None


class AreaUpdate(BaseModel):
    name: str
    slug: str
    description: str | None = None
    color: str | None = None


def _row_to_area_dict(row) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "slug": row.slug,
        "description": row.description,
        "color": row.color,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("")
async def list_areas(session: AsyncSession = Depends(get_session)):
    result = await session.execute(text("""
        SELECT a.id, a.name, a.slug, a.description, a.color, a.created_at,
               COUNT(t.id) AS team_count
        FROM areas a
        LEFT JOIN teams t ON t.area_id = a.id
        GROUP BY a.id
        ORDER BY a.name
    """))
    rows = result.mappings().all()
    return [
        {
            "id": str(row["id"]),
            "name": row["name"],
            "slug": row["slug"],
            "description": row["description"],
            "color": row["color"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "team_count": row["team_count"],
        }
        for row in rows
    ]


@router.post("", status_code=201)
async def create_area(
    body: AreaCreate, request: Request, session: AsyncSession = Depends(get_session)
):
    result = await session.execute(
        text("""
            INSERT INTO areas (name, slug, description, color)
            VALUES (:name, :slug, :description, :color)
            RETURNING id, name, slug, description, color, created_at
        """),
        {"name": body.name, "slug": body.slug, "description": body.description, "color": body.color},
    )
    row = result.mappings().one()
    area_id = row["id"]
    await audit.record(session, request, "create_area", "area", resource_id=area_id)
    await session.commit()
    return {
        "id": str(area_id),
        "name": row["name"],
        "slug": row["slug"],
        "description": row["description"],
        "color": row["color"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


@router.get("/{area_id}")
async def get_area(area_id: UUID, session: AsyncSession = Depends(get_session)):
    area_result = await session.execute(
        text("SELECT id, name, slug, description, color, created_at FROM areas WHERE id = :id"),
        {"id": area_id},
    )
    area_row = area_result.mappings().one_or_none()
    if not area_row:
        raise HTTPException(status_code=404, detail="Area not found")

    teams_result = await session.execute(
        text("""
            SELECT id, name, slug, created_at, monthly_budget_usd, budget_alert_pct, budget_action
            FROM teams WHERE area_id = :area_id ORDER BY name
        """),
        {"area_id": area_id},
    )
    teams = [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "slug": r["slug"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "monthly_budget_usd": float(r["monthly_budget_usd"]) if r["monthly_budget_usd"] is not None else None,
            "budget_alert_pct": r["budget_alert_pct"],
            "budget_action": r["budget_action"],
        }
        for r in teams_result.mappings().all()
    ]

    return {
        "area": {
            "id": str(area_row["id"]),
            "name": area_row["name"],
            "slug": area_row["slug"],
            "description": area_row["description"],
            "color": area_row["color"],
            "created_at": area_row["created_at"].isoformat() if area_row["created_at"] else None,
        },
        "teams": teams,
    }


@router.put("/{area_id}")
async def update_area(
    area_id: UUID,
    body: AreaUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        text("""
            UPDATE areas SET name = :name, slug = :slug, description = :description, color = :color
            WHERE id = :id
            RETURNING id, name, slug, description, color, created_at
        """),
        {"id": area_id, "name": body.name, "slug": body.slug, "description": body.description, "color": body.color},
    )
    row = result.mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Area not found")
    await audit.record(
        session, request, "update_area", "area", resource_id=area_id,
        details={"name": body.name, "slug": body.slug},
    )
    await session.commit()
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "slug": row["slug"],
        "description": row["description"],
        "color": row["color"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


@router.delete("/{area_id}", status_code=204)
async def delete_area(
    area_id: UUID, request: Request, session: AsyncSession = Depends(get_session)
):
    result = await session.execute(
        text("DELETE FROM areas WHERE id = :id RETURNING id"),
        {"id": area_id},
    )
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Area not found")
    await audit.record(session, request, "delete_area", "area", resource_id=area_id)
    await session.commit()
