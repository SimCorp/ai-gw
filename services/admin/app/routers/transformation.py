"""
Agentic transformation endpoints.

Developer-facing:
  GET  /dev-auth/me/transformation   — personal score, achievements, rank
  POST /dev-auth/me/leaderboard       — opt in / out of leaderboard

Admin-facing:
  GET  /admin/transformation          — org + team + individual scores
  POST /admin/transformation/classify — trigger classifier on demand
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.jobs.agentic_classifier import run_classifier
from app.routers.admin_auth import get_admin_session
from app.routers.dev_auth import _get_current_developer

dev_router = APIRouter(prefix="/dev-auth/me", tags=["transformation"])
admin_router = APIRouter(prefix="/admin/transformation", tags=["transformation-admin"])

# ---------------------------------------------------------------------------
# Score helpers
# ---------------------------------------------------------------------------

_SCORE_SQL = """
WITH base AS (
    SELECT
        s.session_type,
        s.tool_invocations,
        s.turn_count,
        s.produced_commit,
        s.total_cost
    FROM sessions s
    WHERE s.developer_id = CAST(:dev_id AS uuid)
      AND s.first_request_at >= NOW() - INTERVAL '30 days'
      AND s.session_type IS NOT NULL
),
totals AS (
    SELECT
        COUNT(*)                                                              AS total_sessions,
        COALESCE(SUM(total_cost), 0)                                         AS total_cost,
        COUNT(*) FILTER (WHERE session_type IN ('agentic','autonomous'))     AS agentic_sessions,
        COALESCE(SUM(total_cost) FILTER (WHERE session_type IN ('agentic','autonomous')), 0) AS agentic_cost,
        COALESCE(AVG(tool_invocations::float / GREATEST(turn_count,1)), 0)   AS avg_tool_density,
        COUNT(*) FILTER (WHERE produced_commit AND session_type IN ('agentic','autonomous')) AS agent_commits,
        COUNT(*) FILTER (WHERE session_type IN ('agentic','autonomous') AND produced_commit IS NOT NULL) AS agent_sessions_with_outcome
    FROM base
)
SELECT
    total_sessions,
    agentic_sessions,
    total_cost,
    agentic_cost,
    avg_tool_density,
    agent_commits,
    agent_sessions_with_outcome,
    CASE WHEN total_sessions > 0
         THEN ROUND(agentic_sessions::numeric / total_sessions * 100, 1) END AS agentic_session_pct,
    CASE WHEN total_cost > 0
         THEN ROUND(agentic_cost::numeric / total_cost * 100, 1) END       AS agentic_cost_pct
FROM totals
"""


def _compute_score(row) -> int:
    if not row or row["total_sessions"] == 0:
        return 0
    session_pct = float(row["agentic_session_pct"] or 0)
    cost_pct = float(row["agentic_cost_pct"] or 0)
    tool_density = min(float(row["avg_tool_density"] or 0) * 50, 100)  # cap at 100
    agent_sessions = int(row["agent_sessions_with_outcome"] or 0)
    commits = int(row["agent_commits"] or 0)
    commit_rate = (commits / max(agent_sessions, 1) * 100) if agent_sessions > 0 else 0

    score = (
        session_pct * 0.40 +
        cost_pct    * 0.30 +
        tool_density * 0.15 +
        commit_rate  * 0.15
    )
    return min(100, round(score))


# ---------------------------------------------------------------------------
# Developer endpoints
# ---------------------------------------------------------------------------

@dev_router.get("/transformation")
async def my_transformation(
    developer: dict = Depends(_get_current_developer),
    session: AsyncSession = Depends(get_session),
    request: Request = None,
):
    dev_id = developer["developer_id"]

    stats = (await session.execute(text(_SCORE_SQL), {"dev_id": dev_id})).mappings().one()
    score = _compute_score(stats)

    achievements = (await session.execute(
        text("""
            SELECT achievement, earned_at
            FROM developer_achievements
            WHERE developer_id = CAST(:dev_id AS uuid)
            ORDER BY earned_at
        """),
        {"dev_id": dev_id},
    )).mappings().all()

    # Weekly breakdown (last 8 weeks)
    weekly = (await session.execute(
        text("""
            SELECT
                date_trunc('week', first_request_at)::date AS week,
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE session_type IN ('agentic','autonomous')) AS agentic
            FROM sessions
            WHERE developer_id = CAST(:dev_id AS uuid)
              AND first_request_at >= NOW() - INTERVAL '8 weeks'
              AND session_type IS NOT NULL
            GROUP BY 1 ORDER BY 1
        """),
        {"dev_id": dev_id},
    )).mappings().all()

    # Leaderboard opt-in status
    opt_ins = (await session.execute(
        text("""
            SELECT scope FROM developer_leaderboard_opt_in
            WHERE developer_id = CAST(:dev_id AS uuid)
        """),
        {"dev_id": dev_id},
    )).scalars().all()

    # Rank if opted in
    rank_team = rank_company = None
    team_id = developer.get("team_id")

    if "team" in opt_ins and team_id:
        rank_row = (await session.execute(
            text("""
                WITH scores AS (
                    SELECT s.developer_id,
                           COUNT(*) FILTER (WHERE s.session_type IN ('agentic','autonomous'))::float
                               / GREATEST(COUNT(*), 1) * 100 AS pct
                    FROM sessions s
                    JOIN developers d ON d.id = s.developer_id
                    WHERE d.team_id = CAST(:team_id AS uuid)
                      AND s.first_request_at >= NOW() - INTERVAL '30 days'
                      AND s.session_type IS NOT NULL
                    GROUP BY s.developer_id
                )
                SELECT COUNT(*) + 1 AS rank, (SELECT COUNT(*) FROM scores) AS total
                FROM scores
                WHERE pct > (SELECT pct FROM scores WHERE developer_id = CAST(:dev_id AS uuid))
            """),
            {"team_id": team_id, "dev_id": dev_id},
        )).mappings().one_or_none()
        if rank_row:
            rank_team = {"rank": int(rank_row["rank"]), "total": int(rank_row["total"])}

    if "company" in opt_ins:
        rank_row = (await session.execute(
            text("""
                WITH scores AS (
                    SELECT s.developer_id,
                           COUNT(*) FILTER (WHERE s.session_type IN ('agentic','autonomous'))::float
                               / GREATEST(COUNT(*), 1) * 100 AS pct
                    FROM sessions s
                    WHERE s.first_request_at >= NOW() - INTERVAL '30 days'
                      AND s.session_type IS NOT NULL
                      AND s.developer_id IS NOT NULL
                    GROUP BY s.developer_id
                )
                SELECT COUNT(*) + 1 AS rank, (SELECT COUNT(*) FROM scores) AS total
                FROM scores
                WHERE pct > (SELECT pct FROM scores WHERE developer_id = CAST(:dev_id AS uuid))
            """),
            {"dev_id": dev_id},
        )).mappings().one_or_none()
        if rank_row:
            rank_company = {"rank": int(rank_row["rank"]), "total": int(rank_row["total"])}

    return {
        "score": score,
        "stats": {
            "total_sessions": int(stats["total_sessions"] or 0),
            "agentic_sessions": int(stats["agentic_sessions"] or 0),
            "agentic_session_pct": float(stats["agentic_session_pct"] or 0),
            "agentic_cost_pct": float(stats["agentic_cost_pct"] or 0),
            "agent_commits": int(stats["agent_commits"] or 0),
        },
        "achievements": [
            {"achievement": r["achievement"], "earned_at": r["earned_at"].isoformat()}
            for r in achievements
        ],
        "weekly": [
            {
                "week": str(r["week"]),
                "total": int(r["total"]),
                "agentic": int(r["agentic"]),
                "agentic_pct": round(int(r["agentic"]) / max(int(r["total"]), 1) * 100, 1),
            }
            for r in weekly
        ],
        "leaderboard": {
            "opted_in": list(opt_ins),
            "rank_team": rank_team,
            "rank_company": rank_company,
        },
    }


class LeaderboardUpdate(BaseModel):
    scope: str  # "team" or "company"
    opt_in: bool


@dev_router.post("/leaderboard")
async def update_leaderboard_opt_in(
    body: LeaderboardUpdate,
    developer: dict = Depends(_get_current_developer),
    session: AsyncSession = Depends(get_session),
):
    if body.scope not in ("team", "company"):
        raise HTTPException(status_code=422, detail="scope must be 'team' or 'company'")
    dev_id = developer["developer_id"]
    if body.opt_in:
        await session.execute(
            text("""
                INSERT INTO developer_leaderboard_opt_in (developer_id, scope)
                VALUES (CAST(:dev_id AS uuid), :scope)
                ON CONFLICT DO NOTHING
            """),
            {"dev_id": dev_id, "scope": body.scope},
        )
    else:
        await session.execute(
            text("""
                DELETE FROM developer_leaderboard_opt_in
                WHERE developer_id = CAST(:dev_id AS uuid) AND scope = :scope
            """),
            {"dev_id": dev_id, "scope": body.scope},
        )
    await session.commit()
    return {"ok": True, "scope": body.scope, "opted_in": body.opt_in}


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------

@admin_router.get("")
async def org_transformation(
    admin: dict = Depends(get_admin_session),
    session: AsyncSession = Depends(get_session),
):
    # Org-level weekly adoption (last 12 weeks)
    org_weekly = (await session.execute(
        text("""
            SELECT
                date_trunc('week', first_request_at)::date AS week,
                COUNT(*) AS total_sessions,
                COUNT(*) FILTER (WHERE session_type IN ('agentic','autonomous')) AS agentic_sessions,
                COUNT(DISTINCT developer_id) AS active_devs,
                COUNT(DISTINCT developer_id) FILTER (WHERE session_type IN ('agentic','autonomous')) AS agentic_devs
            FROM sessions
            WHERE first_request_at >= NOW() - INTERVAL '12 weeks'
              AND session_type IS NOT NULL
            GROUP BY 1 ORDER BY 1
        """)
    )).mappings().all()

    # Per-team breakdown
    teams = (await session.execute(
        text("""
            SELECT
                d.team_id::text,
                t.name AS team_name,
                COUNT(DISTINCT d.id) AS dev_count,
                COUNT(DISTINCT d.id) FILTER (
                    WHERE EXISTS (
                        SELECT 1 FROM sessions s
                        WHERE s.developer_id = d.id
                          AND s.session_type IN ('agentic','autonomous')
                          AND s.first_request_at >= NOW() - INTERVAL '30 days'
                    )
                ) AS agentic_devs_30d,
                ROUND(
                    COUNT(s.session_trace_id) FILTER (WHERE s.session_type IN ('agentic','autonomous'))::numeric
                    / NULLIF(COUNT(s.session_trace_id), 0) * 100, 1
                ) AS agentic_session_pct_30d
            FROM developers d
            LEFT JOIN organization_nodes t ON t.id = d.team_id
            LEFT JOIN sessions s ON s.developer_id = d.id
                AND s.first_request_at >= NOW() - INTERVAL '30 days'
                AND s.session_type IS NOT NULL
            WHERE d.team_id IS NOT NULL
            GROUP BY d.team_id, t.name
            ORDER BY agentic_session_pct_30d DESC NULLS LAST
        """)
    )).mappings().all()

    # Individual developer scores
    developers = (await session.execute(
        text("""
            SELECT
                d.id::text AS developer_id,
                d.email,
                d.display_name,
                d.team_id::text,
                t.name AS team_name,
                COUNT(s.session_trace_id) AS total_sessions_30d,
                COUNT(s.session_trace_id) FILTER (WHERE s.session_type IN ('agentic','autonomous')) AS agentic_sessions_30d,
                ROUND(
                    COUNT(s.session_trace_id) FILTER (WHERE s.session_type IN ('agentic','autonomous'))::numeric
                    / NULLIF(COUNT(s.session_trace_id), 0) * 100, 1
                ) AS agentic_pct,
                COUNT(da.achievement) AS achievement_count
            FROM developers d
            LEFT JOIN organization_nodes t ON t.id = d.team_id
            LEFT JOIN sessions s ON s.developer_id = d.id
                AND s.first_request_at >= NOW() - INTERVAL '30 days'
                AND s.session_type IS NOT NULL
            LEFT JOIN developer_achievements da ON da.developer_id = d.id
            GROUP BY d.id, d.email, d.display_name, d.team_id, t.name
            ORDER BY agentic_pct DESC NULLS LAST
        """)
    )).mappings().all()

    return {
        "org_weekly": [
            {
                "week": str(r["week"]),
                "total_sessions": int(r["total_sessions"]),
                "agentic_sessions": int(r["agentic_sessions"]),
                "active_devs": int(r["active_devs"]),
                "agentic_devs": int(r["agentic_devs"]),
                "agentic_pct": round(int(r["agentic_sessions"]) / max(int(r["total_sessions"]), 1) * 100, 1),
            }
            for r in org_weekly
        ],
        "teams": [
            {
                "team_id": r["team_id"],
                "team_name": r["team_name"],
                "dev_count": int(r["dev_count"]),
                "agentic_devs_30d": int(r["agentic_devs_30d"] or 0),
                "agentic_session_pct_30d": float(r["agentic_session_pct_30d"] or 0),
                "laggard": float(r["agentic_session_pct_30d"] or 0) < 20,
            }
            for r in teams
        ],
        "developers": [
            {
                "developer_id": r["developer_id"],
                "email": r["email"],
                "display_name": r["display_name"],
                "team_id": r["team_id"],
                "team_name": r["team_name"],
                "total_sessions_30d": int(r["total_sessions_30d"] or 0),
                "agentic_sessions_30d": int(r["agentic_sessions_30d"] or 0),
                "agentic_pct": float(r["agentic_pct"] or 0),
                "achievement_count": int(r["achievement_count"] or 0),
            }
            for r in developers
        ],
    }


@admin_router.post("/classify")
async def trigger_classify(
    admin: dict = Depends(get_admin_session),
    session: AsyncSession = Depends(get_session),
):
    """Trigger the session classifier and achievement engine on demand."""
    result = await run_classifier(session)
    return result
