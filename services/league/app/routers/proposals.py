# services/league/app/routers/proposals.py
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin_auth, require_dev_auth
from app.db import get_session

router = APIRouter(prefix="/proposals", tags=["proposals"])


class ProposalCreate(BaseModel):
    title: str
    goal: str
    notes: str = ""


class ProposalReview(BaseModel):
    status: str  # "approved" or "rejected"
    reviewer_notes: str = ""


@router.get("")
async def list_proposals(
    session: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin_auth),
):
    result = await session.execute(text("""
        SELECT p.*, u.email AS proposer_name
        FROM league_challenge_proposals p
        JOIN users u ON u.id = p.proposed_by
        ORDER BY p.created_at DESC
    """))
    return [
        {
            "id": str(r["id"]),
            "title": r["title"],
            "goal": r["goal"],
            "notes": r["notes"],
            "status": r["status"],
            "proposer_name": r["proposer_name"],
            "proposed_by": str(r["proposed_by"]),
            "reviewed_by": str(r["reviewed_by"]) if r["reviewed_by"] else None,
            "reviewer_notes": r["reviewer_notes"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in result.mappings().all()
    ]


@router.post("", status_code=201)
async def create_proposal(
    body: ProposalCreate,
    session: AsyncSession = Depends(get_session),
    user=Depends(require_dev_auth),
):
    result = await session.execute(text("""
        INSERT INTO league_challenge_proposals (proposed_by, title, goal, notes)
        VALUES (:uid, :title, :goal, :notes)
        RETURNING id
    """), {"uid": user["user_id"], "title": body.title, "goal": body.goal, "notes": body.notes})
    await session.commit()
    return {"id": str(result.scalar()), "status": "proposed"}


@router.patch("/{proposal_id}/review")
async def review_proposal(
    proposal_id: UUID,
    body: ProposalReview,
    session: AsyncSession = Depends(get_session),
    admin=Depends(require_admin_auth),
):
    if body.status not in ("approved", "rejected"):
        raise HTTPException(status_code=422, detail="status must be 'approved' or 'rejected'")
    result = await session.execute(text("""
        UPDATE league_challenge_proposals
        SET status = :status, reviewed_by = :reviewer, reviewer_notes = :notes
        WHERE id = :id
        RETURNING id, status
    """), {
        "status": body.status,
        "reviewer": admin["user_id"],
        "notes": body.reviewer_notes,
        "id": str(proposal_id),
    })
    await session.commit()
    row = result.mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return {"id": str(row["id"]), "status": row["status"]}
