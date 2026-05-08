from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session

router = APIRouter(prefix="/reports", tags=["reports"])

Period = Literal["7d", "30d", "90d", "mtd", "all"]
GroupBy = Literal["area", "team", "model"]


def _since_clause(period: Period) -> tuple[str, dict]:
    """Return (WHERE fragment, bind params) for the given period."""
    if period == "7d":
        return "AND cr.created_at >= NOW() - INTERVAL '7 days'", {}
    elif period == "30d":
        return "AND cr.created_at >= NOW() - INTERVAL '30 days'", {}
    elif period == "90d":
        return "AND cr.created_at >= NOW() - INTERVAL '90 days'", {}
    elif period == "mtd":
        return "AND cr.created_at >= date_trunc('month', NOW())", {}
    else:  # "all"
        return "", {}


def _since_clause_bare(period: Period) -> str:
    """Return WHERE fragment without table alias (for model group_by)."""
    if period == "7d":
        return "WHERE created_at >= NOW() - INTERVAL '7 days'"
    elif period == "30d":
        return "WHERE created_at >= NOW() - INTERVAL '30 days'"
    elif period == "90d":
        return "WHERE created_at >= NOW() - INTERVAL '90 days'"
    elif period == "mtd":
        return "WHERE created_at >= date_trunc('month', NOW())"
    else:
        return ""


@router.get("/cost")
async def cost_report(
    period: Period = "30d",
    group_by: GroupBy = "area",
    session: AsyncSession = Depends(get_session),
):
    if group_by == "area":
        return await _cost_by_area(period, session)
    elif group_by == "team":
        return await _cost_by_team(period, session)
    else:
        return await _cost_by_model(period, session)


async def _cost_by_area(period: Period, session: AsyncSession) -> list[dict]:
    since_fragment, _ = _since_clause(period)

    sql = text(f"""
        SELECT a.id AS area_id, a.name AS area_name, a.color AS area_color,
               COUNT(cr.id) AS request_count,
               COALESCE(SUM(cr.tokens_input + cr.tokens_output), 0) AS total_tokens,
               COALESCE(ROUND(SUM(cr.cost_usd)::numeric, 6), 0) AS total_cost_usd,
               ROUND(AVG(CASE WHEN cr.cache_hit THEN 1.0 ELSE 0.0 END) * 100, 1) AS cache_hit_pct
        FROM areas a
        LEFT JOIN teams t ON t.area_id = a.id
        LEFT JOIN cost_records cr ON cr.team_id = t.id {since_fragment}
        GROUP BY a.id, a.name, a.color
        ORDER BY total_cost_usd DESC NULLS LAST
    """)
    rows = (await session.execute(sql)).mappings().all()
    results = [
        {
            "area_id": str(r["area_id"]),
            "area_name": r["area_name"],
            "area_color": r["area_color"],
            "request_count": r["request_count"],
            "total_tokens": int(r["total_tokens"]),
            "total_cost_usd": float(r["total_cost_usd"]),
            "cache_hit_pct": float(r["cache_hit_pct"]) if r["cache_hit_pct"] is not None else None,
        }
        for r in rows
    ]

    # "No area" bucket — teams without area_id
    since_fragment_no_alias, _ = _since_clause(period)
    # Rewrite alias for this query (cr alias already in place)
    no_area_sql = text(f"""
        SELECT COUNT(cr.id) AS request_count,
               COALESCE(SUM(cr.tokens_input + cr.tokens_output), 0) AS total_tokens,
               COALESCE(ROUND(SUM(cr.cost_usd)::numeric, 6), 0) AS total_cost_usd,
               ROUND(AVG(CASE WHEN cr.cache_hit THEN 1.0 ELSE 0.0 END) * 100, 1) AS cache_hit_pct
        FROM teams t
        LEFT JOIN cost_records cr ON cr.team_id = t.id {since_fragment}
        WHERE t.area_id IS NULL
    """)
    no_area_row = (await session.execute(no_area_sql)).mappings().one()
    results.append({
        "area_id": None,
        "area_name": "No area",
        "area_color": None,
        "request_count": no_area_row["request_count"],
        "total_tokens": int(no_area_row["total_tokens"]),
        "total_cost_usd": float(no_area_row["total_cost_usd"]),
        "cache_hit_pct": float(no_area_row["cache_hit_pct"]) if no_area_row["cache_hit_pct"] is not None else None,
    })

    return results


async def _cost_by_team(period: Period, session: AsyncSession) -> list[dict]:
    since_fragment, _ = _since_clause(period)

    sql = text(f"""
        SELECT t.id AS team_id, t.name AS team_name, t.slug AS team_slug,
               a.id AS area_id, a.name AS area_name, a.color AS area_color,
               COUNT(cr.id) AS request_count,
               COALESCE(SUM(cr.tokens_input + cr.tokens_output), 0) AS total_tokens,
               COALESCE(ROUND(SUM(cr.cost_usd)::numeric, 6), 0) AS total_cost_usd,
               ROUND(AVG(CASE WHEN cr.cache_hit THEN 1.0 ELSE 0.0 END) * 100, 1) AS cache_hit_pct
        FROM teams t
        LEFT JOIN areas a ON a.id = t.area_id
        LEFT JOIN cost_records cr ON cr.team_id = t.id {since_fragment}
        GROUP BY t.id, t.name, t.slug, a.id, a.name, a.color
        ORDER BY a.name NULLS LAST, total_cost_usd DESC NULLS LAST
    """)
    rows = (await session.execute(sql)).mappings().all()
    return [
        {
            "team_id": str(r["team_id"]),
            "team_name": r["team_name"],
            "team_slug": r["team_slug"],
            "area_id": str(r["area_id"]) if r["area_id"] else None,
            "area_name": r["area_name"],
            "area_color": r["area_color"],
            "request_count": r["request_count"],
            "total_tokens": int(r["total_tokens"]),
            "total_cost_usd": float(r["total_cost_usd"]),
            "cache_hit_pct": float(r["cache_hit_pct"]) if r["cache_hit_pct"] is not None else None,
        }
        for r in rows
    ]


async def _cost_by_model(period: Period, session: AsyncSession) -> list[dict]:
    where_clause = _since_clause_bare(period)

    sql = text(f"""
        SELECT model,
               COUNT(id) AS request_count,
               COALESCE(SUM(tokens_input + tokens_output), 0) AS total_tokens,
               COALESCE(ROUND(SUM(cost_usd)::numeric, 6), 0) AS total_cost_usd
        FROM cost_records
        {where_clause}
        GROUP BY model
        ORDER BY total_cost_usd DESC
    """)
    rows = (await session.execute(sql)).mappings().all()
    return [
        {
            "model": r["model"],
            "request_count": r["request_count"],
            "total_tokens": int(r["total_tokens"]),
            "total_cost_usd": float(r["total_cost_usd"]),
        }
        for r in rows
    ]
