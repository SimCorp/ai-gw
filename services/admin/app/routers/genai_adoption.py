import asyncio
import json
import logging

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session

log = logging.getLogger(__name__)

router = APIRouter(prefix="/genai-adoption", tags=["genai-adoption"])


# ── helpers ───────────────────────────────────────────────────────────────────

def _f(v) -> float | None:
    return float(v) if v is not None else None


# ── Adoption ──────────────────────────────────────────────────────────────────

@router.get("/adoption/summary")
async def adoption_summary(
    period_days: int = Query(default=30, ge=7, le=365),
    session: AsyncSession = Depends(get_session),
):
    total_row = await session.execute(
        text("SELECT COUNT(*) AS total FROM developers")
    )
    total = int(total_row.scalar() or 0)

    rows = (await session.execute(text(f"""
        WITH active_devs AS (
            SELECT developer_id,
                   COUNT(DISTINCT date) AS active_days
            FROM developer_activity_log
            WHERE date >= CURRENT_DATE - INTERVAL '{period_days} days'
            GROUP BY developer_id
        )
        SELECT
            COUNT(*) AS active_users,
            COUNT(CASE WHEN active_days BETWEEN 1 AND 3  THEN 1 END) AS rare,
            COUNT(CASE WHEN active_days BETWEEN 4 AND 14 THEN 1 END) AS occasional,
            COUNT(CASE WHEN active_days >= 15            THEN 1 END) AS regular
        FROM active_devs
    """))).mappings().one()

    active = int(rows["active_users"])
    return {
        "period_days": period_days,
        "total_licensed_developers": total,
        "active_users": active,
        "adoption_rate_pct": round(active * 100.0 / max(total, 1), 1),
        "frequency_buckets": {
            "rare":       int(rows["rare"]),
            "occasional": int(rows["occasional"]),
            "regular":    int(rows["regular"]),
        },
    }


@router.get("/adoption/by-team")
async def adoption_by_team(
    period_days: int = Query(default=30, ge=7, le=365),
    session: AsyncSession = Depends(get_session),
):
    rows = (await session.execute(text(f"""
        WITH active_devs AS (
            SELECT developer_id,
                   COUNT(DISTINCT date) AS active_days
            FROM developer_activity_log
            WHERE date >= CURRENT_DATE - INTERVAL '{period_days} days'
            GROUP BY developer_id
        ),
        team_licensed AS (
            SELECT team_id, COUNT(*) AS licensed_count
            FROM developers
            WHERE team_id IS NOT NULL
            GROUP BY team_id
        )
        SELECT
            t.id                                  AS team_id,
            t.name                                AS team_name,
            COALESCE(tl.licensed_count, 0)        AS licensed_count,
            COUNT(ad.developer_id)                AS active_users,
            COUNT(CASE WHEN ad.active_days BETWEEN 1 AND 3  THEN 1 END) AS rare,
            COUNT(CASE WHEN ad.active_days BETWEEN 4 AND 14 THEN 1 END) AS occasional,
            COUNT(CASE WHEN ad.active_days >= 15             THEN 1 END) AS regular
        FROM organization_nodes t
        LEFT JOIN developers d         ON d.team_id = t.id
        LEFT JOIN active_devs ad       ON ad.developer_id = d.id
        LEFT JOIN team_licensed tl     ON tl.team_id = t.id
        WHERE t.type = 'team'
        GROUP BY t.id, t.name, tl.licensed_count
        ORDER BY active_users DESC NULLS LAST
    """))).mappings().all()

    return [
        {
            "team_id": str(r["team_id"]),
            "team_name": r["team_name"],
            "licensed_count": int(r["licensed_count"]),
            "active_users": int(r["active_users"]),
            "adoption_rate_pct": round(
                int(r["active_users"]) * 100.0 / max(int(r["licensed_count"]), 1), 1
            ),
            "frequency_buckets": {
                "rare":       int(r["rare"]),
                "occasional": int(r["occasional"]),
                "regular":    int(r["regular"]),
            },
        }
        for r in rows
    ]


@router.get("/adoption/trend")
async def adoption_trend(
    period_days: int = Query(default=90, ge=7, le=365),
    session: AsyncSession = Depends(get_session),
):
    rows = (await session.execute(text(f"""
        SELECT
            date_trunc('week', date::timestamptz) AS week_start,
            COUNT(DISTINCT developer_id)          AS active_users
        FROM developer_activity_log
        WHERE date >= CURRENT_DATE - INTERVAL '{period_days} days'
        GROUP BY week_start
        ORDER BY week_start
    """))).mappings().all()

    return [
        {"week_start": r["week_start"].isoformat(), "active_users": int(r["active_users"])}
        for r in rows
    ]


# ── Productivity ──────────────────────────────────────────────────────────────

@router.get("/productivity/summary")
async def productivity_summary(
    period_days: int = Query(default=30, ge=7, le=365),
    session: AsyncSession = Depends(get_session),
):
    rows = (await session.execute(text(f"""
        WITH cohorts AS (
            SELECT developer_id,
                   COUNT(DISTINCT date) AS active_days
            FROM developer_activity_log
            WHERE date >= CURRENT_DATE - INTERVAL '{period_days} days'
            GROUP BY developer_id
        ),
        session_stats AS (
            SELECT
                s.developer_id,
                AVG(s.quality_score)         AS avg_quality,
                AVG(s.avg_inter_request_s)   AS avg_inter_s,
                AVG(s.turn_count)            AS avg_turns,
                AVG(s.tool_invocations)      AS avg_tools,
                COUNT(s.session_trace_id)    AS sessions
            FROM sessions s
            WHERE s.first_request_at >= NOW() - INTERVAL '{period_days} days'
              AND s.developer_id IS NOT NULL
            GROUP BY s.developer_id
        )
        SELECT
            CASE WHEN c.active_days >= 15 THEN 'high' ELSE 'low' END AS cohort,
            ROUND(AVG(ss.avg_quality)::numeric,   2) AS avg_quality_score,
            ROUND(AVG(ss.avg_inter_s)::numeric,   0) AS avg_inter_request_s,
            ROUND(AVG(ss.avg_turns)::numeric,     1) AS avg_turn_count,
            ROUND(AVG(ss.avg_tools)::numeric,     1) AS avg_tool_invocations,
            SUM(ss.sessions)                         AS session_count
        FROM session_stats ss
        JOIN cohorts c ON c.developer_id = ss.developer_id
        WHERE c.active_days >= 15 OR c.active_days < 4
        GROUP BY cohort
    """))).mappings().all()

    result: dict = {"high_adoption": {}, "low_adoption": {}}
    for r in rows:
        key = "high_adoption" if r["cohort"] == "high" else "low_adoption"
        result[key] = {
            "avg_quality_score":    _f(r["avg_quality_score"]),
            "avg_inter_request_s":  _f(r["avg_inter_request_s"]),
            "avg_turn_count":       _f(r["avg_turn_count"]),
            "avg_tool_invocations": _f(r["avg_tool_invocations"]),
            "session_count":        int(r["session_count"]),
        }
    return result


@router.get("/productivity/by-team")
async def productivity_by_team(
    period_days: int = Query(default=30, ge=7, le=365),
    session: AsyncSession = Depends(get_session),
):
    rows = (await session.execute(text(f"""
        SELECT
            t.id                                                   AS team_id,
            t.name                                                 AS team_name,
            ROUND(AVG(s.quality_score)::numeric,        2)        AS avg_quality_score,
            ROUND(AVG(s.avg_inter_request_s)::numeric,  0)        AS avg_inter_request_s,
            ROUND(AVG(s.turn_count)::numeric,           1)        AS avg_turn_count,
            COUNT(s.session_trace_id)                              AS session_count
        FROM organization_nodes t
        LEFT JOIN sessions s ON CAST(t.id AS TEXT) = s.team_id
          AND s.first_request_at >= NOW() - INTERVAL '{period_days} days'
        WHERE t.type = 'team'
        GROUP BY t.id, t.name
        ORDER BY avg_quality_score DESC NULLS LAST
    """))).mappings().all()

    return [
        {
            "team_id":             str(r["team_id"]),
            "team_name":           r["team_name"],
            "avg_quality_score":   _f(r["avg_quality_score"]),
            "avg_inter_request_s": _f(r["avg_inter_request_s"]),
            "avg_turn_count":      _f(r["avg_turn_count"]),
            "session_count":       int(r["session_count"]),
        }
        for r in rows
    ]


@router.get("/productivity/trend")
async def productivity_trend(
    period_days: int = Query(default=90, ge=7, le=365),
    session: AsyncSession = Depends(get_session),
):
    rows = (await session.execute(text(f"""
        WITH cohorts AS (
            SELECT developer_id, COUNT(DISTINCT date) AS active_days
            FROM developer_activity_log
            WHERE date >= CURRENT_DATE - INTERVAL '{period_days} days'
            GROUP BY developer_id
        )
        SELECT
            date_trunc('week', s.first_request_at) AS week_start,
            ROUND(AVG(CASE WHEN c.active_days >= 15
                THEN s.quality_score END)::numeric, 2) AS high_adoption_quality,
            ROUND(AVG(CASE WHEN c.active_days < 4
                THEN s.quality_score END)::numeric, 2) AS low_adoption_quality
        FROM sessions s
        LEFT JOIN cohorts c ON c.developer_id = s.developer_id
        WHERE s.first_request_at >= NOW() - INTERVAL '{period_days} days'
        GROUP BY week_start
        ORDER BY week_start
    """))).mappings().all()

    return [
        {
            "week_start":           r["week_start"].isoformat(),
            "high_adoption_quality": _f(r["high_adoption_quality"]),
            "low_adoption_quality":  _f(r["low_adoption_quality"]),
        }
        for r in rows
    ]


# ── Code Quality ──────────────────────────────────────────────────────────────

@router.get("/quality/summary")
async def quality_summary(
    period_days: int = Query(default=30, ge=7, le=365),
    session: AsyncSession = Depends(get_session),
):
    rows = (await session.execute(text(f"""
        WITH cohorts AS (
            SELECT developer_id, COUNT(DISTINCT date) AS active_days
            FROM developer_activity_log
            WHERE date >= CURRENT_DATE - INTERVAL '{period_days} days'
            GROUP BY developer_id
        ),
        session_stats AS (
            SELECT
                s.developer_id,
                AVG(CASE WHEN s.turn_count > 0
                    THEN s.error_count::float / s.turn_count END) AS error_rate,
                AVG(CASE WHEN s.turn_count > 0
                    THEN s.retry_count::float / s.turn_count END) AS retry_rate
            FROM sessions s
            WHERE s.first_request_at >= NOW() - INTERVAL '{period_days} days'
              AND s.developer_id IS NOT NULL
            GROUP BY s.developer_id
        ),
        cache_stats AS (
            SELECT
                developer_id,
                SUM(cache_hits)::float / GREATEST(SUM(request_count), 1) AS cache_hit_rate
            FROM developer_activity_log
            WHERE date >= CURRENT_DATE - INTERVAL '{period_days} days'
            GROUP BY developer_id
        )
        SELECT
            CASE WHEN c.active_days >= 15 THEN 'high' ELSE 'low' END AS cohort,
            ROUND((AVG(ss.error_rate) * 100)::numeric, 1)  AS avg_error_rate_pct,
            ROUND((AVG(ss.retry_rate) * 100)::numeric, 1)  AS avg_retry_rate_pct,
            ROUND((AVG(cs.cache_hit_rate) * 100)::numeric, 1) AS cache_hit_rate_pct
        FROM session_stats ss
        JOIN cohorts c ON c.developer_id = ss.developer_id
        LEFT JOIN cache_stats cs ON cs.developer_id = ss.developer_id
        WHERE c.active_days >= 15 OR c.active_days < 4
        GROUP BY cohort
    """))).mappings().all()

    result: dict = {"high_adoption": {}, "low_adoption": {}}
    for r in rows:
        key = "high_adoption" if r["cohort"] == "high" else "low_adoption"
        result[key] = {
            "avg_error_rate_pct":  _f(r["avg_error_rate_pct"]),
            "avg_retry_rate_pct":  _f(r["avg_retry_rate_pct"]),
            "cache_hit_rate_pct":  _f(r["cache_hit_rate_pct"]),
        }
    return result


@router.get("/quality/by-team")
async def quality_by_team(
    period_days: int = Query(default=30, ge=7, le=365),
    session: AsyncSession = Depends(get_session),
):
    rows = (await session.execute(text(f"""
        SELECT
            t.id AS team_id,
            t.name AS team_name,
            ROUND((AVG(CASE WHEN s.turn_count > 0
                THEN s.error_count::float / s.turn_count END) * 100)::numeric, 1) AS avg_error_rate_pct,
            ROUND((AVG(CASE WHEN s.turn_count > 0
                THEN s.retry_count::float / s.turn_count END) * 100)::numeric, 1) AS avg_retry_rate_pct,
            ROUND((
                SUM(dal.cache_hits)::float / GREATEST(SUM(dal.request_count), 1) * 100
            )::numeric, 1) AS cache_hit_rate_pct,
            COUNT(DISTINCT s.session_trace_id) AS session_count
        FROM organization_nodes t
        LEFT JOIN sessions s ON CAST(t.id AS TEXT) = s.team_id
          AND s.first_request_at >= NOW() - INTERVAL '{period_days} days'
        LEFT JOIN developers d ON d.team_id = t.id
        LEFT JOIN developer_activity_log dal ON dal.developer_id = d.id
          AND dal.date >= CURRENT_DATE - INTERVAL '{period_days} days'
        WHERE t.type = 'team'
        GROUP BY t.id, t.name
        ORDER BY avg_error_rate_pct ASC NULLS LAST
    """))).mappings().all()

    return [
        {
            "team_id":            str(r["team_id"]),
            "team_name":          r["team_name"],
            "avg_error_rate_pct": _f(r["avg_error_rate_pct"]),
            "avg_retry_rate_pct": _f(r["avg_retry_rate_pct"]),
            "cache_hit_rate_pct": _f(r["cache_hit_rate_pct"]),
            "session_count":      int(r["session_count"]),
            "high_error_flag":    (float(r["avg_error_rate_pct"]) > 10)
                                  if r["avg_error_rate_pct"] is not None else False,
        }
        for r in rows
    ]


@router.get("/quality/trend")
async def quality_trend(
    period_days: int = Query(default=90, ge=7, le=365),
    session: AsyncSession = Depends(get_session),
):
    rows = (await session.execute(text(f"""
        WITH cohorts AS (
            SELECT developer_id, COUNT(DISTINCT date) AS active_days
            FROM developer_activity_log
            WHERE date >= CURRENT_DATE - INTERVAL '{period_days} days'
            GROUP BY developer_id
        )
        SELECT
            date_trunc('week', s.first_request_at) AS week_start,
            ROUND((AVG(CASE WHEN c.active_days >= 15 AND s.turn_count > 0
                THEN s.error_count::float / s.turn_count * 100 END))::numeric, 1)
                AS high_adoption_error_pct,
            ROUND((AVG(CASE WHEN c.active_days < 4 AND s.turn_count > 0
                THEN s.error_count::float / s.turn_count * 100 END))::numeric, 1)
                AS low_adoption_error_pct
        FROM sessions s
        LEFT JOIN cohorts c ON c.developer_id = s.developer_id
        WHERE s.first_request_at >= NOW() - INTERVAL '{period_days} days'
        GROUP BY week_start
        ORDER BY week_start
    """))).mappings().all()

    return [
        {
            "week_start":              r["week_start"].isoformat(),
            "high_adoption_error_pct": _f(r["high_adoption_error_pct"]),
            "low_adoption_error_pct":  _f(r["low_adoption_error_pct"]),
        }
        for r in rows
    ]


# ── AI Insights ───────────────────────────────────────────────────────────────

_INSIGHTS_SYSTEM = """You are an expert engineering analytics advisor embedded in a GenAI adoption dashboard.
Your task is to analyse metrics about how ~2000 software engineers at a large financial-services firm
are using AI coding assistants (Claude Code / Copilot equivalents) via a central gateway.

Metrics you receive cover three dimensions:
- Adoption: how many developers are active and how frequently
- Productivity: session quality scores, inter-request timing, turn depth by cohort
- Code Quality: error rates, retry rates, cache hit rates by cohort

You will produce a concise, actionable analysis in valid JSON matching this schema exactly:
{
  "summary": "<2-3 sentence executive summary of the overall AI adoption health>",
  "highlights": ["<finding 1>", "<finding 2>", "<finding 3>"],
  "recommendations": ["<action 1>", "<action 2>", "<action 3>"],
  "risks": ["<risk or watch item 1>", "<risk or watch item 2>"]
}

Rules:
- Be specific — reference actual numbers from the data where they add weight
- Highlights: mix positive and negative findings
- Recommendations: must be concrete and actionable by an engineering platform team
- Risks: flag teams or metrics that need attention
- Return only valid JSON, no markdown, no commentary outside the JSON object"""


async def _gather_metrics(session: AsyncSession, period_days: int) -> dict:
    """Fetch all adoption/productivity/quality metrics in parallel."""

    async def _adoption_summary():
        total_row = await session.execute(text("SELECT COUNT(*) FROM developers"))
        total = int(total_row.scalar() or 0)
        row = (await session.execute(text(f"""
            WITH a AS (
                SELECT developer_id, COUNT(DISTINCT date) AS active_days
                FROM developer_activity_log
                WHERE date >= CURRENT_DATE - INTERVAL '{period_days} days'
                GROUP BY developer_id
            )
            SELECT COUNT(*) AS active_users,
                   COUNT(CASE WHEN active_days BETWEEN 1 AND 3  THEN 1 END) AS rare,
                   COUNT(CASE WHEN active_days BETWEEN 4 AND 14 THEN 1 END) AS occasional,
                   COUNT(CASE WHEN active_days >= 15            THEN 1 END) AS regular
            FROM a
        """))).mappings().one()
        active = int(row["active_users"])
        return {
            "total_developers": total,
            "active_users": active,
            "adoption_rate_pct": round(active * 100.0 / max(total, 1), 1),
            "rare": int(row["rare"]),
            "occasional": int(row["occasional"]),
            "regular": int(row["regular"]),
        }

    async def _productivity_summary():
        rows = (await session.execute(text(f"""
            WITH cohorts AS (
                SELECT developer_id, COUNT(DISTINCT date) AS active_days
                FROM developer_activity_log
                WHERE date >= CURRENT_DATE - INTERVAL '{period_days} days'
                GROUP BY developer_id
            ),
            ss AS (
                SELECT s.developer_id,
                    AVG(s.quality_score) AS q,
                    AVG(s.avg_inter_request_s) AS inter_s,
                    AVG(s.turn_count) AS turns,
                    COUNT(s.session_trace_id) AS sessions
                FROM sessions s
                WHERE s.first_request_at >= NOW() - INTERVAL '{period_days} days'
                  AND s.developer_id IS NOT NULL
                GROUP BY s.developer_id
            )
            SELECT CASE WHEN c.active_days >= 15 THEN 'high' ELSE 'low' END AS cohort,
                   ROUND(AVG(ss.q)::numeric, 2)       AS avg_quality_score,
                   ROUND(AVG(ss.inter_s)::numeric, 0) AS avg_inter_request_s,
                   ROUND(AVG(ss.turns)::numeric, 1)   AS avg_turn_count,
                   SUM(ss.sessions)                   AS session_count
            FROM ss JOIN cohorts c ON c.developer_id = ss.developer_id
            WHERE c.active_days >= 15 OR c.active_days < 4
            GROUP BY cohort
        """))).mappings().all()
        out: dict = {}
        for r in rows:
            out[r["cohort"]] = {
                "avg_quality_score": _f(r["avg_quality_score"]),
                "avg_inter_request_s": _f(r["avg_inter_request_s"]),
                "avg_turn_count": _f(r["avg_turn_count"]),
                "session_count": int(r["session_count"]),
            }
        return out

    async def _quality_summary():
        rows = (await session.execute(text(f"""
            WITH cohorts AS (
                SELECT developer_id, COUNT(DISTINCT date) AS active_days
                FROM developer_activity_log
                WHERE date >= CURRENT_DATE - INTERVAL '{period_days} days'
                GROUP BY developer_id
            ),
            ss AS (
                SELECT s.developer_id,
                    AVG(CASE WHEN s.turn_count > 0 THEN s.error_count::float / s.turn_count END) AS er,
                    AVG(CASE WHEN s.turn_count > 0 THEN s.retry_count::float / s.turn_count END) AS rr
                FROM sessions s
                WHERE s.first_request_at >= NOW() - INTERVAL '{period_days} days'
                  AND s.developer_id IS NOT NULL
                GROUP BY s.developer_id
            ),
            cs AS (
                SELECT developer_id,
                    SUM(cache_hits)::float / GREATEST(SUM(request_count), 1) AS chr
                FROM developer_activity_log
                WHERE date >= CURRENT_DATE - INTERVAL '{period_days} days'
                GROUP BY developer_id
            )
            SELECT CASE WHEN c.active_days >= 15 THEN 'high' ELSE 'low' END AS cohort,
                   ROUND((AVG(ss.er) * 100)::numeric, 1)  AS avg_error_rate_pct,
                   ROUND((AVG(ss.rr) * 100)::numeric, 1)  AS avg_retry_rate_pct,
                   ROUND((AVG(cs.chr) * 100)::numeric, 1) AS cache_hit_rate_pct
            FROM ss JOIN cohorts c ON c.developer_id = ss.developer_id
            LEFT JOIN cs ON cs.developer_id = ss.developer_id
            WHERE c.active_days >= 15 OR c.active_days < 4
            GROUP BY cohort
        """))).mappings().all()
        out: dict = {}
        for r in rows:
            out[r["cohort"]] = {
                "avg_error_rate_pct": _f(r["avg_error_rate_pct"]),
                "avg_retry_rate_pct": _f(r["avg_retry_rate_pct"]),
                "cache_hit_rate_pct": _f(r["cache_hit_rate_pct"]),
            }
        return out

    async def _team_summary():
        rows = (await session.execute(text(f"""
            WITH active_devs AS (
                SELECT developer_id, COUNT(DISTINCT date) AS active_days
                FROM developer_activity_log
                WHERE date >= CURRENT_DATE - INTERVAL '{period_days} days'
                GROUP BY developer_id
            )
            SELECT t.name AS team_name,
                   COUNT(DISTINCT d.id)        AS licensed_count,
                   COUNT(ad.developer_id)       AS active_users,
                   ROUND(AVG(s.quality_score)::numeric, 2) AS avg_quality,
                   ROUND((AVG(CASE WHEN s.turn_count > 0
                       THEN s.error_count::float / s.turn_count * 100 END))::numeric, 1) AS error_rate_pct
            FROM organization_nodes t
            LEFT JOIN developers d ON d.team_id = t.id
            LEFT JOIN active_devs ad ON ad.developer_id = d.id
            LEFT JOIN sessions s ON CAST(t.id AS TEXT) = s.team_id
              AND s.first_request_at >= NOW() - INTERVAL '{period_days} days'
            WHERE t.type = 'team'
            GROUP BY t.id, t.name
            HAVING COUNT(DISTINCT d.id) > 0
            ORDER BY active_users DESC NULLS LAST
            LIMIT 10
        """))).mappings().all()
        return [
            {
                "team": r["team_name"],
                "licensed": int(r["licensed_count"]),
                "active": int(r["active_users"]),
                "adoption_pct": round(int(r["active_users"]) * 100.0 / max(int(r["licensed_count"]), 1), 1),
                "avg_quality": _f(r["avg_quality"]),
                "error_rate_pct": _f(r["error_rate_pct"]),
            }
            for r in rows
        ]

    adoption, productivity, quality, teams = await asyncio.gather(
        _adoption_summary(),
        _productivity_summary(),
        _quality_summary(),
        _team_summary(),
    )
    return {
        "period_days": period_days,
        "adoption": adoption,
        "productivity_by_cohort": productivity,
        "quality_by_cohort": quality,
        "top_teams": teams,
    }


@router.get("/teams/{team_id}/score")
async def team_adoption_score(
    team_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Return a composite AI adoption health score (0–100) for a team."""
    team_size = (await session.execute(
        text("SELECT COUNT(*) FROM node_members WHERE node_id=CAST(:tid AS uuid)"),
        {"tid": team_id},
    )).scalar() or 0

    if team_size == 0:
        return {
            "score": 0,
            "grade": "N/A",
            "active_user_rate": 0,
            "model_diversity": 0,
            "weekly_sessions": 0,
            "trend": "flat",
        }

    # Active users this week, inferred from developer_activity_log via team membership
    try:
        active_users = (await session.execute(text("""
            SELECT COUNT(DISTINCT dal.developer_id)
            FROM developer_activity_log dal
            JOIN developers d ON d.id = dal.developer_id
            WHERE d.team_id = CAST(:tid AS uuid)
              AND dal.date >= CURRENT_DATE - INTERVAL '7 days'
        """), {"tid": team_id})).scalar() or 0
    except Exception:
        active_users = 0

    active_rate = min(1.0, active_users / max(1, team_size))

    # Score: 40% active_rate + 30% model diversity (default 0.5) + 30% trend (default 0.5)
    score = int((active_rate * 0.4 + 0.5 * 0.3 + 0.5 * 0.3) * 100)
    grade = "A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "D"

    return {
        "score": score,
        "grade": grade,
        "active_user_rate": round(active_rate, 2),
        "model_diversity": 0.5,
        "weekly_sessions": int(active_users),
        "trend": "flat",
    }


@router.get("/insights")
async def genai_insights(
    period_days: int = Query(default=30, ge=7, le=365),
    session: AsyncSession = Depends(get_session),
):
    metrics = await _gather_metrics(session, period_days)
    metrics_json = json.dumps(metrics, indent=2)

    prompt = (
        f"Analyse the following GenAI adoption metrics for the last {period_days} days "
        f"and return your structured JSON analysis:\n\n{metrics_json}"
    )

    url = f"{settings.litellm_url}/v1/chat/completions"
    payload = {
        "model": "claude-sonnet-4-6",
        "messages": [
            {"role": "system", "content": _INSIGHTS_SYSTEM},
            {"role": "user",   "content": prompt},
        ],
        "max_tokens": 800,
        "temperature": 0.2,
    }

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
            )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        # Strip markdown fences if present
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        insights = json.loads(content)
    except Exception as exc:
        log.warning("AI insights generation failed: %s", exc)
        insights = {
            "summary": "AI analysis unavailable — metrics are shown below.",
            "highlights": [],
            "recommendations": [],
            "risks": [],
        }

    return {"period_days": period_days, "metrics": metrics, "insights": insights}
