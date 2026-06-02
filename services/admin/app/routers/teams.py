from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.db import get_session
from app.models.team import Project, Team
from app.routers.unified_auth import _can_manage_area, _can_manage_team, get_current_user

router = APIRouter(prefix="/teams", tags=["teams"])


class TeamCreate(BaseModel):
    name: str
    slug: str
    area_id: UUID | None = None
    unit_id: UUID | None = None


class ProjectCreate(BaseModel):
    name: str
    slug: str


def _team_row_to_dict(row) -> dict:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "slug": row["slug"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "monthly_budget_usd": float(row["monthly_budget_usd"])
        if row["monthly_budget_usd"] is not None
        else None,
        "budget_alert_pct": row["budget_alert_pct"],
        "budget_action": row["budget_action"],
        "area_id": str(row["area_id"]) if row["area_id"] else None,
        "area_name": row["area_name"],
        "area_slug": row["area_slug"],
        "area_color": row["area_color"],
        "unit_id": str(row["unit_id"]) if row["unit_id"] else None,
        "unit_name": row["unit_name"],
        "unit_slug": row["unit_slug"],
    }


@router.get("")
async def list_teams(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        text("""
        SELECT t.id, t.name, t.slug, t.created_at, t.monthly_budget_usd,
               t.budget_alert_pct, t.budget_action, t.area_id,
               a.name AS area_name, a.slug AS area_slug, a.color AS area_color,
               t.unit_id, u.name AS unit_name, u.slug AS unit_slug
        FROM teams t
        LEFT JOIN areas a ON a.id = t.area_id
        LEFT JOIN units u ON u.id = t.unit_id
        ORDER BY a.name NULLS LAST, u.name NULLS LAST, t.name
    """)
    )
    return [_team_row_to_dict(row) for row in result.mappings().all()]


@router.post("", status_code=201)
async def create_team(
    body: TeamCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    # area_owner can create teams in their area; platform_admin can create anywhere
    area_id_for_check = str(body.area_id) if body.area_id else ""
    if not await _can_manage_area(user, area_id_for_check):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    area_id = body.area_id
    unit_id = body.unit_id

    # derive area_id from unit if unit_id is provided and area_id is not
    if unit_id and not area_id:
        unit_row = (
            await session.execute(text("SELECT area_id FROM units WHERE id = :id"), {"id": unit_id})
        ).one_or_none()
        if not unit_row:
            raise HTTPException(status_code=404, detail="Unit not found")
        area_id = unit_row[0]

    team = Team(name=body.name, slug=body.slug, area_id=area_id)
    session.add(team)
    await session.flush()  # get generated ID before commit

    # set unit_id via raw SQL since ORM model may not have the column yet
    if unit_id:
        await session.execute(
            text("UPDATE teams SET unit_id = :unit_id WHERE id = :id"),
            {"unit_id": unit_id, "id": team.id},
        )

    await audit.record(session, request, "create_team", "team", resource_id=team.id)
    await session.commit()
    await session.refresh(team)
    return {
        "id": str(team.id),
        "name": team.name,
        "slug": team.slug,
        "created_at": team.created_at.isoformat() if team.created_at else None,
        "monthly_budget_usd": float(team.monthly_budget_usd)
        if team.monthly_budget_usd is not None
        else None,
        "budget_alert_pct": team.budget_alert_pct,
        "budget_action": team.budget_action,
        "area_id": str(team.area_id) if team.area_id else None,
        "unit_id": str(unit_id) if unit_id else None,
    }


@router.get("/{team_id}")
async def get_team(team_id: UUID, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        text("""
            SELECT t.id, t.name, t.slug, t.created_at, t.monthly_budget_usd,
                   t.budget_alert_pct, t.budget_action, t.area_id,
                   a.name AS area_name, a.slug AS area_slug, a.color AS area_color,
                   t.unit_id, u.name AS unit_name, u.slug AS unit_slug
            FROM teams t
            LEFT JOIN areas a ON a.id = t.area_id
            LEFT JOIN units u ON u.id = t.unit_id
            WHERE t.id = :id
        """),
        {"id": team_id},
    )
    row = result.mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Team not found")
    return _team_row_to_dict(row)


@router.put("/{team_id}")
async def update_team(
    team_id: UUID,
    body: TeamCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    if not await _can_manage_team(user, str(team_id), session):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    team = await session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    team.name = body.name
    team.slug = body.slug
    team.area_id = body.area_id
    await audit.record(
        session,
        request,
        "update_team",
        "team",
        resource_id=team_id,
        details={"name": body.name, "slug": body.slug},
    )
    await session.commit()
    await session.refresh(team)
    return {
        "id": str(team.id),
        "name": team.name,
        "slug": team.slug,
        "created_at": team.created_at.isoformat() if team.created_at else None,
        "monthly_budget_usd": float(team.monthly_budget_usd)
        if team.monthly_budget_usd is not None
        else None,
        "budget_alert_pct": team.budget_alert_pct,
        "budget_action": team.budget_action,
        "area_id": str(team.area_id) if team.area_id else None,
    }


@router.delete("/{team_id}", status_code=204)
async def delete_team(
    team_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    if not await _can_manage_team(user, str(team_id), session):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    team = await session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    await audit.record(session, request, "delete_team", "team", resource_id=team_id)
    await session.delete(team)
    await session.commit()


@router.get("/{team_id}/projects")
async def list_projects(team_id: UUID, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Project).where(Project.team_id == team_id))
    return result.scalars().all()


@router.post("/{team_id}/projects", status_code=201)
async def create_project(
    team_id: UUID,
    body: ProjectCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    project = Project(team_id=team_id, name=body.name, slug=body.slug)
    session.add(project)
    await session.flush()
    await audit.record(
        session,
        request,
        "create_project",
        "project",
        resource_id=project.id,
        details={"team_id": str(team_id)},
    )
    await session.commit()
    await session.refresh(project)
    return project
