from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin_role, require_superadmin_role
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
               ROUND((AVG(CASE WHEN cr.cache_hit THEN 1.0 ELSE 0.0 END) * 100)::numeric, 1) AS cache_hit_pct
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
               ROUND((AVG(CASE WHEN cr.cache_hit THEN 1.0 ELSE 0.0 END) * 100)::numeric, 1) AS cache_hit_pct
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
               ROUND((AVG(CASE WHEN cr.cache_hit THEN 1.0 ELSE 0.0 END) * 100)::numeric, 1) AS cache_hit_pct
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


@router.get("/developers")
async def developer_productivity_report(
    period: Period = "30d",
    session: AsyncSession = Depends(get_session),
    _auth: dict = Depends(require_admin_role),
):
    """Aggregate productivity metrics per developer, ranked by cost."""
    since_fragment, _ = _since_clause(period)

    sql = text(f"""
        SELECT d.id AS developer_id, d.email, d.display_name,
               t.name AS team_name,
               COUNT(cr.id)                                                  AS request_count,
               COALESCE(SUM(cr.tokens_input + cr.tokens_output), 0)         AS total_tokens,
               COALESCE(ROUND(SUM(cr.cost_usd)::numeric, 6), 0)             AS cost_usd,
               COALESCE(SUM(cr.tool_invocation_count), 0)                   AS tool_invocations,
               ROUND((AVG(CASE WHEN cr.cache_hit THEN 1.0 ELSE 0.0 END)*100)::numeric, 1) AS cache_hit_pct,
               COUNT(CASE WHEN cr.request_error_type IS NOT NULL THEN 1 END) AS error_count,
               COUNT(DISTINCT cr.repo)                                       AS repo_count
        FROM developers d
        LEFT JOIN teams t ON t.id = d.team_id
        LEFT JOIN cost_records cr ON cr.developer_id = d.id {since_fragment}
        GROUP BY d.id, d.email, d.display_name, t.name
        ORDER BY cost_usd DESC NULLS LAST
    """)
    rows = (await session.execute(sql)).mappings().all()
    return [
        {
            "developer_id": str(r["developer_id"]),
            "email": r["email"],
            "display_name": r["display_name"],
            "team_name": r["team_name"],
            "request_count": r["request_count"],
            "total_tokens": int(r["total_tokens"]),
            "cost_usd": float(r["cost_usd"]),
            "tool_invocations": int(r["tool_invocations"]),
            "cache_hit_pct": float(r["cache_hit_pct"]) if r["cache_hit_pct"] is not None else None,
            "error_count": int(r["error_count"]),
            "repo_count": int(r["repo_count"]),
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


# ---------------------------------------------------------------------------
# B. Cost-per-outcome (cost per PR / cost per commit)
# ---------------------------------------------------------------------------

@router.get("/outcomes")
async def outcome_efficiency_report(
    period: Period = "30d",
    session: AsyncSession = Depends(get_session),
    _auth: dict = Depends(require_admin_role),
):
    """Cost-per-PR and cost-per-commit by developer, ranked by efficiency."""
    since_cr = _since_clause(period)[0]
    since_doe = since_cr.replace("AND cr.created_at", "AND doe.occurred_at") if since_cr else ""

    sql = text(f"""
        WITH dev_cost AS (
            SELECT cr.developer_id,
                   COALESCE(ROUND(SUM(cr.cost_usd)::numeric, 6), 0) AS cost_usd,
                   COUNT(cr.id) AS request_count,
                   COALESCE(SUM(cr.tokens_input + cr.tokens_output), 0) AS total_tokens
            FROM cost_records cr
            WHERE cr.developer_id IS NOT NULL {since_cr}
            GROUP BY cr.developer_id
        ),
        dev_output AS (
            SELECT doe.developer_id,
                   SUM(doe.commit_count) AS total_commits,
                   COUNT(CASE WHEN doe.event_type IN ('pr_opened', 'pr_merged') THEN 1 END) AS total_prs,
                   COUNT(CASE WHEN doe.event_type = 'pr_merged' THEN 1 END) AS merged_prs
            FROM developer_output_events doe
            WHERE doe.developer_id IS NOT NULL {since_doe}
            GROUP BY doe.developer_id
        )
        SELECT d.id AS developer_id, d.email, d.display_name, t.name AS team_name,
               dc.cost_usd, dc.request_count, dc.total_tokens,
               COALESCE(do2.total_commits, 0) AS total_commits,
               COALESCE(do2.total_prs, 0) AS total_prs,
               COALESCE(do2.merged_prs, 0) AS merged_prs,
               CASE WHEN COALESCE(do2.total_prs, 0) > 0
                    THEN ROUND((dc.cost_usd / do2.total_prs)::numeric, 4) END AS cost_per_pr,
               CASE WHEN COALESCE(do2.total_commits, 0) > 0
                    THEN ROUND((dc.cost_usd / do2.total_commits)::numeric, 4) END AS cost_per_commit,
               CASE WHEN COALESCE(do2.total_prs, 0) > 0
                    THEN ROUND((do2.merged_prs * 100.0 / do2.total_prs)::numeric, 1) END AS pr_merge_rate_pct
        FROM developers d
        JOIN dev_cost dc ON dc.developer_id = d.id
        LEFT JOIN dev_output do2 ON do2.developer_id = d.id
        LEFT JOIN teams t ON t.id = d.team_id
        ORDER BY cost_per_pr ASC NULLS LAST, dc.cost_usd DESC
    """)
    rows = (await session.execute(sql)).mappings().all()
    return [
        {
            "developer_id": str(r["developer_id"]),
            "email": r["email"],
            "display_name": r["display_name"],
            "team_name": r["team_name"],
            "cost_usd": float(r["cost_usd"]),
            "request_count": r["request_count"],
            "total_tokens": int(r["total_tokens"]),
            "total_commits": int(r["total_commits"]),
            "total_prs": int(r["total_prs"]),
            "merged_prs": int(r["merged_prs"]),
            "cost_per_pr": float(r["cost_per_pr"]) if r["cost_per_pr"] is not None else None,
            "cost_per_commit": float(r["cost_per_commit"]) if r["cost_per_commit"] is not None else None,
            "pr_merge_rate_pct": float(r["pr_merge_rate_pct"]) if r["pr_merge_rate_pct"] is not None else None,
        }
        for r in rows
    ]


@router.get("/team-efficiency")
async def team_efficiency_report(
    period: Period = "30d",
    session: AsyncSession = Depends(get_session),
):
    """Cost-per-PR by team with DORA-inspired signals (amplifier vs detractor)."""
    since_cr = _since_clause(period)[0]
    since_doe = since_cr.replace("AND cr.created_at", "AND doe.occurred_at") if since_cr else ""

    sql = text(f"""
        WITH team_cost AS (
            SELECT cr.team_id,
                   COALESCE(ROUND(SUM(cr.cost_usd)::numeric, 6), 0) AS cost_usd,
                   COUNT(cr.id) AS request_count,
                   COUNT(DISTINCT cr.developer_id) AS active_developers,
                   ROUND((AVG(CASE WHEN cr.cache_hit THEN 1.0 ELSE 0.0 END)*100)::numeric, 1) AS cache_hit_pct
            FROM cost_records cr
            WHERE cr.developer_id IS NOT NULL {since_cr}
            GROUP BY cr.team_id
        ),
        team_output AS (
            SELECT t2.team_id,
                   SUM(doe.commit_count) AS total_commits,
                   COUNT(CASE WHEN doe.event_type IN ('pr_opened', 'pr_merged') THEN 1 END) AS total_prs,
                   COUNT(CASE WHEN doe.event_type = 'pr_merged' THEN 1 END) AS merged_prs
            FROM developer_output_events doe
            JOIN developers d2 ON d2.id = doe.developer_id
            JOIN team_members t2 ON t2.developer_id = d2.id
            WHERE doe.developer_id IS NOT NULL {since_doe}
            GROUP BY t2.team_id
        )
        SELECT t.id AS team_id, t.name AS team_name, a.name AS area_name, a.color AS area_color,
               tc.cost_usd, tc.request_count, tc.active_developers, tc.cache_hit_pct,
               COALESCE(to2.total_commits, 0) AS total_commits,
               COALESCE(to2.total_prs, 0) AS total_prs,
               COALESCE(to2.merged_prs, 0) AS merged_prs,
               CASE WHEN COALESCE(to2.total_prs, 0) > 0
                    THEN ROUND((tc.cost_usd / to2.total_prs)::numeric, 4) END AS cost_per_pr,
               CASE WHEN COALESCE(to2.merged_prs, 0) > 0
                    THEN ROUND((tc.cost_usd / to2.merged_prs)::numeric, 4) END AS cost_per_merged_pr
        FROM teams t
        JOIN team_cost tc ON tc.team_id = t.id
        LEFT JOIN team_output to2 ON to2.team_id = t.id
        LEFT JOIN areas a ON a.id = t.area_id
        ORDER BY cost_per_pr ASC NULLS LAST
    """)
    rows = (await session.execute(sql)).mappings().all()
    return [
        {
            "team_id": str(r["team_id"]),
            "team_name": r["team_name"],
            "area_name": r["area_name"],
            "area_color": r["area_color"],
            "cost_usd": float(r["cost_usd"]),
            "request_count": r["request_count"],
            "active_developers": r["active_developers"],
            "cache_hit_pct": float(r["cache_hit_pct"]) if r["cache_hit_pct"] is not None else None,
            "total_commits": int(r["total_commits"]),
            "total_prs": int(r["total_prs"]),
            "merged_prs": int(r["merged_prs"]),
            "cost_per_pr": float(r["cost_per_pr"]) if r["cost_per_pr"] is not None else None,
            "cost_per_merged_pr": float(r["cost_per_merged_pr"]) if r["cost_per_merged_pr"] is not None else None,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# D. Model calibration report
# ---------------------------------------------------------------------------

@router.get("/model-calibration")
async def model_calibration_report(
    period: Period = "30d",
    session: AsyncSession = Depends(get_session),
    _auth: dict = Depends(require_admin_role),
):
    """Per-developer model tier distribution — detects calibration inefficiencies."""
    since_cr = _since_clause(period)[0]

    sql = text(f"""
        SELECT d.id AS developer_id, d.email, d.display_name, t.name AS team_name,
               cr.model,
               COUNT(cr.id) AS request_count,
               COALESCE(ROUND(SUM(cr.cost_usd)::numeric, 6), 0) AS cost_usd,
               COALESCE(SUM(cr.tokens_input + cr.tokens_output), 0) AS total_tokens
        FROM cost_records cr
        JOIN developers d ON d.id = cr.developer_id
        LEFT JOIN teams t ON t.id = d.team_id
        WHERE cr.developer_id IS NOT NULL {since_cr}
        GROUP BY d.id, d.email, d.display_name, t.name, cr.model
        ORDER BY d.email, cost_usd DESC
    """)
    rows = (await session.execute(sql)).mappings().all()

    # Group by developer
    devs: dict = {}
    for r in rows:
        dev_id = str(r["developer_id"])
        if dev_id not in devs:
            devs[dev_id] = {
                "developer_id": dev_id,
                "email": r["email"],
                "display_name": r["display_name"],
                "team_name": r["team_name"],
                "total_cost_usd": 0.0,
                "total_requests": 0,
                "models": [],
            }
        cost = float(r["cost_usd"])
        devs[dev_id]["total_cost_usd"] += cost
        devs[dev_id]["total_requests"] += r["request_count"]
        devs[dev_id]["models"].append({
            "model": r["model"],
            "request_count": r["request_count"],
            "cost_usd": cost,
            "total_tokens": int(r["total_tokens"]),
        })

    # Compute calibration signals
    EXPENSIVE_PREFIXES = ("claude-opus", "gpt-4o ", "gpt-4")
    result = []
    for dev in devs.values():
        expensive_reqs = sum(
            m["request_count"] for m in dev["models"]
            if any(m["model"].startswith(p) for p in EXPENSIVE_PREFIXES)
        )
        expensive_pct = round(expensive_reqs * 100 / max(1, dev["total_requests"]), 1)
        dev["expensive_model_pct"] = expensive_pct
        dev["calibration_flag"] = expensive_pct > 80  # >80% expensive = potentially uncalibrated
        result.append(dev)

    result.sort(key=lambda x: x["total_cost_usd"], reverse=True)
    return result


# ---------------------------------------------------------------------------
# Session quality reports
# ---------------------------------------------------------------------------

@router.get("/sessions")
async def session_quality_report(
    period: Period = "30d",
    min_quality: int = Query(default=1, ge=1, le=5),
    max_quality: int = Query(default=5, ge=1, le=5),
    session: AsyncSession = Depends(get_session),
    _auth: dict = Depends(require_admin_role),
):
    """Aggregate session quality stats by developer."""
    since = _since_clause(period)[0].replace("AND cr.created_at", "AND s.first_request_at") if _since_clause(period)[0] else ""

    sql = text(f"""
        SELECT d.id AS developer_id, d.email, d.display_name, t.name AS team_name,
               COUNT(s.session_trace_id)                              AS session_count,
               ROUND(AVG(s.quality_score)::numeric, 2)                        AS avg_quality_score,
               ROUND(AVG(s.turn_count)::numeric, 1)                           AS avg_turns,
               ROUND(AVG(s.avg_inter_request_s)::numeric, 1)                  AS avg_inter_request_s,
               ROUND(AVG(s.retry_count::float / GREATEST(s.turn_count, 1))::numeric, 3) AS avg_retry_rate,
               COUNT(CASE WHEN s.produced_commit THEN 1 END)         AS sessions_with_commit,
               ROUND(COUNT(CASE WHEN s.produced_commit THEN 1 END) * 100.0
                     / GREATEST(COUNT(s.session_trace_id), 1), 1)    AS commit_conversion_pct,
               COALESCE(ROUND(SUM(s.total_cost)::numeric, 6), 0)     AS total_cost_usd
        FROM sessions s
        JOIN developers d ON d.id = s.developer_id
        LEFT JOIN teams t ON t.id = d.team_id
        WHERE s.developer_id IS NOT NULL
          AND s.quality_score BETWEEN :min_q AND :max_q
          {since}
        GROUP BY d.id, d.email, d.display_name, t.name
        ORDER BY avg_quality_score ASC
    """)
    rows = (await session.execute(sql, {"min_q": min_quality, "max_q": max_quality})).mappings().all()
    return [
        {
            "developer_id": str(r["developer_id"]),
            "email": r["email"],
            "display_name": r["display_name"],
            "team_name": r["team_name"],
            "session_count": r["session_count"],
            "avg_quality_score": float(r["avg_quality_score"]) if r["avg_quality_score"] is not None else None,
            "avg_turns": float(r["avg_turns"]) if r["avg_turns"] is not None else None,
            "avg_inter_request_s": float(r["avg_inter_request_s"]) if r["avg_inter_request_s"] is not None else None,
            "avg_retry_rate": float(r["avg_retry_rate"]) if r["avg_retry_rate"] is not None else None,
            "sessions_with_commit": r["sessions_with_commit"],
            "commit_conversion_pct": float(r["commit_conversion_pct"]) if r["commit_conversion_pct"] is not None else None,
            "total_cost_usd": float(r["total_cost_usd"]),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Guardrail analytics
# ---------------------------------------------------------------------------

@router.get("/guardrails")
async def guardrail_analytics(
    period: Period = "30d",
    session: AsyncSession = Depends(get_session),
    _auth: dict = Depends(require_superadmin_role),
):
    """Aggregate guardrail hit stats: which rules fire most, top triggering developers.
    Restricted to superadmin — response includes individually-identified behavioral data."""
    since = _since_clause(period)[0].replace("AND cr.created_at", "AND h.created_at")

    # Per-guardrail aggregates
    guard_sql = text(f"""
        SELECT g.id AS guardrail_id, g.name, g.type, g.applies_to, g.action, g.severity,
               g.enabled,
               COUNT(h.id)                                                AS hit_count,
               COUNT(DISTINCT h.team_id)                                  AS teams_affected,
               COUNT(DISTINCT h.api_key_id)                               AS keys_affected,
               COUNT(CASE WHEN h.false_positive = TRUE THEN 1 END)        AS false_positives,
               ROUND(
                   COUNT(CASE WHEN h.false_positive = TRUE THEN 1 END) * 100.0
                   / GREATEST(COUNT(h.id), 1), 1
               )                                                          AS false_positive_pct,
               MAX(h.created_at)                                          AS last_fired_at
        FROM guardrails g
        LEFT JOIN guardrail_hits h ON h.guardrail_id = g.id {since}
        GROUP BY g.id, g.name, g.type, g.applies_to, g.action, g.severity, g.enabled
        ORDER BY hit_count DESC
    """)
    guard_rows = (await session.execute(guard_sql)).mappings().all()

    # Top developers triggering guardrails (via api_key → developer join)
    dev_sql = text(f"""
        SELECT d.id AS developer_id, d.email, d.display_name, t.name AS team_name,
               COUNT(h.id) AS hit_count,
               COUNT(DISTINCT h.guardrail_id) AS distinct_guardrails,
               MODE() WITHIN GROUP (ORDER BY g.type) AS most_common_type
        FROM guardrail_hits h
        JOIN api_keys ak ON ak.id = h.api_key_id
        JOIN developers d ON d.id = ak.developer_id
        LEFT JOIN teams t ON t.id = d.team_id
        JOIN guardrails g ON g.id = h.guardrail_id
        WHERE h.api_key_id IS NOT NULL AND ak.developer_id IS NOT NULL
          {since.replace("AND h.created_at", "AND h.created_at")}
        GROUP BY d.id, d.email, d.display_name, t.name
        ORDER BY hit_count DESC
        LIMIT 20
    """)
    dev_rows = (await session.execute(dev_sql)).mappings().all()

    return {
        "period": period,
        "by_guardrail": [
            {
                "guardrail_id": str(r["guardrail_id"]),
                "name": r["name"],
                "type": r["type"],
                "applies_to": r["applies_to"],
                "action": r["action"],
                "severity": r["severity"],
                "enabled": r["enabled"],
                "hit_count": r["hit_count"],
                "teams_affected": r["teams_affected"],
                "keys_affected": r["keys_affected"],
                "false_positives": r["false_positives"],
                "false_positive_pct": float(r["false_positive_pct"]) if r["false_positive_pct"] is not None else None,
                "last_fired_at": r["last_fired_at"].isoformat() if r["last_fired_at"] else None,
            }
            for r in guard_rows
        ],
        "top_triggering_developers": [
            {
                "developer_id": str(r["developer_id"]),
                "email": r["email"],
                "display_name": r["display_name"],
                "team_name": r["team_name"],
                "hit_count": r["hit_count"],
                "distinct_guardrails": r["distinct_guardrails"],
                "most_common_type": r["most_common_type"],
            }
            for r in dev_rows
        ],
    }


# ---------------------------------------------------------------------------
# Intent distribution
# ---------------------------------------------------------------------------

@router.get("/intents")
async def intent_distribution(
    period: Period = "30d",
    session: AsyncSession = Depends(get_session),
):
    """Distribution of classified request intents across the org."""
    since = _since_clause(period)[0].replace("AND cr.created_at", "AND s.first_request_at")

    sql = text(f"""
        SELECT COALESCE(s.dominant_intent, 'general') AS intent,
               COUNT(s.session_trace_id)               AS session_count,
               COALESCE(ROUND(SUM(s.total_cost)::numeric, 4), 0) AS cost_usd,
               ROUND(AVG(s.quality_score)::numeric, 2)          AS avg_quality,
               ROUND(AVG(s.turn_count)::numeric, 1)             AS avg_turns,
               COUNT(CASE WHEN s.produced_commit THEN 1 END) AS sessions_with_commit,
               ROUND(
                   COUNT(CASE WHEN s.produced_commit THEN 1 END) * 100.0
                   / GREATEST(COUNT(s.session_trace_id), 1), 1
               ) AS commit_conversion_pct
        FROM sessions s
        WHERE TRUE {since}
        GROUP BY COALESCE(s.dominant_intent, 'general')
        ORDER BY session_count DESC
    """)
    rows = (await session.execute(sql)).mappings().all()
    return [
        {
            "intent": r["intent"],
            "session_count": r["session_count"],
            "cost_usd": float(r["cost_usd"]),
            "avg_quality_score": float(r["avg_quality"]) if r["avg_quality"] is not None else None,
            "avg_turns": float(r["avg_turns"]) if r["avg_turns"] is not None else None,
            "sessions_with_commit": r["sessions_with_commit"],
            "commit_conversion_pct": float(r["commit_conversion_pct"]) if r["commit_conversion_pct"] is not None else None,
        }
        for r in rows
    ]
