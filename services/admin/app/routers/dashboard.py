from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session

router = APIRouter(tags=["dashboard"])

_STATS_QUERY = text("""
    SELECT
        t.name AS team_name,
        COUNT(cr.id) AS request_count,
        SUM(cr.tokens_input + cr.tokens_output) AS total_tokens,
        ROUND(SUM(cr.cost_usd)::numeric, 4) AS total_cost_usd,
        ROUND((AVG(CASE WHEN cr.cache_hit THEN 1.0 ELSE 0.0 END) * 100)::numeric, 1) AS cache_hit_pct
    FROM organization_nodes t
    LEFT JOIN cost_records cr ON cr.node_id = t.id
    WHERE t.type = 'team'
    GROUP BY t.id, t.name
    ORDER BY total_tokens DESC NULLS LAST
""")


@router.get("/dashboard/stats")
async def dashboard_stats(session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(_STATS_QUERY)).mappings().all()
    return [dict(r) for r in rows]
