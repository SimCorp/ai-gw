"""
Developer portal authentication.
Provides register / login / me / logout for the developer portal (localhost:3002).
Sessions are UUID tokens stored in Redis with a 7-day TTL.
Passwords are hashed with PBKDF2-HMAC-SHA256 (standard library, no extra deps).
"""

import hashlib
import json
import os
import re
import secrets
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from threading import Lock

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session

router = APIRouter(prefix="/dev-auth", tags=["developer-auth"])

_SESSION_TTL = int(timedelta(days=7).total_seconds())
_ITERATIONS = 390_000  # NIST SP 800-132 recommended minimum for PBKDF2-HMAC-SHA256

_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')

# ---------------------------------------------------------------------------
# Rate limiting (in-memory, per IP)
# ---------------------------------------------------------------------------

_login_attempts: dict[str, list[float]] = defaultdict(list)
_login_lock = Lock()


def _real_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_limit_key(request: Request) -> str:
    # In dev/test, allow a per-test unique ID so parallel tests don't share a bucket.
    if settings.dev_bypass_auth:
        test_id = request.headers.get("X-Test-Client-ID")
        if test_id:
            return f"test:{test_id}"
    return _real_ip(request)


def _check_auth_rate_limit(identifier: str, max_attempts: int = 10, window_seconds: int = 60) -> None:
    # Rate limiting is always active; it is independent of DEV_BYPASS_AUTH.
    now = time.time()
    with _login_lock:
        attempts = _login_attempts[identifier]
        _login_attempts[identifier] = [t for t in attempts if now - t < window_seconds]
        if len(_login_attempts[identifier]) >= max_attempts:
            raise HTTPException(status_code=429, detail="Too many attempts, try again later")
        _login_attempts[identifier].append(now)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _ITERATIONS)
    return f"pbkdf2:sha256:{_ITERATIONS}:{salt}:{dk.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        parts = stored_hash.split(":")
        if parts[0] != "pbkdf2" or parts[1] != "sha256":
            return False
        iterations, salt, expected_hex = int(parts[2]), parts[3], parts[4]
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations)
        return secrets.compare_digest(dk.hex(), expected_hex)
    except Exception:
        return False


def _session_key(token: str) -> str:
    return f"dev_session:{token}"


async def _get_current_developer(
    authorization: str | None = Header(default=None),
    request: Request = None,
) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.removeprefix("Bearer ").strip()
    redis = request.app.state.redis
    raw = await redis.get(_session_key(token))
    if not raw:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: str = Field(..., max_length=255)
    display_name: str = Field(..., max_length=200, min_length=1)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator('email')
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.lower().strip()
        if not _EMAIL_RE.match(v):
            raise ValueError('Invalid email address')
        return v


class LoginRequest(BaseModel):
    email: str
    password: str


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=200)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/register", status_code=201)
async def register(
    body: RegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    _check_auth_rate_limit(_rate_limit_key(request))

    # Email is already validated and normalised by the schema validator
    email = body.email

    # Corporate domain restriction
    if settings.allowed_email_domains:
        domain = email.split("@")[1]
        if domain not in settings.allowed_email_domains:
            raise HTTPException(status_code=422, detail="Registration is restricted to corporate email addresses")

    # Check uniqueness
    exists = (await session.execute(
        text("SELECT id FROM developers WHERE email = :email"),
        {"email": email},
    )).first()
    if exists:
        raise HTTPException(status_code=409, detail="Email already registered")

    dev_id = str(uuid.uuid4())
    pw_hash = _hash_password(body.password)
    await session.execute(
        text("""
            INSERT INTO developers (id, email, display_name, password_hash, status)
            VALUES (CAST(:id AS uuid), :email, :display_name, :password_hash, 'active')
        """),
        {"id": dev_id, "email": email, "display_name": body.display_name.strip(), "password_hash": pw_hash},
    )
    await session.commit()

    # Issue session
    token = secrets.token_urlsafe(32)
    payload = {"developer_id": dev_id, "email": email, "display_name": body.display_name.strip(), "team_id": None, "team_name": None}
    await request.app.state.redis.setex(_session_key(token), _SESSION_TTL, json.dumps(payload))

    return {"token": token, **payload}


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    _check_auth_rate_limit(_rate_limit_key(request))
    email = body.email.lower().strip()
    row = (await session.execute(
        text("""
            SELECT d.id, d.email, d.display_name, d.password_hash, d.status,
                   d.team_id, t.name AS team_name
            FROM developers d
            LEFT JOIN teams t ON t.id = d.team_id
            WHERE d.email = :email
        """),
        {"email": email},
    )).mappings().first()

    if not row or not _verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if row["status"] != "active":
        raise HTTPException(status_code=403, detail="Account is not active")

    token = secrets.token_urlsafe(32)
    payload = {
        "developer_id": str(row["id"]),
        "email": row["email"],
        "display_name": row["display_name"],
        "team_id": str(row["team_id"]) if row["team_id"] else None,
        "team_name": row["team_name"],
    }
    await request.app.state.redis.setex(_session_key(token), _SESSION_TTL, json.dumps(payload))

    return {"token": token, **payload}


@router.get("/me")
async def me(developer: dict = Depends(_get_current_developer)):
    return developer


@router.patch("/profile")
async def update_profile(
    body: ProfileUpdate,
    request: Request,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    developer = await _get_current_developer(authorization, request)
    updates: dict = {}
    params: dict = {"id": developer["developer_id"]}

    if body.display_name is not None:
        updates["display_name"] = body.display_name.strip()
        params["display_name"] = updates["display_name"]

    if not updates:
        return developer

    await session.execute(
        text("UPDATE developers SET display_name = :display_name WHERE id = CAST(:id AS uuid)"),
        params,
    )
    await session.commit()

    # Refresh session payload
    token = (authorization or "").removeprefix("Bearer ").strip()
    new_payload = {**developer, **updates}
    await request.app.state.redis.setex(_session_key(token), _SESSION_TTL, json.dumps(new_payload))
    return new_payload


@router.post("/select-team")
async def select_team(
    team_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    """Let a developer associate themselves with a team (dev convenience)."""
    developer = await _get_current_developer(authorization, request)
    row = (await session.execute(
        text("SELECT id, name FROM teams WHERE id = CAST(:id AS uuid)"),
        {"id": team_id},
    )).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Team not found")

    # Verify developer is a member of this team
    member_row = (await session.execute(
        text("SELECT id FROM team_members WHERE team_id = CAST(:team_id AS uuid) AND developer_id = :developer_id"),
        {"team_id": team_id, "developer_id": developer["developer_id"]},
    )).first()
    if not member_row:
        raise HTTPException(status_code=403, detail="You are not a member of this team")

    await session.execute(
        text("UPDATE developers SET team_id = CAST(:team_id AS uuid) WHERE id = CAST(:id AS uuid)"),
        {"team_id": team_id, "id": developer["developer_id"]},
    )
    await session.commit()

    token = (authorization or "").removeprefix("Bearer ").strip()
    new_payload = {**developer, "team_id": team_id, "team_name": row["name"]}
    await request.app.state.redis.setex(_session_key(token), _SESSION_TTL, json.dumps(new_payload))
    return new_payload


@router.post("/logout")
async def logout(
    request: Request,
    authorization: str | None = Header(default=None),
):
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        await request.app.state.redis.delete(_session_key(token))
    return {"ok": True}


@router.get("/me/stats")
async def my_stats(
    period: str = "7d",
    developer: dict = Depends(_get_current_developer),
    session: AsyncSession = Depends(get_session),
):
    """Developer-facing productivity stats with personal ROI — no admin token required."""
    valid_periods = {"7d", "30d", "90d", "mtd", "all"}
    if period not in valid_periods:
        period = "7d"

    developer_id = developer["developer_id"]
    team_id = developer.get("team_id")

    since_map = {
        "7d": "AND cr.created_at >= NOW() - INTERVAL '7 days'",
        "30d": "AND cr.created_at >= NOW() - INTERVAL '30 days'",
        "90d": "AND cr.created_at >= NOW() - INTERVAL '90 days'",
        "mtd": "AND cr.created_at >= date_trunc('month', NOW())",
        "all": "",
    }
    since = since_map[period]
    since_doe = since.replace("AND cr.created_at", "AND doe.occurred_at")
    since_s = since.replace("AND cr.created_at", "AND s.first_request_at")

    cost_row = (await session.execute(text(f"""
        SELECT
            COUNT(cr.id)                                                  AS request_count,
            COALESCE(SUM(cr.tokens_input + cr.tokens_output), 0)         AS total_tokens,
            COALESCE(ROUND(SUM(cr.cost_usd)::numeric, 6), 0)             AS cost_usd,
            COALESCE(SUM(cr.tool_invocation_count), 0)                   AS tool_invocations,
            ROUND(AVG(CASE WHEN cr.cache_hit THEN 1.0 ELSE 0.0 END)*100, 1) AS cache_hit_pct,
            ROUND(AVG(cr.latency_ms), 0)                                 AS avg_latency_ms,
            COUNT(CASE WHEN cr.request_error_type IS NOT NULL THEN 1 END) AS error_count,
            COUNT(DISTINCT cr.repo)                                       AS repo_count,
            COALESCE(SUM(cr.retry_count), 0)                             AS total_retries
        FROM cost_records cr
        WHERE cr.developer_id = CAST(:dev_id AS uuid) {since}
    """), {"dev_id": developer_id})).mappings().one()

    # GitHub output for ROI calculation
    output_totals = (await session.execute(text(f"""
        SELECT
            COALESCE(SUM(doe.commit_count), 0) AS total_commits,
            COUNT(CASE WHEN doe.event_type IN ('pr_opened', 'pr_merged') THEN 1 END) AS total_prs,
            COUNT(CASE WHEN doe.event_type = 'pr_merged' THEN 1 END) AS merged_prs
        FROM developer_output_events doe
        WHERE doe.developer_id = CAST(:dev_id AS uuid) {since_doe}
    """), {"dev_id": developer_id})).mappings().one()

    cost_usd = float(cost_row["cost_usd"])
    total_prs = int(output_totals["total_prs"])
    total_commits = int(output_totals["total_commits"])
    merged_prs = int(output_totals["merged_prs"])

    cost_per_pr = round(cost_usd / total_prs, 4) if total_prs > 0 else None
    cost_per_commit = round(cost_usd / total_commits, 4) if total_commits > 0 else None
    pr_merge_rate = round(merged_prs * 100.0 / total_prs, 1) if total_prs > 0 else None

    # Team budget context
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

    # Session quality stats
    session_row = (await session.execute(text(f"""
        SELECT COUNT(s.session_trace_id) AS session_count,
               ROUND(AVG(s.quality_score), 2) AS avg_quality,
               ROUND(AVG(s.turn_count), 1) AS avg_turns,
               ROUND(AVG(s.avg_inter_request_s), 0) AS avg_inter_s,
               COUNT(CASE WHEN s.produced_commit THEN 1 END) AS sessions_with_commit
        FROM sessions s
        WHERE s.developer_id = CAST(:dev_id AS uuid) {since_s}
    """), {"dev_id": developer_id})).mappings().one()

    session_count = int(session_row["session_count"])
    commit_conversion_pct = (
        round(int(session_row["sessions_with_commit"]) * 100.0 / session_count, 1)
        if session_count > 0 else None
    )

    # Efficiency percentile vs team (by cost-per-request; lower = more focused)
    efficiency_percentile = None
    if team_id and cost_row["request_count"] > 0:
        team_costs = (await session.execute(text(f"""
            SELECT cr.developer_id,
                   SUM(cr.cost_usd) / GREATEST(COUNT(cr.id), 1) AS cost_per_req
            FROM cost_records cr
            WHERE cr.team_id = (
                SELECT team_id FROM developers WHERE id = CAST(:dev_id AS uuid)
            ) AND cr.developer_id IS NOT NULL {since}
            GROUP BY cr.developer_id
            HAVING COUNT(cr.id) >= 5
        """), {"dev_id": developer_id})).mappings().all()

        if len(team_costs) > 1:
            my_cpr = cost_usd / max(1, cost_row["request_count"])
            all_cprs = sorted(float(r["cost_per_req"]) for r in team_costs)
            rank = sum(1 for c in all_cprs if c <= my_cpr)
            efficiency_percentile = round(rank * 100 / len(all_cprs), 0)

    # Optimization hints (based on DX/GitHub research)
    hints = []
    request_count = int(cost_row["request_count"])
    retry_count = int(cost_row["total_retries"])
    retry_rate = retry_count / max(1, request_count)

    if retry_rate > 0.3:
        hints.append({
            "type": "high_retry_rate",
            "message": f"Your retry rate is {retry_rate:.0%}. Try scoping prompts to a single task — focused sessions have 3× better acceptance rates.",
            "severity": "warning",
        })
    if cost_row["cache_hit_pct"] is not None and float(cost_row["cache_hit_pct"]) < 20 and request_count > 20:
        hints.append({
            "type": "low_cache_hit",
            "message": "Less than 20% of your requests hit the semantic cache. Using consistent phrasings for repeated tasks can reduce cost significantly.",
            "severity": "info",
        })
    if cost_per_pr is not None and cost_per_pr > 50:
        hints.append({
            "type": "high_cost_per_pr",
            "message": f"Your cost per PR is ${cost_per_pr:.2f}. Top quartile developers achieve <$10/PR. Consider using Sonnet for exploration and Opus only for final implementation.",
            "severity": "warning",
        })
    if session_row["avg_quality"] is not None and float(session_row["avg_quality"]) <= 2:
        hints.append({
            "type": "low_session_quality",
            "message": "Your recent sessions show struggle patterns (high retries, short sessions without commits). Try breaking large tasks into smaller, well-scoped sessions.",
            "severity": "warning",
        })

    daily_rows = (await session.execute(text("""
        SELECT date, request_count, cost_usd, cache_hits, tool_invocations, error_count
        FROM developer_activity_log
        WHERE developer_id = CAST(:dev_id AS uuid)
        ORDER BY date DESC
        LIMIT 30
    """), {"dev_id": developer_id})).mappings().all()

    output_rows = (await session.execute(text(f"""
        SELECT event_type, repo, COUNT(*) AS event_count,
               SUM(commit_count) AS commits, SUM(lines_added) AS lines_added,
               SUM(lines_removed) AS lines_removed
        FROM developer_output_events doe
        WHERE developer_id = CAST(:dev_id AS uuid) {since_doe}
        GROUP BY event_type, repo
        ORDER BY event_count DESC
        LIMIT 20
    """), {"dev_id": developer_id})).mappings().all()

    model_rows = (await session.execute(text(f"""
        SELECT cr.model,
               COUNT(cr.id) AS request_count,
               COALESCE(ROUND(SUM(cr.cost_usd)::numeric, 6), 0) AS cost_usd
        FROM cost_records cr
        WHERE cr.developer_id = CAST(:dev_id AS uuid) {since}
        GROUP BY cr.model
        ORDER BY cost_usd DESC
        LIMIT 10
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
            "total_commits": total_commits,
            "total_prs": total_prs,
            "merged_prs": merged_prs,
            "cost_per_pr": cost_per_pr,
            "cost_per_commit": cost_per_commit,
            "pr_merge_rate_pct": pr_merge_rate,
        },
        "session_quality": {
            "session_count": session_count,
            "avg_quality_score": float(session_row["avg_quality"]) if session_row["avg_quality"] is not None else None,
            "avg_turns": float(session_row["avg_turns"]) if session_row["avg_turns"] is not None else None,
            "avg_inter_request_s": float(session_row["avg_inter_s"]) if session_row["avg_inter_s"] is not None else None,
            "commit_conversion_pct": commit_conversion_pct,
        },
        "efficiency_percentile": efficiency_percentile,
        "team_budget": team_budget_info,
        "optimization_hints": hints,
        "daily": [
            {
                "date": str(r["date"]),
                "request_count": r["request_count"],
                "cost_usd": float(r["cost_usd"]),
                "cache_hits": r["cache_hits"],
                "tool_invocations": r["tool_invocations"],
                "error_count": r["error_count"],
            }
            for r in daily_rows
        ],
        "by_model": [
            {"model": r["model"], "request_count": r["request_count"], "cost_usd": float(r["cost_usd"])}
            for r in model_rows
        ],
        "github_output": [
            {
                "event_type": r["event_type"],
                "repo": r["repo"],
                "event_count": r["event_count"],
                "commits": int(r["commits"] or 0),
                "lines_added": int(r["lines_added"] or 0),
                "lines_removed": int(r["lines_removed"] or 0),
            }
            for r in output_rows
        ],
    }
