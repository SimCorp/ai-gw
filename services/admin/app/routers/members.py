from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.db import get_session
from app.models.member import TeamMember
from app.routers.unified_auth import _can_manage_team, get_current_user

router = APIRouter(prefix="/teams/{team_id}/members", tags=["members"])


class MemberAdd(BaseModel):
    user_id: str
    role: str = "member"


@router.get("")
async def list_members(team_id: UUID, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(TeamMember).where(TeamMember.team_id == team_id))
    return result.scalars().all()


@router.post("", status_code=201)
async def add_member(
    team_id: UUID,
    body: MemberAdd,
    request: Request,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not await _can_manage_team(current_user, str(team_id), session):
        raise HTTPException(status_code=403, detail="You cannot manage this team")

    if body.role not in ("admin", "member"):
        raise HTTPException(status_code=422, detail="role must be 'admin' or 'member'")

    # Try to link developer by email if user_id looks like an email
    # Bug 3 fix: make legacy developers table lookup non-fatal
    developer_id = None
    if "@" in body.user_id:
        try:
            dev_row = (
                await session.execute(
                    text("SELECT id FROM developers WHERE email = :email"),
                    {"email": body.user_id},
                )
            ).first()
            developer_id = dev_row[0] if dev_row else None
        except Exception:
            pass  # developers table may not exist post-migration

    member = TeamMember(
        team_id=team_id, user_id=body.user_id, role=body.role, developer_id=developer_id
    )
    session.add(member)

    # Bug 1 fix: set primary_team_id on the user (first assignment wins)
    resolved_uid: str | None = None
    if body.user_id and "-" in body.user_id:
        resolved_uid = body.user_id  # already a UUID string
    elif body.user_id and "@" in body.user_id:
        uid_row = (
            await session.execute(
                text("SELECT id::text FROM users WHERE email = :e"),
                {"e": body.user_id},
            )
        ).first()
        resolved_uid = str(uid_row[0]) if uid_row else None

    if resolved_uid:
        await session.execute(
            text("""
                UPDATE users SET primary_team_id = CAST(:tid AS uuid)
                WHERE id = CAST(:uid AS uuid) AND primary_team_id IS NULL
            """),
            {"tid": str(team_id), "uid": resolved_uid},
        )

    await audit.record(
        session,
        request,
        "add_member",
        "team_member",
        details={"team_id": str(team_id), "user_id": body.user_id, "role": body.role},
    )
    await session.commit()

    # Bug 2 fix: invalidate cached session so get_current_user will reload from DB
    if resolved_uid:
        redis = request.app.state.redis
        await redis.setex(f"user_team_changed:{resolved_uid}", 600, "1")

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
        select(TeamMember).where(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    member.role = body.role
    await audit.record(
        session,
        request,
        "update_member_role",
        "team_member",
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
        select(TeamMember).where(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    await audit.record(
        session,
        request,
        "remove_member",
        "team_member",
        details={"team_id": str(team_id), "user_id": user_id},
    )
    await session.delete(member)
    await session.commit()
