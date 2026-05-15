import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.db import get_session

router = APIRouter(prefix="/units", tags=["units"])


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


class UnitCreate(BaseModel):
    area_id: UUID
    name: str
    slug: str | None = None
    description: str | None = None
    color: str | None = None


class UnitUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    description: str | None = None
    color: str | None = None


def _row_to_dict(row) -> dict:
    return {
        "id": str(row["id"]),
        "area_id": str(row["area_id"]),
        "area_name": row["area_name"],
        "name": row["name"],
        "slug": row["slug"],
        "description": row["description"],
        "color": row["color"],
        "team_count": row["team_count"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


@router.get("")
async def list_units(area_id: UUID | None = None, session: AsyncSession = Depends(get_session)):
    if area_id:
        result = await session.execute(
            text("""
                SELECT u.id, u.area_id, a.name AS area_name, u.name, u.slug, u.description, u.color,
                       COUNT(t.id) AS team_count, u.created_at
                FROM units u
                JOIN areas a ON a.id = u.area_id
                LEFT JOIN teams t ON t.unit_id = u.id
                WHERE u.area_id = :area_id
                GROUP BY u.id, a.name
                ORDER BY a.name, u.name
            """),
            {"area_id": area_id},
        )
    else:
        result = await session.execute(text("""
            SELECT u.id, u.area_id, a.name AS area_name, u.name, u.slug, u.description, u.color,
                   COUNT(t.id) AS team_count, u.created_at
            FROM units u
            JOIN areas a ON a.id = u.area_id
            LEFT JOIN teams t ON t.unit_id = u.id
            GROUP BY u.id, a.name
            ORDER BY a.name, u.name
        """))
    return [_row_to_dict(row) for row in result.mappings().all()]


@router.post("", status_code=201)
async def create_unit(body: UnitCreate, request: Request, session: AsyncSession = Depends(get_session)):
    slug = body.slug or _slugify(body.name)

    # check area exists
    area = (await session.execute(
        text("SELECT id FROM areas WHERE id = :id"), {"id": body.area_id}
    )).one_or_none()
    if not area:
        raise HTTPException(status_code=404, detail="Area not found")

    # check slug uniqueness within area
    existing = (await session.execute(
        text("SELECT id FROM units WHERE area_id = :area_id AND slug = :slug"),
        {"area_id": body.area_id, "slug": slug},
    )).one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="A unit with this slug already exists in the area")

    result = await session.execute(
        text("""
            INSERT INTO units (area_id, name, slug, description, color)
            VALUES (:area_id, :name, :slug, :description, :color)
            RETURNING id, area_id, name, slug, description, color, created_at
        """),
        {"area_id": body.area_id, "name": body.name, "slug": slug,
         "description": body.description, "color": body.color},
    )
    row = result.mappings().one()
    await audit.record(session, request, "create_unit", "unit", resource_id=row["id"])
    await session.commit()
    return {
        "id": str(row["id"]),
        "area_id": str(row["area_id"]),
        "name": row["name"],
        "slug": row["slug"],
        "description": row["description"],
        "color": row["color"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


@router.get("/{unit_id}")
async def get_unit(unit_id: UUID, session: AsyncSession = Depends(get_session)):
    unit_row = (await session.execute(
        text("""
            SELECT u.id, u.area_id, a.name AS area_name, u.name, u.slug, u.description, u.color, u.created_at
            FROM units u JOIN areas a ON a.id = u.area_id
            WHERE u.id = :id
        """),
        {"id": unit_id},
    )).mappings().one_or_none()
    if not unit_row:
        raise HTTPException(status_code=404, detail="Unit not found")

    teams_result = await session.execute(
        text("""
            SELECT id, name, slug, created_at, monthly_budget_usd, budget_alert_pct, budget_action
            FROM teams WHERE unit_id = :unit_id ORDER BY name
        """),
        {"unit_id": unit_id},
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
        "unit": {
            "id": str(unit_row["id"]),
            "area_id": str(unit_row["area_id"]),
            "area_name": unit_row["area_name"],
            "name": unit_row["name"],
            "slug": unit_row["slug"],
            "description": unit_row["description"],
            "color": unit_row["color"],
            "created_at": unit_row["created_at"].isoformat() if unit_row["created_at"] else None,
        },
        "teams": teams,
    }


@router.put("/{unit_id}")
async def update_unit(
    unit_id: UUID, body: UnitUpdate, request: Request, session: AsyncSession = Depends(get_session)
):
    current = (await session.execute(
        text("SELECT id, area_id, name, slug, description, color, created_at FROM units WHERE id = :id"),
        {"id": unit_id},
    )).mappings().one_or_none()
    if not current:
        raise HTTPException(status_code=404, detail="Unit not found")

    new_name = body.name if body.name is not None else current["name"]
    new_slug = body.slug if body.slug is not None else current["slug"]
    new_description = body.description if body.description is not None else current["description"]
    new_color = body.color if body.color is not None else current["color"]

    # check slug uniqueness if changed
    if new_slug != current["slug"]:
        conflict = (await session.execute(
            text("SELECT id FROM units WHERE area_id = :area_id AND slug = :slug AND id != :id"),
            {"area_id": current["area_id"], "slug": new_slug, "id": unit_id},
        )).one_or_none()
        if conflict:
            raise HTTPException(status_code=409, detail="A unit with this slug already exists in the area")

    result = await session.execute(
        text("""
            UPDATE units SET name = :name, slug = :slug, description = :description, color = :color
            WHERE id = :id
            RETURNING id, area_id, name, slug, description, color, created_at
        """),
        {"id": unit_id, "name": new_name, "slug": new_slug,
         "description": new_description, "color": new_color},
    )
    row = result.mappings().one()
    await audit.record(session, request, "update_unit", "unit", resource_id=unit_id,
                       details={"name": new_name, "slug": new_slug})
    await session.commit()
    return {
        "id": str(row["id"]),
        "area_id": str(row["area_id"]),
        "name": row["name"],
        "slug": row["slug"],
        "description": row["description"],
        "color": row["color"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


@router.delete("/{unit_id}", status_code=204)
async def delete_unit(unit_id: UUID, request: Request, session: AsyncSession = Depends(get_session)):
    unit = (await session.execute(
        text("SELECT id FROM units WHERE id = :id"), {"id": unit_id}
    )).one_or_none()
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")

    team_count = (await session.execute(
        text("SELECT COUNT(*) FROM teams WHERE unit_id = :unit_id"), {"unit_id": unit_id}
    )).scalar()
    if team_count > 0:
        raise HTTPException(status_code=409, detail="Cannot delete unit with existing teams")

    await session.execute(text("DELETE FROM units WHERE id = :id"), {"id": unit_id})
    await audit.record(session, request, "delete_unit", "unit", resource_id=unit_id)
    await session.commit()
