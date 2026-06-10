# services/league/app/routers/leaderboard.py
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_dev_auth
from app.db import get_session

router = APIRouter(tags=["leaderboard"])


@router.get("/seasons/{season_id}/leaderboard")
async def get_leaderboard(
    season_id: UUID,
    session: AsyncSession = Depends(get_session),
    _user=Depends(require_dev_auth),
):
    result = await session.execute(
        text("""
        SELECT
            lb.engineer_id,
            u.email,
            u.display_name,
            n_team.name AS team_name,
            n_area.name AS area_name,
            lb.composite_score,
            lb.rank,
            lb.points_earned,
            lb.updated_at
        FROM league_leaderboard lb
        JOIN users u ON u.id = lb.engineer_id
        LEFT JOIN organization_nodes n_team ON n_team.id = u.primary_node_id
        LEFT JOIN organization_nodes n_area ON n_area.id = n_team.parent_id
        WHERE lb.season_id = :sid
        ORDER BY lb.composite_score DESC
    """),
        {"sid": str(season_id)},
    )
    rows = result.mappings().all()
    return [
        {
            "engineer_id": str(r["engineer_id"]),
            "email": r["email"],
            "display_name": r["display_name"],
            "team_name": r["team_name"],
            "area_name": r["area_name"],
            "composite_score": float(r["composite_score"]),
            "rank": r["rank"],
            "points_earned": r["points_earned"],
            "updated_at": r["updated_at"].isoformat() if hasattr(r["updated_at"], "isoformat") else r["updated_at"],
        }
        for r in rows
    ]


@router.get("/seasons/{season_id}/leaderboard/me")
async def my_rank(
    season_id: UUID,
    session: AsyncSession = Depends(get_session),
    user=Depends(require_dev_auth),
):
    row = (
        (
            await session.execute(
                text("""
        SELECT composite_score, rank, points_earned
        FROM league_leaderboard
        WHERE season_id = :sid AND engineer_id = :uid
    """),
                {"sid": str(season_id), "uid": user["user_id"]},
            )
        )
        .mappings()
        .one_or_none()
    )
    if not row:
        return {"rank": None, "composite_score": 0.0, "points_earned": 0}
    return {
        "rank": row["rank"],
        "composite_score": float(row["composite_score"]),
        "points_earned": row["points_earned"],
    }
