from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin_role, require_superadmin_role
from app.db import get_session

router = APIRouter(prefix="/developers", tags=["developers"])

Period = Literal["7d", "30d", "90d", "mtd", "all"]


def _since_sql(period: Period, alias: str = "cr") -> str:
    col = f"{alias}.created_at" if alias else "created_at"
    if period == "7d":
        return f"AND {col} >= NOW() - INTERVAL '7 days'"
    elif period == "30d":
        return f"AND {col} >= NOW() - INTERVAL '30 days'"
    elif period == "90d":
        return f"AND {col} >= NOW() - INTERVAL '90 days'"
    elif period == "mtd":
        return f"AND {col} >= date_trunc('month', NOW())"
    return ""


@router.get("")
async def list_developers(
    session: AsyncSession = Depends(get_session),
    _auth: dict = Depends(require_admin_role),
):
    rows = (
        (
            await session.execute(
                text("""
        SELECT d.id, d.email, d.display_name, d.status, d.created_at,
               d.team_id, t.name AS team_name
        FROM developers d
        LEFT JOIN organization_nodes t ON t.id = d.team_id
        ORDER BY d.created_at DESC
    """)
            )
        )
        .mappings()
        .all()
    )
    return [
        {
            "id": str(r["id"]),
            "email": r["email"],
            "display_name": r["display_name"],
            "status": r["status"],
            "team_id": str(r["team_id"]) if r["team_id"] else None,
            "team_name": r["team_name"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]


@router.get("/{developer_id}")
async def get_developer(
    developer_id: UUID,
    session: AsyncSession = Depends(get_session),
    _auth: dict = Depends(require_admin_role),
):
    row = (
        (
            await session.execute(
                text("""
            SELECT d.id, d.email, d.display_name, d.status, d.created_at,
                   d.team_id, t.name AS team_name, a.name AS area_name, a.color AS area_color
            FROM developers d
            LEFT JOIN organization_nodes t ON t.id = d.team_id
            LEFT JOIN organization_nodes a
                   ON a.type = 'area' AND t.path LIKE a.path || '/%'
            WHERE d.id = :id
        """),
                {"id": developer_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Developer not found")
    return {
        "id": str(row["id"]),
        "email": row["email"],
        "display_name": row["display_name"],
        "status": row["status"],
        "team_id": str(row["team_id"]) if row["team_id"] else None,
        "team_name": row["team_name"],
        "area_name": row["area_name"],
        "area_color": row["area_color"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


@router.get("/{developer_id}/stats")
async def get_developer_stats(
    developer_id: UUID,
    period: Period = "7d",
    session: AsyncSession = Depends(get_session),
    _auth: dict = Depends(require_admin_role),
):
    dev_row = (
        (
            await session.execute(
                text("SELECT id, email, display_name FROM developers WHERE id = :id"),
                {"id": developer_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    if not dev_row:
        raise HTTPException(status_code=404, detail="Developer not found")

    since = _since_sql(period)

    cost_row = (
        (
            await session.execute(
                text(f"""
        SELECT
            COUNT(cr.id)                                                  AS request_count,
            COALESCE(SUM(cr.tokens_input), 0)                            AS tokens_input,
            COALESCE(SUM(cr.tokens_output), 0)                           AS tokens_output,
            COALESCE(SUM(cr.tokens_input + cr.tokens_output), 0)         AS total_tokens,
            COALESCE(ROUND(SUM(cr.cost_usd)::numeric, 6), 0)             AS cost_usd,
            COALESCE(SUM(cr.tool_invocation_count), 0)                   AS tool_invocations,
            COALESCE(SUM(cr.retry_count), 0)                             AS retry_count,
            ROUND((AVG(CASE WHEN cr.cache_hit THEN 1.0 ELSE 0.0 END)*100)::numeric, 1) AS cache_hit_pct,
            ROUND(AVG(cr.latency_ms)::numeric, 0)                                 AS avg_latency_ms,
            COUNT(CASE WHEN cr.request_error_type IS NOT NULL THEN 1 END) AS error_count
        FROM cost_records cr
        WHERE cr.developer_id = :dev_id {since}
    """),
                {"dev_id": developer_id},
            )
        )
        .mappings()
        .one()
    )

    model_rows = (
        (
            await session.execute(
                text(f"""
        SELECT cr.model,
               COUNT(cr.id)                                       AS request_count,
               COALESCE(SUM(cr.tokens_input + cr.tokens_output), 0) AS total_tokens,
               COALESCE(ROUND(SUM(cr.cost_usd)::numeric, 6), 0)   AS cost_usd
        FROM cost_records cr
        WHERE cr.developer_id = :dev_id {since}
        GROUP BY cr.model
        ORDER BY cost_usd DESC
        LIMIT 10
    """),
                {"dev_id": developer_id},
            )
        )
        .mappings()
        .all()
    )

    repo_rows = (
        (
            await session.execute(
                text(f"""
        SELECT cr.repo,
               COUNT(cr.id) AS request_count,
               COALESCE(ROUND(SUM(cr.cost_usd)::numeric, 6), 0) AS cost_usd
        FROM cost_records cr
        WHERE cr.developer_id = :dev_id AND cr.repo IS NOT NULL {since}
        GROUP BY cr.repo
        ORDER BY cost_usd DESC
        LIMIT 10
    """),
                {"dev_id": developer_id},
            )
        )
        .mappings()
        .all()
    )

    daily_rows = (
        (
            await session.execute(
                text("""
        SELECT date, request_count, tokens_input, tokens_output,
               cost_usd, cache_hits, tool_invocations, error_count
        FROM developer_activity_log
        WHERE developer_id = :dev_id
        ORDER BY date DESC
        LIMIT 30
    """),
                {"dev_id": developer_id},
            )
        )
        .mappings()
        .all()
    )

    return {
        "developer_id": str(developer_id),
        "email": dev_row["email"],
        "display_name": dev_row["display_name"],
        "period": period,
        "summary": {
            "request_count": cost_row["request_count"],
            "tokens_input": int(cost_row["tokens_input"]),
            "tokens_output": int(cost_row["tokens_output"]),
            "total_tokens": int(cost_row["total_tokens"]),
            "cost_usd": float(cost_row["cost_usd"]),
            "tool_invocations": int(cost_row["tool_invocations"]),
            "retry_count": int(cost_row["retry_count"]),
            "cache_hit_pct": float(cost_row["cache_hit_pct"])
            if cost_row["cache_hit_pct"] is not None
            else None,
            "avg_latency_ms": int(cost_row["avg_latency_ms"])
            if cost_row["avg_latency_ms"] is not None
            else None,
            "error_count": int(cost_row["error_count"]),
        },
        "by_model": [
            {
                "model": r["model"],
                "request_count": r["request_count"],
                "total_tokens": int(r["total_tokens"]),
                "cost_usd": float(r["cost_usd"]),
            }
            for r in model_rows
        ],
        "by_repo": [
            {
                "repo": r["repo"],
                "request_count": r["request_count"],
                "cost_usd": float(r["cost_usd"]),
            }
            for r in repo_rows
        ],
        "daily": [
            {
                "date": str(r["date"]),
                "request_count": r["request_count"],
                "tokens_input": int(r["tokens_input"]),
                "tokens_output": int(r["tokens_output"]),
                "cost_usd": float(r["cost_usd"]),
                "cache_hits": r["cache_hits"],
                "tool_invocations": r["tool_invocations"],
                "error_count": r["error_count"],
            }
            for r in daily_rows
        ],
    }


@router.get("/{developer_id}/teams")
async def get_developer_teams(developer_id: UUID, session: AsyncSession = Depends(get_session)):
    dev_id_str = str(developer_id)
    # Accept both legacy developers table (pre-0010) and unified users table (post-0010)
    dev_exists = (
        await session.execute(
            text("SELECT id FROM developers WHERE id = :id"), {"id": developer_id}
        )
    ).one_or_none()
    if not dev_exists:
        dev_exists = (
            await session.execute(
                text("SELECT id FROM users WHERE id = CAST(:id AS uuid)"), {"id": dev_id_str}
            )
        ).one_or_none()
    if not dev_exists:
        raise HTTPException(status_code=404, detail="Developer not found")

    rows = (
        (
            await session.execute(
                text("""
            SELECT tm.id AS membership_id, tm.role, tm.created_at AS joined_at,
                   t.id AS team_id, t.name AS team_name, t.slug AS team_slug,
                   a.name AS area_name, a.color AS area_color
            FROM node_members tm
            JOIN organization_nodes t ON t.id = tm.node_id
            LEFT JOIN organization_nodes a
                   ON a.type = 'area' AND t.path LIKE a.path || '/%'
            WHERE tm.developer_id = :developer_id
               OR tm.user_id = :dev_id_str
            ORDER BY t.name
        """),
                {"developer_id": developer_id, "dev_id_str": dev_id_str},
            )
        )
        .mappings()
        .all()
    )

    return [
        {
            "membership_id": str(r["membership_id"]),
            "role": r["role"],
            "joined_at": r["joined_at"].isoformat() if r["joined_at"] else None,
            "team_id": str(r["team_id"]),
            "team_name": r["team_name"],
            "team_slug": r["team_slug"],
            "area_name": r["area_name"],
            "area_color": r["area_color"],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# E. At-risk developer detection (struggle signals)
# ---------------------------------------------------------------------------


@router.get("/at-risk")
async def at_risk_developers(
    period: Period = "7d",
    session: AsyncSession = Depends(get_session),
    _auth: dict = Depends(require_superadmin_role),
):
    """
    Developers showing struggle signals based on DX/GitHub research:
    - High retry rate (>30%)
    - High error rate (>30%)
    - High spend with zero git output
    - Session quality score ≤2 (if session tracking is active)
    """
    since = _since_sql(period)
    since_doe = since.replace("AND cr.created_at", "AND doe.occurred_at")
    since_s = since.replace("AND cr.created_at", "AND s.first_request_at")

    sql = text(f"""
        WITH dev_stats AS (
            SELECT cr.developer_id,
                   COUNT(cr.id)                                             AS request_count,
                   COALESCE(ROUND(SUM(cr.cost_usd)::numeric, 6), 0)        AS cost_usd,
                   COALESCE(SUM(cr.retry_count), 0)                        AS total_retries,
                   COUNT(CASE WHEN cr.request_error_type IS NOT NULL THEN 1 END) AS error_count,
                   ROUND(SUM(cr.retry_count)::float / GREATEST(COUNT(cr.id), 1), 3) AS retry_rate,
                   ROUND(COUNT(CASE WHEN cr.request_error_type IS NOT NULL THEN 1 END)::float
                         / GREATEST(COUNT(cr.id), 1), 3) AS error_rate
            FROM cost_records cr
            WHERE cr.developer_id IS NOT NULL {since}
            GROUP BY cr.developer_id
            HAVING COUNT(cr.id) >= 5  -- ignore very low-volume devs
        ),
        dev_output AS (
            SELECT doe.developer_id,
                   COALESCE(SUM(doe.commit_count), 0) AS total_commits,
                   COUNT(CASE WHEN doe.event_type IN ('pr_opened', 'pr_merged') THEN 1 END) AS total_prs
            FROM developer_output_events doe
            WHERE doe.developer_id IS NOT NULL {since_doe}
            GROUP BY doe.developer_id
        ),
        session_quality AS (
            SELECT s.developer_id,
                   ROUND(AVG(s.quality_score)::numeric, 2) AS avg_quality,
                   COUNT(CASE WHEN s.produced_commit THEN 1 END) AS sessions_with_commit,
                   COUNT(s.session_trace_id) AS session_count
            FROM sessions s
            WHERE s.developer_id IS NOT NULL {since_s}
            GROUP BY s.developer_id
        )
        SELECT d.id AS developer_id, d.email, d.display_name,
               t.name AS team_name,
               ds.request_count, ds.cost_usd,
               ds.retry_rate, ds.error_rate,
               COALESCE(do2.total_commits, 0) AS total_commits,
               COALESCE(do2.total_prs, 0) AS total_prs,
               sq.avg_quality, sq.session_count,
               CASE WHEN sq.session_count > 0
                    THEN ROUND(sq.sessions_with_commit * 100.0 / sq.session_count, 1) END AS commit_conversion_pct,
               -- Struggle flags
               (ds.retry_rate > 0.3)::int +
               (ds.error_rate > 0.3)::int +
               (ds.cost_usd > 5 AND COALESCE(do2.total_commits, 0) = 0 AND COALESCE(do2.total_prs, 0) = 0)::int +
               (sq.avg_quality IS NOT NULL AND sq.avg_quality <= 2)::int AS struggle_flags
        FROM developers d
        JOIN dev_stats ds ON ds.developer_id = d.id
        LEFT JOIN dev_output do2 ON do2.developer_id = d.id
        LEFT JOIN session_quality sq ON sq.developer_id = d.id
        LEFT JOIN organization_nodes t ON t.id = d.team_id
        HAVING (
            ds.retry_rate > 0.3 OR
            ds.error_rate > 0.3 OR
            (ds.cost_usd > 5 AND COALESCE(do2.total_commits, 0) = 0 AND COALESCE(do2.total_prs, 0) = 0) OR
            (sq.avg_quality IS NOT NULL AND sq.avg_quality <= 2)
        )
        ORDER BY struggle_flags DESC, ds.cost_usd DESC
    """)
    rows = (await session.execute(sql)).mappings().all()
    return [
        {
            "developer_id": str(r["developer_id"]),
            "email": r["email"],
            "display_name": r["display_name"],
            "team_name": r["team_name"],
            "request_count": r["request_count"],
            "cost_usd": float(r["cost_usd"]),
            "retry_rate": float(r["retry_rate"]),
            "error_rate": float(r["error_rate"]),
            "total_commits": int(r["total_commits"]),
            "total_prs": int(r["total_prs"]),
            "avg_session_quality": float(r["avg_quality"])
            if r["avg_quality"] is not None
            else None,
            "commit_conversion_pct": float(r["commit_conversion_pct"])
            if r["commit_conversion_pct"] is not None
            else None,
            "struggle_flags": int(r["struggle_flags"]),
            "signals": {
                "high_retry_rate": float(r["retry_rate"]) > 0.3,
                "high_error_rate": float(r["error_rate"]) > 0.3,
                "high_spend_no_output": float(r["cost_usd"]) > 5
                and int(r["total_commits"]) == 0
                and int(r["total_prs"]) == 0,
                "low_session_quality": r["avg_quality"] is not None
                and float(r["avg_quality"]) <= 2,
            },
        }
        for r in rows
    ]
