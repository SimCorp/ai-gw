from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session

router = APIRouter(prefix="/requests", tags=["requests"])

_SUMMARY_QUERY = text("""
    SELECT
        COUNT(*) AS request_count,
        ROUND((AVG(CASE WHEN cache_hit THEN 1.0 ELSE 0.0 END) * 100)::numeric, 1) AS cache_hit_pct,
        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY latency_ms) AS p50_ms,
        PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY latency_ms) AS p99_ms,
        SUM(tokens_input + tokens_output) AS total_tokens
    FROM cost_records
    WHERE created_at >= NOW() - INTERVAL '10 minutes'
""")


@router.get("")
async def list_requests(
    team_id: str | None = Query(default=None),
    model: str | None = Query(default=None),
    cache_hit: bool | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    session: AsyncSession = Depends(get_session),
):
    conditions = ["1=1"]
    params: dict = {"limit": limit}

    if team_id is not None:
        conditions.append("cr.team_id = CAST(:team_id AS uuid)")
        params["team_id"] = team_id
    if model is not None:
        conditions.append("cr.model = :model")
        params["model"] = model
    if cache_hit is not None:
        conditions.append("cr.cache_hit = :cache_hit")
        params["cache_hit"] = cache_hit

    where = " AND ".join(conditions)
    sql = text(f"""
        SELECT
            cr.id,
            cr.created_at,
            t.name AS team_name,
            ak.name AS key_name,
            cr.model,
            cr.tokens_input,
            cr.tokens_output,
            cr.cost_usd,
            cr.cache_hit,
            cr.latency_ms
        FROM cost_records cr
        JOIN teams t ON t.id = cr.team_id
        LEFT JOIN api_keys ak ON ak.id = cr.api_key_id
        WHERE {where}
        ORDER BY cr.created_at DESC
        LIMIT :limit
    """)
    rows = (await session.execute(sql, params)).mappings().all()
    return [dict(r) for r in rows]


@router.get("/summary")
async def requests_summary(session: AsyncSession = Depends(get_session)):
    row = (await session.execute(_SUMMARY_QUERY)).mappings().first()
    return dict(row) if row else {}
