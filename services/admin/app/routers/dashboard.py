from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session

router = APIRouter(tags=["dashboard"])

_RANGE_INTERVALS = {
    "1h": "1 hour",
    "24h": "24 hours",
    "7d": "7 days",
    "30d": "30 days",
    "90d": "90 days",
}


@router.get("/dashboard/stats")
async def dashboard_stats(
    range: str = Query("30d", pattern=r"^(1h|24h|7d|30d|90d)$"),
    session: AsyncSession = Depends(get_session),
):
    interval = _RANGE_INTERVALS.get(range, "30 days")
    rows = (
        (
            await session.execute(
                text("""
        SELECT
            t.name AS team_name,
            COUNT(cr.id) AS request_count,
            SUM(cr.tokens_input + cr.tokens_output) AS total_tokens,
            ROUND(SUM(cr.cost_usd)::numeric, 4) AS total_cost_usd,
            ROUND((AVG(CASE WHEN cr.cache_hit THEN 1.0 ELSE 0.0 END) * 100)::numeric, 1) AS cache_hit_pct
        FROM organization_nodes t
        LEFT JOIN cost_records cr ON cr.node_id = t.id
            AND cr.created_at >= NOW() - (:interval)::INTERVAL
        WHERE t.type = 'team'
        GROUP BY t.id, t.name
        ORDER BY total_tokens DESC NULLS LAST
    """),
                {"interval": interval},
            )
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]
