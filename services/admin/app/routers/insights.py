"""AI insights API — exposes optimization findings to admin and developer portals."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin_auth
from app.db import get_session
from app.routers.dev_auth import _get_current_developer
from app.workers.optimization_worker import (
    _flush_insights,
    _run_optimization_agent,
)

router = APIRouter(prefix="/insights", tags=["insights"])


def _fmt_insight(r: dict) -> dict:
    return {
        "id": str(r["id"]),
        "generated_at": r["generated_at"].isoformat() if r["generated_at"] else None,
        "category": r["category"],
        "severity": r["severity"],
        "title": r["title"],
        "description": r["description"],
        "action": r["action"],
        "team_name": r["team_name"],
        "dismissed": r["dismissed"],
        "auto_applied": r["auto_applied"],
        "source": r["source"],
    }


# ---------------------------------------------------------------------------
# Admin endpoints (require admin session)
# ---------------------------------------------------------------------------


@router.get("")
async def list_insights(
    category: str | None = None,
    severity: str | None = None,
    include_dismissed: bool = False,
    session: AsyncSession = Depends(get_session),
    _auth: dict = Depends(require_admin_auth),
):
    """List all recent AI optimization insights (admin)."""
    filters = ["generated_at >= NOW() - INTERVAL '25 hours'"]
    params: dict = {}
    if not include_dismissed:
        filters.append("dismissed = FALSE")
    if category:
        filters.append("category = :category")
        params["category"] = category
    if severity:
        filters.append("severity = :severity")
        params["severity"] = severity

    where = " AND ".join(filters)
    rows = (
        (
            await session.execute(
                text(f"""
        SELECT id, generated_at, category, severity, title, description, action,
               team_name, dismissed, auto_applied, source
        FROM ai_insights
        WHERE {where}
        ORDER BY
            CASE severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,
            generated_at DESC
    """),
                params,
            )
        )
        .mappings()
        .all()
    )
    return [_fmt_insight(dict(r)) for r in rows]


@router.post("/{insight_id}/dismiss")
async def dismiss_insight(
    insight_id: str,
    session: AsyncSession = Depends(get_session),
    _auth: dict = Depends(require_admin_auth),
):
    """Dismiss an insight so it no longer appears in the default view."""
    result = await session.execute(
        text("UPDATE ai_insights SET dismissed = TRUE WHERE id = :id RETURNING id"),
        {"id": insight_id},
    )
    if not result.one_or_none():
        raise HTTPException(status_code=404, detail="Insight not found")
    await session.commit()
    return {"dismissed": True}


@router.post("/trigger")
async def trigger_optimization_run(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _auth: dict = Depends(require_admin_auth),
):
    """Manually trigger an optimization analysis run (runs synchronously, may take ~30s)."""
    import asyncpg

    from app.config import settings

    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
    try:
        insights = await _run_optimization_agent(pool)
        stored = await _flush_insights(pool, insights)
    finally:
        await pool.close()

    return {"insights_stored": stored, "insights": insights}


@router.get("/summary")
async def insights_summary(
    session: AsyncSession = Depends(get_session),
    _auth: dict = Depends(require_admin_auth),
):
    """Counts of current insights by severity for the dashboard badge."""
    row = (
        (
            await session.execute(
                text("""
        SELECT
            COUNT(*) FILTER (WHERE severity = 'critical' AND NOT dismissed) AS critical,
            COUNT(*) FILTER (WHERE severity = 'warning'  AND NOT dismissed) AS warning,
            COUNT(*) FILTER (WHERE severity = 'info'     AND NOT dismissed) AS info,
            MAX(generated_at) AS last_run
        FROM ai_insights
        WHERE generated_at >= NOW() - INTERVAL '25 hours'
    """)
            )
        )
        .mappings()
        .one()
    )
    return {
        "critical": int(row["critical"] or 0),
        "warning": int(row["warning"] or 0),
        "info": int(row["info"] or 0),
        "last_run": row["last_run"].isoformat() if row["last_run"] else None,
    }


# ---------------------------------------------------------------------------
# Developer portal endpoint (dev session auth, team-scoped)
# ---------------------------------------------------------------------------


@router.get("/developer/me")
async def developer_insights(
    session: AsyncSession = Depends(get_session),
    developer: dict = Depends(_get_current_developer),
):
    """AI recommendations for the current developer (their team + personal insights)."""
    developer_id = developer.get("developer_id")
    team_id = developer.get("team_id")

    conditions = ["generated_at >= NOW() - INTERVAL '25 hours'", "dismissed = FALSE"]
    scope = []
    if team_id:
        scope.append("team_id = :team_id")
    if developer_id:
        scope.append("developer_id = :developer_id")
    scope.append("(team_id IS NULL AND developer_id IS NULL)")  # org-wide insights

    conditions.append(f"({' OR '.join(scope)})")
    where = " AND ".join(conditions)

    rows = (
        (
            await session.execute(
                text(f"""
            SELECT id, generated_at, category, severity, title, description, action,
                   team_name, dismissed, auto_applied, source
            FROM ai_insights
            WHERE {where}
            ORDER BY
                CASE severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,
                generated_at DESC
            LIMIT 10
        """),
                {"team_id": team_id, "developer_id": developer_id},
            )
        )
        .mappings()
        .all()
    )

    return [_fmt_insight(dict(r)) for r in rows]
