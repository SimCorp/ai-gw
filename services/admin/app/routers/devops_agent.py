"""DevOps AI agent — inspects and diagnoses the AI gateway.

Calls litellm directly (bypassing the cache and auth proxy services) so
the agent remains operational even when those services are degraded.

The agentic loop runs entirely server-side: the LLM decides which tools to
call, the backend executes them, and the results are fed back until the
model produces a final text reply.
"""

import asyncio
import json
import time
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin_auth
from app.config import settings
from app.db import get_session

router = APIRouter(prefix="/devops-agent", tags=["devops-agent"])

_MAX_ROUNDS = 6  # maximum tool-call rounds before forcing a final answer
_LLM_TIMEOUT = 45.0
_TOOL_TIMEOUT = 8.0
_MODEL = "claude-sonnet-4-6"

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM = """You are an expert DevOps AI agent embedded in the AI Gateway admin portal.
You have direct access to live gateway data via tools. Use them proactively to give
accurate, data-driven answers.

You can:
- Check the health and latency of every gateway service
- Analyse error patterns, cache performance, and model usage
- Review team budgets and identify overspend or waste
- Inspect recent admin actions in the audit log
- Identify at-risk developers and struggling sessions
- Search live container logs (query_logs — Loki) to find WHY a service failed
- Query time-series metrics (query_metrics — PromQL) for resource trends
- Summarise per-container health (get_container_state) — memory, CPU, restarts

When a service is unhealthy or erroring, use query_logs to read its actual error
output and get_container_state / query_metrics to check for OOM, CPU saturation, or
restarts — don't stop at "it's down", find the root cause.

When asked to "inspect", "troubleshoot", or "optimise" the gateway:
1. Call the relevant tools first to gather live data
2. Summarise the findings clearly — use numbers and specific names
3. Give concrete, prioritised recommendations

Be concise. Prefer bullet points for findings. Flag critical issues first.
Never make up data — if a tool returns an error, say so and work around it."""

# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function-calling format — litellm translates)
# ---------------------------------------------------------------------------

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_service_health",
            "description": (
                "Check live health of all gateway services (auth, cache, litellm, observability), "
                "Redis, and PostgreSQL. Returns status, HTTP code, and latency in ms."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_gateway_metrics",
            "description": (
                "Get gateway traffic metrics: request volume, cache hit rate, error rate, "
                "and average latency for a given period."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": ["1h", "6h", "24h", "7d", "30d"],
                        "description": "Time window for metrics",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_errors",
            "description": (
                "Fetch recent API request errors from cost_records. Includes error type, "
                "model, team, developer, and timestamp."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max errors to return (1–50)",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_budget_status",
            "description": (
                "Check monthly budget utilisation for all teams. Shows spend, budget, "
                "percentage used, and which teams are over or near their limit."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_model_usage",
            "description": (
                "Get a breakdown of model usage: which models are called most, total "
                "tokens, cost, and cache hit rate per model."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": ["24h", "7d", "30d"],
                        "description": "Time window",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_audit_log",
            "description": (
                "Retrieve recent admin audit log entries. Optionally filter by action keyword."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Entries to return (1–50)"},
                    "action_filter": {
                        "type": "string",
                        "description": "Substring to filter action field (e.g. 'revoke', 'policy')",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_teams_by_spend",
            "description": (
                "Get teams ranked by total spend for a given period, including request count, "
                "token usage, and cache efficiency."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": ["24h", "7d", "30d", "mtd"],
                        "description": "Time window",
                    },
                    "limit": {"type": "integer", "description": "Number of teams to return"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_logs",
            "description": (
                "Search container logs (Loki) — the live stdout/stderr of every gateway "
                "service. Use this to find WHY something failed: errors, stack traces, "
                "startup problems. Logs are structured JSON with a request_id."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "description": (
                            "Compose service name to filter (e.g. cache, auth, litellm, "
                            "admin, observability). Omit to search all services."
                        ),
                    },
                    "grep": {
                        "type": "string",
                        "description": "Optional substring to filter log lines (e.g. 'error', a request_id).",
                    },
                    "since": {
                        "type": "string",
                        "enum": ["15m", "1h", "6h", "24h"],
                        "description": "Look-back window (default 1h).",
                    },
                    "limit": {"type": "integer", "description": "Max lines (default 50, max 200)."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_metrics",
            "description": (
                "Run a PromQL query against Prometheus for time-series metrics: per-container "
                "CPU/memory (cAdvisor), host metrics, and service request metrics. Use for "
                "resource trends, leaks, and saturation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "promql": {
                        "type": "string",
                        "description": (
                            "PromQL expression, e.g. "
                            'container_memory_usage_bytes{name="ai-gateway-cache-1"} or '
                            "rate(container_cpu_usage_seconds_total[5m])."
                        ),
                    },
                    "range": {
                        "type": "string",
                        "enum": ["instant", "15m", "1h", "6h", "24h"],
                        "description": "Instant query, or a range (default instant).",
                    },
                },
                "required": ["promql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_container_state",
            "description": (
                "Summarise per-container health from metrics: restart counts, memory, and CPU "
                "for each gateway container. Use to spot a crashing/OOMing/CPU-bound service."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "description": "Optional container/service name substring to filter.",
                    },
                },
                "required": [],
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


async def _tool_check_service_health(request: Request, session: AsyncSession) -> dict:
    from app.routers.system import _collect_health

    return await _collect_health(request, session)


async def _tool_get_gateway_metrics(session: AsyncSession, period: str = "24h") -> dict:
    _interval = {
        "1h": "1 hour",
        "6h": "6 hours",
        "24h": "24 hours",
        "7d": "7 days",
        "30d": "30 days",
    }.get(period, "24 hours")
    try:
        row = (
            (
                await session.execute(
                    text(f"""
            SELECT
                COUNT(*)                                                        AS total_requests,
                COUNT(*) FILTER (WHERE request_error_type IS NOT NULL)          AS error_count,
                ROUND((AVG(CASE WHEN cache_hit THEN 1.0 ELSE 0.0 END)*100)::numeric, 1)   AS cache_hit_pct,
                ROUND(AVG(latency_ms)::numeric, 0)                                       AS avg_latency_ms,
                ROUND(SUM(cost_usd)::numeric, 4)                               AS total_cost_usd,
                COALESCE(SUM(tokens_input + tokens_output), 0)                  AS total_tokens
            FROM cost_records
            WHERE created_at >= NOW() - INTERVAL '{_interval}'
        """)
                )
            )
            .mappings()
            .one()
        )
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
    except Exception as exc:
        return {"error": str(exc)}


async def _tool_get_recent_errors(session: AsyncSession, limit: int = 20) -> list:
    limit = max(1, min(limit, 50))
    try:
        rows = (
            (
                await session.execute(
                    text(f"""
            SELECT cr.created_at, cr.request_error_type, cr.model,
                   d.email AS developer_email, t.name AS team_name,
                   cr.latency_ms, cr.retry_count
            FROM cost_records cr
            LEFT JOIN developers d ON d.id = cr.developer_id
            LEFT JOIN teams t ON t.id = cr.team_id
            WHERE cr.request_error_type IS NOT NULL
            ORDER BY cr.created_at DESC
            LIMIT {limit}
        """)
                )
            )
            .mappings()
            .all()
        )
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
    except Exception as exc:
        return [{"error": str(exc)}]


async def _tool_get_budget_status(session: AsyncSession) -> list:
    try:
        rows = (
            (
                await session.execute(
                    text("""
            SELECT t.name AS team_name,
                   p.monthly_budget_usd,
                   COALESCE(ROUND(SUM(cr.cost_usd)::numeric, 4), 0) AS spent_usd,
                   CASE WHEN p.monthly_budget_usd > 0
                        THEN ROUND(SUM(cr.cost_usd) / p.monthly_budget_usd * 100, 1)
                   END AS pct_used
            FROM teams t
            LEFT JOIN policies p ON p.team_id = t.id
            LEFT JOIN cost_records cr ON cr.team_id = t.id
                AND cr.created_at >= date_trunc('month', NOW())
            WHERE p.monthly_budget_usd IS NOT NULL AND p.monthly_budget_usd > 0
            GROUP BY t.name, p.monthly_budget_usd
            ORDER BY pct_used DESC NULLS LAST
        """)
                )
            )
            .mappings()
            .all()
        )
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
    except Exception as exc:
        return [{"error": str(exc)}]


async def _tool_get_model_usage(session: AsyncSession, period: str = "7d") -> list:
    _interval = {"24h": "24 hours", "7d": "7 days", "30d": "30 days"}.get(period, "7 days")
    try:
        rows = (
            (
                await session.execute(
                    text(f"""
            SELECT model,
                   COUNT(*) AS request_count,
                   COALESCE(SUM(tokens_input + tokens_output), 0) AS total_tokens,
                   ROUND(SUM(cost_usd)::numeric, 4) AS cost_usd,
                   ROUND((AVG(CASE WHEN cache_hit THEN 1.0 ELSE 0.0 END)*100)::numeric, 1) AS cache_hit_pct,
                   ROUND(AVG(latency_ms)::numeric, 0) AS avg_latency_ms
            FROM cost_records
            WHERE created_at >= NOW() - INTERVAL '{_interval}'
              AND model IS NOT NULL
            GROUP BY model
            ORDER BY cost_usd DESC
            LIMIT 15
        """)
                )
            )
            .mappings()
            .all()
        )
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
    except Exception as exc:
        return [{"error": str(exc)}]


async def _tool_get_audit_log(
    session: AsyncSession,
    limit: int = 20,
    action_filter: str | None = None,
) -> list:
    limit = max(1, min(limit, 50))
    if action_filter:
        rows = (
            (
                await session.execute(
                    text("""
                SELECT timestamp, actor, action, resource_type, resource_id, detail
                FROM audit_log
                WHERE action ILIKE :filter
                ORDER BY timestamp DESC
                LIMIT :limit
            """),
                    {"filter": f"%{action_filter[:40]}%", "limit": limit},
                )
            )
            .mappings()
            .all()
        )
    else:
        rows = (
            (
                await session.execute(
                    text("""
                SELECT timestamp, actor, action, resource_type, resource_id, detail
                FROM audit_log
                ORDER BY timestamp DESC
                LIMIT :limit
            """),
                    {"limit": limit},
                )
            )
            .mappings()
            .all()
        )
    try:
        rows = list(rows)
        return [
            {
                "timestamp": str(r["timestamp"]),
                "actor": r["actor"],
                "action": r["action"],
                "resource_type": r["resource_type"],
                "resource_id": r["resource_id"],
                "detail": r["detail"],
            }
            for r in rows
        ]
    except Exception as exc:
        return [{"error": str(exc)}]


async def _tool_get_top_teams_by_spend(
    session: AsyncSession,
    period: str = "mtd",
    limit: int = 10,
) -> list:
    limit = max(1, min(limit, 30))
    _interval = {
        "24h": "AND cr.created_at >= NOW() - INTERVAL '24 hours'",
        "7d": "AND cr.created_at >= NOW() - INTERVAL '7 days'",
        "30d": "AND cr.created_at >= NOW() - INTERVAL '30 days'",
        "mtd": "AND cr.created_at >= date_trunc('month', NOW())",
    }.get(period, "AND cr.created_at >= date_trunc('month', NOW())")
    try:
        rows = (
            (
                await session.execute(
                    text(f"""
            SELECT t.name AS team_name,
                   COUNT(cr.id) AS request_count,
                   COALESCE(SUM(cr.tokens_input + cr.tokens_output), 0) AS total_tokens,
                   ROUND(SUM(cr.cost_usd)::numeric, 4) AS cost_usd,
                   ROUND((AVG(CASE WHEN cr.cache_hit THEN 1.0 ELSE 0.0 END)*100)::numeric, 1) AS cache_hit_pct
            FROM teams t
            LEFT JOIN cost_records cr ON cr.team_id = t.id {_interval}
            GROUP BY t.name
            ORDER BY cost_usd DESC NULLS LAST
            LIMIT {limit}
        """)
                )
            )
            .mappings()
            .all()
        )
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
    except Exception as exc:
        return [{"error": str(exc)}]


# --- Observability tools (Loki logs + Prometheus metrics) ---

_SINCE_SECONDS = {"15m": 900, "1h": 3600, "6h": 21600, "24h": 86400}


async def _tool_query_logs(
    service: str | None = None,
    grep: str | None = None,
    since: str = "1h",
    limit: int = 50,
) -> dict:
    """Search container logs via Loki LogQL."""
    limit = max(1, min(limit, 200))
    secs = _SINCE_SECONDS.get(since, 3600)
    selector = f'{{compose_service="{service}"}}' if service else '{compose_project="ai-gateway"}'
    if grep:
        safe = grep.replace("\\", "\\\\").replace('"', '\\"')
        selector += f' |= "{safe}"'
    end = time.time()
    try:
        async with httpx.AsyncClient(timeout=_TOOL_TIMEOUT) as client:
            r = await client.get(
                f"{settings.loki_url}/loki/api/v1/query_range",
                params={
                    "query": selector,
                    "start": str(int((end - secs) * 1e9)),
                    "end": str(int(end * 1e9)),
                    "limit": str(limit),
                    "direction": "backward",
                },
            )
            r.raise_for_status()
            streams = r.json().get("data", {}).get("result", [])
        lines = []
        for stream in streams:
            svc = stream.get("stream", {}).get("compose_service", "?")
            for _ts, line in stream.get("values", []):
                lines.append({"service": svc, "line": line[:500]})
        return {"count": len(lines[:limit]), "lines": lines[:limit]}
    except Exception as exc:
        return {"error": str(exc)}


async def _tool_query_metrics(promql: str, time_range: str = "instant") -> dict:
    """Run a PromQL query against Prometheus (instant or range)."""
    try:
        async with httpx.AsyncClient(timeout=_TOOL_TIMEOUT) as client:
            if time_range == "instant":
                r = await client.get(
                    f"{settings.prometheus_url}/api/v1/query", params={"query": promql}
                )
            else:
                secs = _SINCE_SECONDS.get(time_range, 3600)
                end = time.time()
                r = await client.get(
                    f"{settings.prometheus_url}/api/v1/query_range",
                    params={
                        "query": promql,
                        "start": str(end - secs),
                        "end": str(end),
                        "step": str(max(15, secs // 60)),
                    },
                )
            r.raise_for_status()
            res = r.json().get("data", {}).get("result", [])
        out = []
        for s in res[:20]:
            if "value" in s:
                out.append({"labels": s.get("metric", {}), "value": s["value"][1]})
            else:
                vals = s.get("values", [])
                out.append(
                    {
                        "labels": s.get("metric", {}),
                        "points": len(vals),
                        "last": vals[-1][1] if vals else None,
                    }
                )
        return {"series": len(res), "result": out}
    except Exception as exc:
        return {"error": str(exc)}


async def _tool_get_container_state(service: str | None = None) -> list:
    """Per-container memory / CPU / restart summary from cAdvisor metrics."""
    sel = f'{{name=~"ai-gateway-.*{service}.*"}}' if service else '{name=~"ai-gateway-.*"}'
    queries = {
        "memory_mb": f"container_memory_usage_bytes{sel} / 1024 / 1024",
        "cpu_pct": f"rate(container_cpu_usage_seconds_total{sel}[5m]) * 100",
        "restarts_1h": f"changes(container_last_seen{sel}[1h])",
    }
    out: dict[str, dict] = {}
    try:
        async with httpx.AsyncClient(timeout=_TOOL_TIMEOUT) as client:
            for metric, q in queries.items():
                r = await client.get(f"{settings.prometheus_url}/api/v1/query", params={"query": q})
                if r.status_code != 200:
                    continue
                for s in r.json().get("data", {}).get("result", []):
                    name = s.get("metric", {}).get("name", "?")
                    out.setdefault(name, {"container": name})[metric] = round(
                        float(s["value"][1]), 2
                    )
        return list(out.values())
    except Exception as exc:
        return [{"error": str(exc)}]


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------


async def _dispatch_tool(
    name: str,
    args: dict,
    request: Request,
    session: AsyncSession,
) -> Any:
    t0 = time.monotonic()
    try:
        if name == "check_service_health":
            result = await asyncio.wait_for(
                _tool_check_service_health(request, session), _TOOL_TIMEOUT
            )
        elif name == "get_gateway_metrics":
            result = await asyncio.wait_for(
                _tool_get_gateway_metrics(session, args.get("period", "24h")), _TOOL_TIMEOUT
            )
        elif name == "get_recent_errors":
            result = await asyncio.wait_for(
                _tool_get_recent_errors(session, args.get("limit", 20)), _TOOL_TIMEOUT
            )
        elif name == "get_budget_status":
            result = await asyncio.wait_for(_tool_get_budget_status(session), _TOOL_TIMEOUT)
        elif name == "get_model_usage":
            result = await asyncio.wait_for(
                _tool_get_model_usage(session, args.get("period", "7d")), _TOOL_TIMEOUT
            )
        elif name == "get_audit_log":
            result = await asyncio.wait_for(
                _tool_get_audit_log(session, args.get("limit", 20), args.get("action_filter")),
                _TOOL_TIMEOUT,
            )
        elif name == "get_top_teams_by_spend":
            result = await asyncio.wait_for(
                _tool_get_top_teams_by_spend(
                    session, args.get("period", "mtd"), args.get("limit", 10)
                ),
                _TOOL_TIMEOUT,
            )
        elif name == "query_logs":
            result = await asyncio.wait_for(
                _tool_query_logs(
                    args.get("service"),
                    args.get("grep"),
                    args.get("since", "1h"),
                    args.get("limit", 50),
                ),
                _TOOL_TIMEOUT,
            )
        elif name == "query_metrics":
            result = await asyncio.wait_for(
                _tool_query_metrics(args.get("promql", ""), args.get("range", "instant")),
                _TOOL_TIMEOUT,
            )
        elif name == "get_container_state":
            result = await asyncio.wait_for(
                _tool_get_container_state(args.get("service")), _TOOL_TIMEOUT
            )
        else:
            result = {"error": f"Unknown tool: {name}"}
    except asyncio.TimeoutError:
        result = {"error": "Tool timed out"}
    except Exception as exc:
        result = {"error": str(exc)[:200]}

    return {"result": result, "elapsed_ms": round((time.monotonic() - t0) * 1000, 1)}


# ---------------------------------------------------------------------------
# Agentic loop
# ---------------------------------------------------------------------------


async def _run_agent(
    user_messages: list[dict],
    request: Request,
    session: AsyncSession,
) -> dict:
    messages = [{"role": "system", "content": _SYSTEM}] + user_messages
    tool_log: list[dict] = []

    async with httpx.AsyncClient(timeout=_LLM_TIMEOUT) as client:
        for _round in range(_MAX_ROUNDS):
            resp = await client.post(
                f"{settings.litellm_url}/v1/chat/completions",
                json={
                    "model": _MODEL,
                    "messages": messages,
                    "tools": _TOOLS,
                    "tool_choice": "auto" if _round < _MAX_ROUNDS - 1 else "none",
                    "max_tokens": 1500,
                    "temperature": 0.2,
                },
                headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
            )
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"LLM error: {resp.status_code}")

            data = resp.json()
            choice = data["choices"][0]
            msg = choice["message"]
            messages.append(msg)

            tool_calls = msg.get("tool_calls") or []
            if not tool_calls or choice.get("finish_reason") == "stop":
                # Final answer
                return {"reply": msg.get("content", ""), "tool_log": tool_log}

            # Execute all tool calls in parallel
            dispatch_tasks = [
                _dispatch_tool(
                    tc["function"]["name"],
                    json.loads(tc["function"]["arguments"] or "{}"),
                    request,
                    session,
                )
                for tc in tool_calls
            ]
            results = await asyncio.gather(*dispatch_tasks)

            for tc, outcome in zip(tool_calls, results):
                fn_name = tc["function"]["name"]
                fn_args = json.loads(tc["function"]["arguments"] or "{}")
                tool_log.append(
                    {
                        "tool": fn_name,
                        "args": fn_args,
                        "elapsed_ms": outcome["elapsed_ms"],
                        "result_preview": _preview(outcome["result"]),
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(outcome["result"]),
                    }
                )

    return {
        "reply": "Reached maximum reasoning steps. Partial data collected.",
        "tool_log": tool_log,
    }


def _preview(result: Any) -> str:
    """Short human-readable preview of a tool result for the UI log."""
    if isinstance(result, dict) and "error" in result:
        return f"error: {result['error']}"
    if isinstance(result, list):
        return f"{len(result)} items"
    if isinstance(result, dict):
        keys = list(result.keys())[:4]
        return (
            "{"
            + ", ".join(f"{k}: {result[k]}" for k in keys)
            + ("..." if len(result) > 4 else "")
            + "}"
        )
    return str(result)[:80]


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


class AgentMessage(BaseModel):
    role: str
    content: str


class AgentRequest(BaseModel):
    messages: list[AgentMessage] = Field(..., max_length=30)


@router.post("/chat")
async def devops_agent_chat(
    body: AgentRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    _auth: dict = Depends(require_admin_auth),
):
    """Run the DevOps AI agent with live gateway tool access."""
    user_messages = [{"role": m.role, "content": m.content} for m in body.messages]
    return await _run_agent(user_messages, request, session)
