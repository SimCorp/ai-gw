"""
Developer portal authentication — shim over unified_auth.

/dev-auth/login, /register, /me, /logout, /change-password delegate to unified_auth.
Portal-specific endpoints (profile, select-team, stats) stay here and query users table.
Session key: session:{token}  (unified format)
"""
from __future__ import annotations

import json
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.routers.unified_auth import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    _session_key,
    get_current_user,
)
from app.routers.unified_auth import (
    change_password as _unified_change_password,
)
from app.routers.unified_auth import (
    login as _unified_login,
)
from app.routers.unified_auth import (
    logout as _unified_logout,
)
from app.routers.unified_auth import (
    register as _unified_register,
)

router = APIRouter(prefix="/dev-auth", tags=["developer-auth"])

_SESSION_TTL = int(timedelta(days=7).total_seconds())
_SESSION_TTL_REMEMBER = int(timedelta(days=30).total_seconds())


def _rate_limit_key(request: Request) -> str:
    if settings.dev_bypass_auth:
        test_id = request.headers.get("X-Test-Client-ID")
        if test_id:
            return f"test:{test_id}"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _get_current_developer(
    authorization: str | None = Header(default=None),
    request: Request = None,
) -> dict:
    """Backwards-compat dependency. Validates session and checks developer role.
    Returns unified session payload but also maps user_id → developer_id for compat."""
    user = await get_current_user(authorization, request)
    roles = [r["role"] for r in user.get("roles", [])]
    if not any(r in roles for r in ("developer", "platform_admin", "team_admin", "area_owner")):
        raise HTTPException(status_code=403, detail="Developer access required")
    # Backwards compat: expose developer_id as alias for user_id
    if "developer_id" not in user:
        user = {**user, "developer_id": user["user_id"]}
    return user


# ---------------------------------------------------------------------------
# Auth routes (delegate to unified)
# ---------------------------------------------------------------------------

@router.post("/register", status_code=201)
async def register(
    body: RegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    # Apply corporate domain restriction if configured
    if settings.allowed_email_domains:
        domain = body.email.split("@")[1]
        if domain not in settings.allowed_email_domains:
            raise HTTPException(status_code=422, detail="Registration is restricted to corporate email addresses")
    result = await _unified_register(body, request, session)
    # Map to dev portal format
    u = result["user"]
    return {
        "token": result["token"],
        "developer_id": u["user_id"],
        "email": u["email"],
        "display_name": u["display_name"],
        "team_id": u.get("primary_team_id"),
        "team_name": u.get("team_name"),
        "must_change_password": result.get("must_change_password", False),
    }


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    result = await _unified_login(body, request, session)
    u = result["user"]
    roles = [r["role"] for r in u.get("roles", [])]
    if not any(r in roles for r in ("developer", "platform_admin", "team_admin", "area_owner")):
        token = result["token"]
        await request.app.state.redis.delete(_session_key(token))
        raise HTTPException(status_code=403, detail="Developer portal access required")

    return {
        "token": result["token"],
        "developer_id": u["user_id"],
        "email": u["email"],
        "display_name": u["display_name"],
        "team_id": u.get("primary_team_id"),
        "team_name": u.get("team_name"),
        "must_change_password": result.get("must_change_password", False),
    }


@router.get("/me")
async def me(developer: dict = Depends(_get_current_developer)):
    return developer


@router.post("/logout")
async def logout(
    request: Request,
    authorization: str | None = Header(default=None),
):
    return await _unified_logout(request, authorization)


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    return await _unified_change_password(body, request, authorization, session)


# ---------------------------------------------------------------------------
# Portal-specific routes
# ---------------------------------------------------------------------------

class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=200)


@router.patch("/profile")
async def update_profile(
    body: ProfileUpdate,
    request: Request,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    developer = await _get_current_developer(authorization, request)
    if body.display_name is None:
        return developer

    display_name = body.display_name.strip()
    await session.execute(
        text("UPDATE users SET display_name = :dn, updated_at = NOW() WHERE id = CAST(:id AS uuid)"),
        {"dn": display_name, "id": developer["user_id"]},
    )
    await session.commit()

    token = (authorization or "").removeprefix("Bearer ").strip()
    new_payload = {**developer, "display_name": display_name}
    ttl = _SESSION_TTL_REMEMBER if len(token) > 40 else _SESSION_TTL
    await request.app.state.redis.setex(_session_key(token), ttl, json.dumps(new_payload))
    return new_payload


@router.post("/select-team")
async def select_team(
    team_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    developer = await _get_current_developer(authorization, request)
    row = (await session.execute(
        text("SELECT id, name FROM teams WHERE id = CAST(:id AS uuid)"),
        {"id": team_id},
    )).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Team not found")

    member_row = (await session.execute(
        text("""
            SELECT id FROM team_members
            WHERE team_id = CAST(:team_id AS uuid)
              AND (user_id = CAST(:uid AS uuid) OR developer_id = CAST(:uid AS uuid))
        """),
        {"team_id": team_id, "uid": developer["user_id"]},
    )).first()
    if not member_row:
        raise HTTPException(status_code=403, detail="You are not a member of this team")

    await session.execute(
        text("UPDATE users SET primary_team_id = CAST(:team_id AS uuid) WHERE id = CAST(:id AS uuid)"),
        {"team_id": team_id, "id": developer["user_id"]},
    )
    await session.commit()

    token = (authorization or "").removeprefix("Bearer ").strip()
    new_payload = {**developer, "primary_team_id": team_id, "team_id": team_id, "team_name": row["name"]}
    await request.app.state.redis.setex(_session_key(token), _SESSION_TTL, json.dumps(new_payload))
    return new_payload


# ---------------------------------------------------------------------------
# /dev-auth/me/stats — kept here (large endpoint, developer-only)
# ---------------------------------------------------------------------------

@router.get("/me/stats")
async def my_stats(
    period: str = "7d",
    developer: dict = Depends(_get_current_developer),
    session: AsyncSession = Depends(get_session),
):
    valid_periods = {"7d", "30d", "90d", "mtd", "all"}
    if period not in valid_periods:
        period = "7d"

    developer_id = developer["user_id"]
    team_id = developer.get("primary_team_id") or developer.get("team_id")

    since_map = {
        "7d":  "AND cr.created_at >= NOW() - INTERVAL '7 days'",
        "30d": "AND cr.created_at >= NOW() - INTERVAL '30 days'",
        "90d": "AND cr.created_at >= NOW() - INTERVAL '90 days'",
        "mtd": "AND cr.created_at >= date_trunc('month', NOW())",
        "all": "",
    }
    since = since_map[period]
    since_doe = since.replace("AND cr.created_at", "AND doe.occurred_at")
    since_s   = since.replace("AND cr.created_at", "AND s.first_request_at")

    cost_row = (await session.execute(text(f"""
        SELECT
            COUNT(cr.id)                                                              AS request_count,
            COALESCE(SUM(cr.tokens_input + cr.tokens_output), 0)                     AS total_tokens,
            COALESCE(ROUND(SUM(cr.cost_usd)::numeric, 6), 0)                         AS cost_usd,
            COALESCE(SUM(cr.tool_invocation_count), 0)                               AS tool_invocations,
            ROUND((AVG(CASE WHEN cr.cache_hit THEN 1.0 ELSE 0.0 END)*100)::numeric, 1) AS cache_hit_pct,
            ROUND(AVG(cr.latency_ms)::numeric, 0)                                    AS avg_latency_ms,
            COUNT(CASE WHEN cr.request_error_type IS NOT NULL THEN 1 END)            AS error_count,
            COUNT(DISTINCT cr.repo)                                                   AS repo_count,
            COALESCE(SUM(cr.retry_count), 0)                                         AS total_retries
        FROM cost_records cr
        WHERE cr.developer_id = CAST(:dev_id AS uuid) {since}
    """), {"dev_id": developer_id})).mappings().one()

    output_totals = (await session.execute(text(f"""
        SELECT
            COALESCE(SUM(doe.commit_count), 0)                                       AS total_commits,
            COUNT(CASE WHEN doe.event_type IN ('pr_opened','pr_merged') THEN 1 END)  AS total_prs,
            COUNT(CASE WHEN doe.event_type = 'pr_merged' THEN 1 END)                AS merged_prs
        FROM developer_output_events doe
        WHERE doe.developer_id = CAST(:dev_id AS uuid) {since_doe}
    """), {"dev_id": developer_id})).mappings().one()

    cost_usd     = float(cost_row["cost_usd"])
    total_prs    = int(output_totals["total_prs"])
    total_commits = int(output_totals["total_commits"])
    merged_prs   = int(output_totals["merged_prs"])

    cost_per_pr     = round(cost_usd / total_prs, 4)    if total_prs    > 0 else None
    cost_per_commit = round(cost_usd / total_commits, 4) if total_commits > 0 else None
    pr_merge_rate   = round(merged_prs * 100.0 / total_prs, 1) if total_prs > 0 else None

    team_budget_info = None
    if team_id:
        budget_row = (await session.execute(text("""
            SELECT t.monthly_budget_usd,
                   COALESCE(SUM(cr.cost_usd), 0) AS team_mtd_spend
            FROM teams t
            LEFT JOIN cost_records cr ON cr.team_id = t.id
              AND cr.created_at >= date_trunc('month', NOW())
            WHERE t.id = CAST(:team_id AS uuid)
            GROUP BY t.monthly_budget_usd
        """), {"team_id": team_id})).mappings().one_or_none()
        if budget_row:
            team_limit = float(budget_row["monthly_budget_usd"]) if budget_row["monthly_budget_usd"] else None
            team_spent = float(budget_row["team_mtd_spend"])
            team_budget_info = {
                "monthly_budget_usd": team_limit,
                "team_mtd_spend_usd": team_spent,
                "pct_used": round(team_spent * 100 / team_limit, 1) if team_limit else None,
                "remaining_usd": round(team_limit - team_spent, 4) if team_limit else None,
            }

    session_row = (await session.execute(text(f"""
        SELECT COUNT(s.session_trace_id)                                AS session_count,
               ROUND(AVG(s.quality_score)::numeric, 2)                  AS avg_quality,
               ROUND(AVG(s.turn_count)::numeric, 1)                     AS avg_turns,
               ROUND(AVG(s.avg_inter_request_s)::numeric, 0)            AS avg_inter_s,
               COUNT(CASE WHEN s.produced_commit THEN 1 END)            AS sessions_with_commit
        FROM sessions s
        WHERE s.developer_id = CAST(:dev_id AS uuid) {since_s}
    """), {"dev_id": developer_id})).mappings().one()

    session_count = int(session_row["session_count"])
    commit_conversion_pct = (
        round(int(session_row["sessions_with_commit"]) * 100.0 / session_count, 1)
        if session_count > 0 else None
    )

    hints = []
    request_count = int(cost_row["request_count"])
    retry_count   = int(cost_row["total_retries"])
    retry_rate    = retry_count / max(1, request_count)

    if retry_rate > 0.3:
        hints.append({"type": "high_retry_rate", "severity": "warning",
            "message": f"Your retry rate is {retry_rate:.0%}. Try scoping prompts to a single task."})
    if cost_row["cache_hit_pct"] is not None and float(cost_row["cache_hit_pct"]) < 20 and request_count > 20:
        hints.append({"type": "low_cache_hit", "severity": "info",
            "message": "Less than 20% of your requests hit the semantic cache."})
    if cost_per_pr is not None and cost_per_pr > 50:
        hints.append({"type": "high_cost_per_pr", "severity": "warning",
            "message": f"Your cost per PR is ${cost_per_pr:.2f}. Top quartile developers achieve <$10/PR."})

    daily_rows = (await session.execute(text("""
        SELECT date, request_count, cost_usd, cache_hits, tool_invocations, error_count
        FROM developer_activity_log
        WHERE developer_id = CAST(:dev_id AS uuid)
        ORDER BY date DESC LIMIT 30
    """), {"dev_id": developer_id})).mappings().all()

    return {
        "developer_id": developer_id,
        "email": developer.get("email"),
        "display_name": developer.get("display_name"),
        "period": period,
        "summary": {
            "request_count": request_count,
            "total_tokens": int(cost_row["total_tokens"]),
            "cost_usd": cost_usd,
            "tool_invocations": int(cost_row["tool_invocations"]),
            "cache_hit_pct": float(cost_row["cache_hit_pct"]) if cost_row["cache_hit_pct"] is not None else None,
            "avg_latency_ms": int(cost_row["avg_latency_ms"]) if cost_row["avg_latency_ms"] is not None else None,
            "error_count": int(cost_row["error_count"]),
            "repo_count": int(cost_row["repo_count"]),
        },
        "roi": {
            "total_commits": total_commits, "total_prs": total_prs, "merged_prs": merged_prs,
            "cost_per_pr": cost_per_pr, "cost_per_commit": cost_per_commit,
            "pr_merge_rate_pct": pr_merge_rate,
        },
        "session_quality": {
            "session_count": session_count,
            "avg_quality_score": float(session_row["avg_quality"]) if session_row["avg_quality"] is not None else None,
            "avg_turns": float(session_row["avg_turns"]) if session_row["avg_turns"] is not None else None,
            "avg_inter_request_s": float(session_row["avg_inter_s"]) if session_row["avg_inter_s"] is not None else None,
            "commit_conversion_pct": commit_conversion_pct,
        },
        "team_budget": team_budget_info,
        "optimization_hints": hints,
        "daily": [
            {"date": str(r["date"]), "request_count": r["request_count"],
             "cost_usd": float(r["cost_usd"]), "cache_hits": r["cache_hits"],
             "tool_invocations": r["tool_invocations"], "error_count": r["error_count"]}
            for r in daily_rows
        ],
    }
