from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.db import get_session
from app.models.member import TeamMember

router = APIRouter(prefix="/teams/{team_id}/members", tags=["members"])


class MemberAdd(BaseModel):
    user_id: str
    role: str = "member"


@router.get("")
async def list_members(team_id: UUID, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(TeamMember).where(TeamMember.team_id == team_id)
    )
    return result.scalars().all()


@router.post("", status_code=201)
async def add_member(
    team_id: UUID,
    body: MemberAdd,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    if body.role not in ("admin", "member"):
        raise HTTPException(status_code=422, detail="role must be 'admin' or 'member'")
    member = TeamMember(team_id=team_id, user_id=body.user_id, role=body.role)
    session.add(member)
    await audit.record(
        session, request, "add_member", "team_member",
        details={"team_id": str(team_id), "user_id": body.user_id, "role": body.role},
    )
    await session.commit()
    await session.refresh(member)
    return member


@router.put("/{user_id}")
async def update_member_role(
    team_id: UUID,
    user_id: str,
    body: MemberAdd,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    if body.role not in ("admin", "member"):
        raise HTTPException(status_code=422, detail="role must be 'admin' or 'member'")
    result = await session.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id, TeamMember.user_id == user_id
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    member.role = body.role
    await audit.record(
        session, request, "update_member_role", "team_member",
        details={"team_id": str(team_id), "user_id": user_id, "role": body.role},
    )
    await session.commit()
    await session.refresh(member)
    return member


@router.delete("/{user_id}", status_code=204)
async def remove_member(
    team_id: UUID,
    user_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id, TeamMember.user_id == user_id
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    await audit.record(
        session, request, "remove_member", "team_member",
        details={"team_id": str(team_id), "user_id": user_id},
    )
    await session.delete(member)
    await session.commit()
