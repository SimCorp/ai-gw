# services/league/app/routers/challenges.py
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin_auth, require_dev_auth
from app.db import get_session

router = APIRouter(tags=["challenges"])

_PUBLIC_COLS = "id, season_id, title, goal, training_inputs, allowed_models, max_tokens_budget, max_league_attempts, scores_revealed_at, status, proposed_by, created_at"


class ChallengeCreate(BaseModel):
    title: str
    goal: str
    training_inputs: list[dict] = []
    hidden_test_suite: list[dict] = []
    allowed_models: list[str] = ["claude-sonnet-4-6"]
    max_tokens_budget: int = 4096
    max_league_attempts: int = 3


def _challenge_to_dict(row, include_hidden: bool = False) -> dict:
    d = {
        "id": str(row["id"]),
        "season_id": str(row["season_id"]),
        "title": row["title"],
        "goal": row["goal"],
        "training_inputs": row["training_inputs"],
        "allowed_models": list(row["allowed_models"]),
        "max_tokens_budget": row["max_tokens_budget"],
        "max_league_attempts": row["max_league_attempts"],
        "scores_revealed_at": row["scores_revealed_at"].isoformat() if row["scores_revealed_at"] else None,
        "status": row["status"],
        "proposed_by": str(row["proposed_by"]) if row["proposed_by"] else None,
        "created_at": row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else row["created_at"],
    }
    if include_hidden:
        d["hidden_test_suite"] = row.get("hidden_test_suite", [])
    return d


@router.get("/seasons/{season_id}/challenges")
async def list_challenges(
    season_id: UUID,
    session: AsyncSession = Depends(get_session),
    _user=Depends(require_dev_auth),
):
    result = await session.execute(text(f"""
        SELECT {_PUBLIC_COLS} FROM league_challenges
        WHERE season_id = :season_id
        ORDER BY created_at
    """), {"season_id": str(season_id)})
    return [_challenge_to_dict(row) for row in result.mappings().all()]


@router.get("/challenges/{challenge_id}")
async def get_challenge(
    challenge_id: UUID,
    session: AsyncSession = Depends(get_session),
    _user=Depends(require_dev_auth),
):
    row = (await session.execute(text(f"""
        SELECT {_PUBLIC_COLS} FROM league_challenges WHERE id = :id
    """), {"id": str(challenge_id)})).mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Challenge not found")
    return _challenge_to_dict(row, include_hidden=False)


@router.post("/seasons/{season_id}/challenges", status_code=201)
async def create_challenge(
    season_id: UUID,
    body: ChallengeCreate,
    session: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin_auth),
):
    result = await session.execute(text("""
        INSERT INTO league_challenges
          (season_id, title, goal, training_inputs, hidden_test_suite,
           allowed_models, max_tokens_budget, max_league_attempts)
        VALUES
          (:season_id, :title, :goal,
           CAST(:training_inputs AS jsonb), CAST(:hidden_test_suite AS jsonb),
           :allowed_models, :max_tokens_budget, :max_league_attempts)
        RETURNING *
    """), {
        "season_id": str(season_id),
        "title": body.title,
        "goal": body.goal,
        "training_inputs": json.dumps(body.training_inputs),
        "hidden_test_suite": json.dumps(body.hidden_test_suite),
        "allowed_models": body.allowed_models,
        "max_tokens_budget": body.max_tokens_budget,
        "max_league_attempts": body.max_league_attempts,
    })
    await session.commit()
    row = result.mappings().one()
    return _challenge_to_dict(row, include_hidden=True)


@router.patch("/challenges/{challenge_id}/status")
async def update_challenge_status(
    challenge_id: UUID,
    body: dict,
    session: AsyncSession = Depends(get_session),
    _admin=Depends(require_admin_auth),
):
    new_status = body.get("status")
    if new_status not in ("draft", "active", "closed"):
        raise HTTPException(status_code=422, detail="status must be draft, active, or closed")
    await session.execute(text(
        "UPDATE league_challenges SET status = :s, scores_revealed_at = CASE WHEN :s = 'closed' THEN NOW() ELSE scores_revealed_at END WHERE id = :id"
    ), {"s": new_status, "id": str(challenge_id)})

    if new_status == "closed":
        await session.execute(text("""
            WITH ranked AS (
                SELECT season_id, engineer_id,
                       RANK() OVER (PARTITION BY season_id ORDER BY composite_score DESC) AS new_rank
                FROM league_leaderboard
                WHERE season_id = (SELECT season_id FROM league_challenges WHERE id = :cid)
            )
            UPDATE league_leaderboard lb
            SET rank = ranked.new_rank
            FROM ranked
            WHERE lb.season_id = ranked.season_id AND lb.engineer_id = ranked.engineer_id
        """), {"cid": str(challenge_id)})

    await session.commit()
    return {"id": str(challenge_id), "status": new_status}
