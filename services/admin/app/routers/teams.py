from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.db import get_session
from app.models.team import Project, Team

router = APIRouter(prefix="/teams", tags=["teams"])


class TeamCreate(BaseModel):
    name: str
    slug: str


class ProjectCreate(BaseModel):
    name: str
    slug: str


@router.get("")
async def list_teams(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Team).order_by(Team.created_at))
    return result.scalars().all()


@router.post("", status_code=201)
async def create_team(
    body: TeamCreate, request: Request, session: AsyncSession = Depends(get_session)
):
    team = Team(name=body.name, slug=body.slug)
    session.add(team)
    await session.flush()  # get generated ID before commit
    await audit.record(session, request, "create_team", "team", resource_id=team.id)
    await session.commit()
    await session.refresh(team)
    return team


@router.get("/{team_id}")
async def get_team(team_id: UUID, session: AsyncSession = Depends(get_session)):
    team = await session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team


@router.put("/{team_id}")
async def update_team(
    team_id: UUID,
    body: TeamCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    team = await session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    team.name = body.name
    team.slug = body.slug
    await audit.record(
        session, request, "update_team", "team", resource_id=team_id,
        details={"name": body.name, "slug": body.slug},
    )
    await session.commit()
    await session.refresh(team)
    return team


@router.delete("/{team_id}", status_code=204)
async def delete_team(
    team_id: UUID, request: Request, session: AsyncSession = Depends(get_session)
):
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
        session, request, "create_project", "project", resource_id=project.id,
        details={"team_id": str(team_id)},
    )
    await session.commit()
    await session.refresh(project)
    return project
