"""Scheduled optimization worker — runs the DevOps AI agent every 6 hours.

The agent uses the same tool infrastructure as the interactive DevOps agent,
plus a write-only `record_insight` tool. The LLM gathers live gateway data,
reasons over it, records structured findings, and optionally applies safe
auto-remediations (cache threshold tuning only).

Background task is started from the FastAPI lifespan in main.py.
"""

import asyncio
import json
import logging
import time
from typing import Any

import httpx
from app.config import settings

_log = logging.getLogger(__name__)

_INTERVAL = 6 * 60 * 60  # 6 hours between runs
_STARTUP_DELAY = 30  # seconds after startup before first run
_MAX_ROUNDS = 8
_LLM_TIMEOUT = 60.0
_TOOL_TIMEOUT = 10.0
_MODEL = "claude-sonnet-4-6"

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_SYSTEM = """You are an automated AI gateway optimization agent running on a schedule.
Your job is to analyse live gateway data and record actionable findings.

For each analysis run:
1. Call the data tools to gather metrics (health, errors, budgets, models, cache)
2. Identify findings — be specific: use team names, model names, percentages, dollar amounts
3. Call record_insight for each finding (aim for 3-8 insights per run; skip trivial ones)
4. Optionally call tune_cache_threshold if cache hit rate is clearly too low or too high

Severity guide:
- critical: service down, budget exceeded, error rate >30%
- warning: approaching limit, efficiency problem with clear cost impact, error rate >10%
- info: optimisation opportunity, usage pattern worth noting

For model right-sizing:
- Flag when a team uses claude-opus-4-7 for requests with <400 input tokens
- Calculate approximate savings: opus costs ~6x haiku; estimate monthly savings

For cache insights:
- Hit rate <25% → warning (consider lowering similarity threshold or adding system prompt reuse advice)
- Hit rate >70% with threshold <0.85 → info (threshold could be tightened)

Developer-specific insights (set developer_email when applicable):
- High retry rate for a specific team's requests
- A specific developer's error pattern

Record insights even when things look healthy — e.g. "cache hit rate is excellent at 72%"
(severity: info) gives developers positive signal too."""

_PROMPT = """Run a complete optimization analysis of the AI gateway.

Check all services, gather 24h and 7d metrics, review budget status, analyse model usage,
look at recent errors, and review top teams by spend.

Record all significant findings using record_insight. For each team using expensive models
for short prompts, calculate the potential monthly savings and record a model right-sizing
insight. If cache performance warrants a threshold adjustment, call tune_cache_threshold."""

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

_INSIGHT_CATEGORIES = ["cache", "model", "budget", "error", "health", "usage"]
_INSIGHT_SEVERITIES = ["critical", "warning", "info"]

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_service_health",
            "description": "Check health of all gateway services, Redis, and PostgreSQL.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_gateway_metrics",
            "description": "Get gateway traffic metrics: requests, errors, cache hit rate, latency, cost.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {"type": "string", "enum": ["1h", "6h", "24h", "7d", "30d"]}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_errors",
            "description": "Fetch recent API request errors with error type, model, team, developer.",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_budget_status",
            "description": "Check monthly budget utilisation for all teams.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_model_usage",
            "description": "Get model usage breakdown: requests, tokens, cost, cache hit rate per model.",
            "parameters": {
                "type": "object",
                "properties": {"period": {"type": "string", "enum": ["24h", "7d", "30d"]}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_teams_by_spend",
            "description": "Teams ranked by spend for a time window.",
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {"type": "string", "enum": ["24h", "7d", "30d", "mtd"]},
                    "limit": {"type": "integer"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_model_rightsizing_data",
            "description": (
                "Identify teams using expensive models (claude-opus-4-7) for short prompts "
                "(<400 input tokens). Returns team name, request count, avg tokens, estimated savings."
            ),
            "parameters": {
                "type": "object",
                "properties": {"period": {"type": "string", "enum": ["7d", "30d", "mtd"]}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_insight",
            "description": "Record an optimization finding or recommendation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": _INSIGHT_CATEGORIES,
                        "description": "Category of the finding",
                    },
                    "severity": {
                        "type": "string",
                        "enum": _INSIGHT_SEVERITIES,
                        "description": "Severity level",
                    },
                    "title": {"type": "string", "description": "Short title (max 80 chars)"},
                    "description": {
                        "type": "string",
                        "description": "Detailed description with specific numbers and team names",
                    },
                    "action": {
                        "type": "string",
                        "description": "Concrete recommended action",
                    },
                    "team_name": {
                        "type": "string",
                        "description": "Team name if team-specific (omit for org-wide)",
                    },
                    "developer_email": {
                        "type": "string",
                        "description": "Developer email if developer-specific",
                    },
                },
                "required": ["category", "severity", "title", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tune_cache_threshold",
            "description": (
                "Adjust the semantic cache similarity threshold. "
                "Only call this when cache hit rate clearly warrants a change. "
                "Safe bounds: 0.72–0.95."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "new_threshold": {
                        "type": "number",
                        "description": "New similarity threshold (0.72–0.95)",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Justification for the change",
                    },
                },
                "required": ["new_threshold", "reason"],
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Tool implementations (DB queries, no HTTP round-trips to the proxy)
# ---------------------------------------------------------------------------


async def _tool_check_service_health(pool) -> dict:
    return {"note": "service health check requires request context; skipping in worker"}


async def _tool_get_gateway_metrics(pool, period: str = "24h") -> dict:
    _interval = {
        "1h": "1 hour",
        "6h": "6 hours",
        "24h": "24 hours",
        "7d": "7 days",
        "30d": "30 days",
    }.get(period, "24 hours")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(f"""
            SELECT
                COUNT(*)                                                        AS total_requests,
                COUNT(*) FILTER (WHERE request_error_type IS NOT NULL)          AS error_count,
                ROUND(AVG(CASE WHEN cache_hit THEN 1.0 ELSE 0.0 END)*100, 1)   AS cache_hit_pct,
                ROUND(AVG(latency_ms), 0)                                       AS avg_latency_ms,
                ROUND(SUM(cost_usd)::numeric, 4)                               AS total_cost_usd,
                COALESCE(SUM(tokens_input + tokens_output), 0)                  AS total_tokens
            FROM cost_records
            WHERE created_at >= NOW() - INTERVAL '{_interval}'
        """)
    total = int(row["total_requests"] or 0)
    errors = int(row["error_count"] or 0)
    return {
        "period": period,
        "total_requests": total,
        "error_count": errors,
        "error_rate_pct": round(errors / max(total, 1) * 100, 1),
        "cache_hit_pct": float(row["cache_hit_pct"] or 0),
        "avg_latency_ms": int(row["avg_latency_ms"] or 0),
        "total_cost_usd": float(row["total_cost_usd"] or 0),
        "total_tokens": int(row["total_tokens"] or 0),
    }


async def _tool_get_recent_errors(pool, limit: int = 20) -> list:
    limit = max(1, min(limit, 50))
    async with pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT cr.created_at, cr.request_error_type, cr.model,
                   d.email AS developer_email, t.name AS team_name,
                   cr.latency_ms, cr.retry_count
            FROM cost_records cr
            LEFT JOIN developers d ON d.id = cr.developer_id
            LEFT JOIN organization_nodes t ON t.id = cr.node_id
            WHERE cr.request_error_type IS NOT NULL
            ORDER BY cr.created_at DESC
            LIMIT {limit}
        """)
    return [
        {
            "timestamp": str(r["created_at"]),
            "error_type": r["request_error_type"],
            "model": r["model"],
            "developer": r["developer_email"],
            "team": r["team_name"],
            "latency_ms": r["latency_ms"],
            "retries": r["retry_count"],
        }
        for r in rows
    ]


async def _tool_get_budget_status(pool) -> list:
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT t.name AS team_name,
                   t.monthly_budget_usd,
                   COALESCE(ROUND(SUM(cr.cost_usd)::numeric, 4), 0) AS spent_usd,
                   CASE WHEN t.monthly_budget_usd > 0
                        THEN ROUND(SUM(cr.cost_usd) / t.monthly_budget_usd * 100, 1)
                   END AS pct_used
            FROM organization_nodes t
            LEFT JOIN cost_records cr ON cr.node_id = t.id
                AND cr.created_at >= date_trunc('month', NOW())
            WHERE t.type = 'team'
              AND t.monthly_budget_usd IS NOT NULL AND t.monthly_budget_usd > 0
            GROUP BY t.name, t.monthly_budget_usd
            ORDER BY pct_used DESC NULLS LAST
        """)
    return [
        {
            "team": r["team_name"],
            "budget_usd": float(r["monthly_budget_usd"]),
            "spent_usd": float(r["spent_usd"]),
            "pct_used": float(r["pct_used"]) if r["pct_used"] is not None else None,
            "status": (
                "over_budget"
                if (r["pct_used"] or 0) >= 100
                else "warning"
                if (r["pct_used"] or 0) >= 80
                else "ok"
            ),
        }
        for r in rows
    ]


async def _tool_get_model_usage(pool, period: str = "7d") -> list:
    _interval = {"24h": "24 hours", "7d": "7 days", "30d": "30 days"}.get(period, "7 days")
    async with pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT model,
                   COUNT(*) AS request_count,
                   COALESCE(SUM(tokens_input + tokens_output), 0) AS total_tokens,
                   ROUND(SUM(cost_usd)::numeric, 4) AS cost_usd,
                   ROUND(AVG(CASE WHEN cache_hit THEN 1.0 ELSE 0.0 END)*100, 1) AS cache_hit_pct,
                   ROUND(AVG(latency_ms), 0) AS avg_latency_ms
            FROM cost_records
            WHERE created_at >= NOW() - INTERVAL '{_interval}'
              AND model IS NOT NULL
            GROUP BY model
            ORDER BY cost_usd DESC LIMIT 15
        """)
    return [
        {
            "model": r["model"],
            "requests": int(r["request_count"]),
            "total_tokens": int(r["total_tokens"]),
            "cost_usd": float(r["cost_usd"] or 0),
            "cache_hit_pct": float(r["cache_hit_pct"] or 0),
            "avg_latency_ms": int(r["avg_latency_ms"] or 0),
        }
        for r in rows
    ]


async def _tool_get_top_teams(pool, period: str = "mtd", limit: int = 10) -> list:
    limit = max(1, min(limit, 30))
    _where = {
        "24h": "AND cr.created_at >= NOW() - INTERVAL '24 hours'",
        "7d": "AND cr.created_at >= NOW() - INTERVAL '7 days'",
        "30d": "AND cr.created_at >= NOW() - INTERVAL '30 days'",
        "mtd": "AND cr.created_at >= date_trunc('month', NOW())",
    }.get(period, "AND cr.created_at >= date_trunc('month', NOW())")
    async with pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT t.name AS team_name,
                   COUNT(cr.id) AS request_count,
                   COALESCE(SUM(cr.tokens_input + cr.tokens_output), 0) AS total_tokens,
                   ROUND(SUM(cr.cost_usd)::numeric, 4) AS cost_usd,
                   ROUND(AVG(CASE WHEN cr.cache_hit THEN 1.0 ELSE 0.0 END)*100, 1) AS cache_hit_pct
            FROM organization_nodes t
            LEFT JOIN cost_records cr ON cr.node_id = t.id {_where}
            WHERE t.type = 'team'
            GROUP BY t.name
            ORDER BY cost_usd DESC NULLS LAST
            LIMIT {limit}
        """)
    return [
        {
            "team": r["team_name"],
            "requests": int(r["request_count"] or 0),
            "total_tokens": int(r["total_tokens"] or 0),
            "cost_usd": float(r["cost_usd"] or 0),
            "cache_hit_pct": float(r["cache_hit_pct"] or 0),
        }
        for r in rows
    ]


async def _tool_get_model_rightsizing(pool, period: str = "7d") -> list:
    _interval = {"7d": "7 days", "30d": "30 days", "mtd": "month"}.get(period, "7 days")
    _since = (
        "cr.created_at >= date_trunc('month', NOW())"
        if period == "mtd"
        else f"cr.created_at >= NOW() - INTERVAL '{_interval}'"
    )
    # Identify opus usage for short prompts (likely simple tasks)
    async with pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT t.name AS team_name,
                   COUNT(*) AS short_opus_requests,
                   ROUND(AVG(cr.tokens_input), 0) AS avg_input_tokens,
                   ROUND(SUM(cr.cost_usd)::numeric, 4) AS opus_cost_usd,
                   -- Haiku is roughly 1/6th the cost of Opus
                   ROUND(SUM(cr.cost_usd) * (5.0/6.0)::numeric, 4) AS potential_savings_usd
            FROM cost_records cr
            LEFT JOIN organization_nodes t ON t.id = cr.node_id
            WHERE {_since}
              AND cr.model ILIKE '%opus%'
              AND cr.tokens_input < 400
              AND cr.tokens_input IS NOT NULL
            GROUP BY t.name
            HAVING COUNT(*) >= 10
            ORDER BY potential_savings_usd DESC
        """)
    return [
        {
            "team": r["team_name"],
            "short_opus_requests": int(r["short_opus_requests"]),
            "avg_input_tokens": int(r["avg_input_tokens"] or 0),
            "opus_cost_usd": float(r["opus_cost_usd"] or 0),
            "potential_savings_usd": float(r["potential_savings_usd"] or 0),
        }
        for r in rows
    ]


async def _tool_record_insight(pool, pending_insights: list, args: dict) -> dict:
    """Buffer insight for bulk insert after the agent completes."""
    pending_insights.append(
        {
            "category": args.get("category", "usage"),
            "severity": args.get("severity", "info"),
            "title": str(args.get("title", ""))[:80],
            "description": str(args.get("description", ""))[:2000],
            "action": str(args.get("action", ""))[:500] if args.get("action") else None,
            "team_name": args.get("team_name"),
            "developer_email": args.get("developer_email"),
        }
    )
    return {"recorded": True, "total_buffered": len(pending_insights)}


async def _tool_tune_cache_threshold(pool, new_threshold: float, reason: str) -> dict:
    """Clamp and apply a new semantic similarity threshold to org_settings."""
    new_threshold = round(max(0.72, min(0.95, new_threshold)), 3)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO org_settings (key, value)
            VALUES ('semantic_similarity_threshold', $1)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """,
            str(new_threshold),
        )
        await conn.execute(
            """
            INSERT INTO audit_log (actor, action, resource_type, detail)
            VALUES ('optimization_worker', 'tune_cache_threshold', 'org_settings',
                    $1)
        """,
            json.dumps({"new_threshold": new_threshold, "reason": reason[:300]}),
        )
    return {"applied": True, "new_threshold": new_threshold, "reason": reason}


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------


async def _dispatch(name: str, args: dict, pool, pending_insights: list) -> Any:
    t0 = time.monotonic()
    try:
        if name == "check_service_health":
            result = await asyncio.wait_for(_tool_check_service_health(pool), _TOOL_TIMEOUT)
        elif name == "get_gateway_metrics":
            result = await asyncio.wait_for(
                _tool_get_gateway_metrics(pool, args.get("period", "24h")), _TOOL_TIMEOUT
            )
        elif name == "get_recent_errors":
            result = await asyncio.wait_for(
                _tool_get_recent_errors(pool, args.get("limit", 20)), _TOOL_TIMEOUT
            )
        elif name == "get_budget_status":
            result = await asyncio.wait_for(_tool_get_budget_status(pool), _TOOL_TIMEOUT)
        elif name == "get_model_usage":
            result = await asyncio.wait_for(
                _tool_get_model_usage(pool, args.get("period", "7d")), _TOOL_TIMEOUT
            )
        elif name == "get_top_teams_by_spend":
            result = await asyncio.wait_for(
                _tool_get_top_teams(pool, args.get("period", "mtd"), args.get("limit", 10)),
                _TOOL_TIMEOUT,
            )
        elif name == "get_model_rightsizing_data":
            result = await asyncio.wait_for(
                _tool_get_model_rightsizing(pool, args.get("period", "7d")), _TOOL_TIMEOUT
            )
        elif name == "record_insight":
            result = await asyncio.wait_for(
                _tool_record_insight(pool, pending_insights, args), _TOOL_TIMEOUT
            )
        elif name == "tune_cache_threshold":
            result = await asyncio.wait_for(
                _tool_tune_cache_threshold(
                    pool, args.get("new_threshold", 0.85), args.get("reason", "")
                ),
                _TOOL_TIMEOUT,
            )
        else:
            result = {"error": f"Unknown tool: {name}"}
    except asyncio.TimeoutError:
        result = {"error": "Tool timed out"}
    except Exception as exc:
        result = {"error": str(exc)[:200]}
    elapsed = round((time.monotonic() - t0) * 1000, 1)
    _log.debug("Tool %s: %.0fms", name, elapsed)
    return result


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------


async def _run_optimization_agent(pool) -> list[dict]:
    """Run the optimization agent and return buffered insights."""
    pending_insights: list[dict] = []
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": _PROMPT},
    ]

    async with httpx.AsyncClient(timeout=_LLM_TIMEOUT) as client:
        for _round in range(_MAX_ROUNDS):
            try:
                resp = await client.post(
                    f"{settings.litellm_url}/v1/chat/completions",
                    json={
                        "model": _MODEL,
                        "messages": messages,
                        "tools": _TOOLS,
                        "tool_choice": "auto" if _round < _MAX_ROUNDS - 1 else "none",
                        "max_tokens": 2000,
                        "temperature": 0.1,
                    },
                    headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
                )
            except Exception as exc:
                _log.error("LLM call failed in round %d: %s", _round, exc)
                break

            if resp.status_code != 200:
                _log.error("LLM returned %d: %s", resp.status_code, resp.text[:200])
                break

            data = resp.json()
            choice = data["choices"][0]
            msg = choice["message"]
            messages.append(msg)

            tool_calls = msg.get("tool_calls") or []
            if not tool_calls or choice.get("finish_reason") == "stop":
                break

            results = await asyncio.gather(
                *[
                    _dispatch(
                        tc["function"]["name"],
                        json.loads(tc["function"]["arguments"] or "{}"),
                        pool,
                        pending_insights,
                    )
                    for tc in tool_calls
                ]
            )

            for tc, result in zip(tool_calls, results):
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(result),
                    }
                )

    return pending_insights


# ---------------------------------------------------------------------------
# Insight persistence
# ---------------------------------------------------------------------------


async def _flush_insights(pool, insights: list[dict]) -> int:
    if not insights:
        return 0

    # Expire old insights (older than 25 hours) before inserting new ones
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM ai_insights WHERE generated_at < NOW() - INTERVAL '25 hours'"
        )

        count = 0
        for ins in insights:
            team_id = None
            if ins.get("team_name"):
                row = await conn.fetchrow(
                    "SELECT id FROM organization_nodes WHERE name = $1 AND type = 'team'",
                    ins["team_name"],
                )
                team_id = row["id"] if row else None

            developer_id = None
            if ins.get("developer_email"):
                row = await conn.fetchrow(
                    "SELECT id FROM developers WHERE email = $1", ins["developer_email"]
                )
                developer_id = row["id"] if row else None

            await conn.execute(
                """
                INSERT INTO ai_insights
                    (category, severity, title, description, action,
                     team_id, team_name, developer_id, source)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'optimization_worker')
            """,
                ins["category"],
                ins["severity"],
                ins["title"],
                ins["description"],
                ins.get("action"),
                team_id,
                ins.get("team_name"),
                developer_id,
            )
            count += 1

    return count


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


async def optimization_loop(pool):
    """Background task — waits for startup, then runs every _INTERVAL seconds."""
    await asyncio.sleep(_STARTUP_DELAY)

    while True:
        try:
            _log.info("Optimization worker: starting analysis run")
            t0 = time.monotonic()
            insights = await _run_optimization_agent(pool)
            stored = await _flush_insights(pool, insights)
            elapsed = round(time.monotonic() - t0, 1)
            _log.info("Optimization worker: stored %d insights in %.1fs", stored, elapsed)
        except asyncio.CancelledError:
            _log.info("Optimization worker: cancelled")
            return
        except Exception as exc:
            _log.exception("Optimization worker: run failed: %s", exc)

        await asyncio.sleep(_INTERVAL)


async def start_optimization_worker(pool):
    """Supervisor wrapper — restarts optimization_loop if it crashes unexpectedly."""
    while True:
        try:
            await optimization_loop(pool)
            return  # clean exit (CancelledError propagated out of loop)
        except asyncio.CancelledError:
            _log.info("Optimization worker supervisor: shutdown")
            raise
        except Exception:
            _log.exception("Optimization worker supervisor: unexpected crash, restarting in 60s")
            await asyncio.sleep(60)
