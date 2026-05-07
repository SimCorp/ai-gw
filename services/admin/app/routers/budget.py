"""Budget management endpoints.

Covers team budgets, per-key budgets, org-level budget, and a combined
status view for the admin dashboard.  Redis cache keys are written so that
the auth service can enforce limits without hitting Postgres on each request.

Redis key contract
------------------
budget_limit:team:{team_id}  -> JSON {"limit": 500.0, "action": "block", "alert_pct": 0.8}
budget_limit:key:{key_id}    -> JSON {"limit": 50.0}
budget_limit:org             -> JSON {"limit": 10000.0, "action": "alert", "alert_pct": 0.8}

monthly_budget_usd = None means unlimited.  In that case the Redis key is
deleted rather than stored, so the auth service treats absence as no-limit.
"""

import calendar
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.db import get_session
from app.models.api_key import APIKey
from app.models.team import Team


def _end_of_month() -> int:
    now = datetime.now(timezone.utc)
    last_day = calendar.monthrange(now.year, now.month)[1]
    return int(datetime(now.year, now.month, last_day, 23, 59, 59, tzinfo=timezone.utc).timestamp())


def _current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")

router = APIRouter(tags=["budget"])

_BUDGET_REDIS_TTL = 300  # seconds


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_pct(spend: float, limit: float | None) -> float | None:
    """Return spend / limit as a fraction, or None if limit is None/zero."""
    if limit is None or limit == 0.0:
        return None
    return spend / limit


def _remaining(spend: float, limit: float | None) -> float | None:
    """Return limit - spend, or None if limit is None (unlimited)."""
    if limit is None:
        return None
    return max(limit - spend, 0.0)


async def _team_monthly_spend(session: AsyncSession, team_id: UUID) -> float:
    row = await session.execute(
        text(
            "SELECT COALESCE(SUM(cost_usd), 0) AS spend "
            "FROM cost_records "
            "WHERE team_id = :team_id "
            "  AND created_at >= date_trunc('month', NOW())"
        ),
        {"team_id": str(team_id)},
    )
    return float(row.scalar_one())


async def _key_monthly_spend(session: AsyncSession, key_id: UUID) -> float:
    row = await session.execute(
        text(
            "SELECT COALESCE(SUM(cost_usd), 0) AS spend "
            "FROM cost_records "
            "WHERE api_key_id = :key_id "
            "  AND created_at >= date_trunc('month', NOW())"
        ),
        {"key_id": str(key_id)},
    )
    return float(row.scalar_one())


async def _org_monthly_spend(session: AsyncSession) -> float:
    row = await session.execute(
        text(
            "SELECT COALESCE(SUM(cost_usd), 0) AS spend "
            "FROM cost_records "
            "WHERE created_at >= date_trunc('month', NOW())"
        )
    )
    return float(row.scalar_one())


async def _redis_set_team_budget(request: Request, team_id: UUID, limit: float | None, action: str, alert_pct: float) -> None:
    redis = request.app.state.redis
    key = f"budget_limit:team:{team_id}"
    if limit is None:
        await redis.delete(key)
    else:
        payload = json.dumps({"limit": limit, "action": action, "alert_pct": alert_pct})
        await redis.set(key, payload, ex=_BUDGET_REDIS_TTL)


async def _redis_set_key_budget(request: Request, key_id: UUID, limit: float | None) -> None:
    redis = request.app.state.redis
    key = f"budget_limit:key:{key_id}"
    if limit is None:
        await redis.delete(key)
    else:
        payload = json.dumps({"limit": limit})
        await redis.set(key, payload, ex=_BUDGET_REDIS_TTL)


async def _redis_set_org_budget(request: Request, limit: float | None, action: str, alert_pct: float) -> None:
    redis = request.app.state.redis
    key = "budget_limit:org"
    if limit is None:
        await redis.delete(key)
    else:
        payload = json.dumps({"limit": limit, "action": action, "alert_pct": alert_pct})
        await redis.set(key, payload, ex=_BUDGET_REDIS_TTL)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class TeamBudgetBody(BaseModel):
    monthly_budget_usd: float | None = Field(default=None, ge=0)
    budget_alert_pct: float = Field(default=0.8, ge=0.0, le=1.0)
    budget_action: Literal["alert", "block"] = "alert"


class KeyBudgetBody(BaseModel):
    monthly_budget_usd: float | None = Field(default=None, ge=0)


class OrgBudgetBody(BaseModel):
    monthly_budget_usd: float | None = Field(default=None, ge=0)
    budget_alert_pct: float = Field(default=0.8, ge=0.0, le=1.0)
    budget_action: Literal["alert", "block"] = "alert"


# ---------------------------------------------------------------------------
# Team budget
# ---------------------------------------------------------------------------

@router.get("/teams/{team_id}/budget")
async def get_team_budget(
    team_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    team = await session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    limit = float(team.monthly_budget_usd) if team.monthly_budget_usd is not None else None
    spend = await _team_monthly_spend(session, team_id)

    return {
        "team_id": str(team_id),
        "monthly_budget_usd": limit,
        "budget_alert_pct": team.budget_alert_pct,
        "budget_action": team.budget_action,
        "current_spend_usd": spend,
        "budget_remaining_usd": _remaining(spend, limit),
        "pct_used": _safe_pct(spend, limit),
    }


@router.put("/teams/{team_id}/budget")
async def set_team_budget(
    team_id: UUID,
    body: TeamBudgetBody,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    team = await session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    team.monthly_budget_usd = Decimal(str(body.monthly_budget_usd)) if body.monthly_budget_usd is not None else None
    team.budget_alert_pct = body.budget_alert_pct
    team.budget_action = body.budget_action

    await audit.record(
        session, request, "set_team_budget", "team", resource_id=team_id,
        details={
            "monthly_budget_usd": body.monthly_budget_usd,
            "budget_alert_pct": body.budget_alert_pct,
            "budget_action": body.budget_action,
        },
    )
    await session.commit()
    await session.refresh(team)

    await _redis_set_team_budget(request, team_id, body.monthly_budget_usd, body.budget_action, body.budget_alert_pct)

    limit = float(team.monthly_budget_usd) if team.monthly_budget_usd is not None else None
    spend = await _team_monthly_spend(session, team_id)

    # Seed the running spend counter so enforcement is immediate
    redis = request.app.state.redis
    month = _current_month()
    await redis.set(f"budget:team:{team_id}:{month}", str(spend), exat=_end_of_month())

    return {
        "team_id": str(team_id),
        "monthly_budget_usd": limit,
        "budget_alert_pct": team.budget_alert_pct,
        "budget_action": team.budget_action,
        "current_spend_usd": spend,
        "budget_remaining_usd": _remaining(spend, limit),
        "pct_used": _safe_pct(spend, limit),
    }


# ---------------------------------------------------------------------------
# API key budget
# ---------------------------------------------------------------------------

@router.get("/keys/{key_id}/budget")
async def get_key_budget(
    key_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    key = await session.get(APIKey, key_id)
    if not key or key.revoked_at is not None:
        raise HTTPException(status_code=404, detail="API key not found")

    limit = float(key.monthly_budget_usd) if key.monthly_budget_usd is not None else None
    spend = await _key_monthly_spend(session, key_id)

    return {
        "key_id": str(key_id),
        "monthly_budget_usd": limit,
        "current_spend_usd": spend,
        "budget_remaining_usd": _remaining(spend, limit),
        "pct_used": _safe_pct(spend, limit),
    }


@router.put("/keys/{key_id}/budget")
async def set_key_budget(
    key_id: UUID,
    body: KeyBudgetBody,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    key = await session.get(APIKey, key_id)
    if not key or key.revoked_at is not None:
        raise HTTPException(status_code=404, detail="API key not found")

    key.monthly_budget_usd = Decimal(str(body.monthly_budget_usd)) if body.monthly_budget_usd is not None else None

    await audit.record(
        session, request, "set_key_budget", "api_key", resource_id=key_id,
        details={"monthly_budget_usd": body.monthly_budget_usd},
    )
    await session.commit()
    await session.refresh(key)

    await _redis_set_key_budget(request, key_id, body.monthly_budget_usd)

    limit = float(key.monthly_budget_usd) if key.monthly_budget_usd is not None else None
    spend = await _key_monthly_spend(session, key_id)

    # Seed spend counter so enforcement is immediate
    redis = request.app.state.redis
    month = _current_month()
    await redis.set(f"budget:key:{key_id}:{month}", str(spend), exat=_end_of_month())

    return {
        "key_id": str(key_id),
        "monthly_budget_usd": limit,
        "current_spend_usd": spend,
        "budget_remaining_usd": _remaining(spend, limit),
        "pct_used": _safe_pct(spend, limit),
    }


# ---------------------------------------------------------------------------
# Org budget
# ---------------------------------------------------------------------------

async def _read_org_settings(session: AsyncSession) -> dict[str, str]:
    rows = await session.execute(text("SELECT key, value FROM org_settings"))
    return {row.key: row.value for row in rows}


@router.get("/org/budget")
async def get_org_budget(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    settings = await _read_org_settings(session)
    raw_limit = float(settings.get("monthly_budget_usd", "0"))
    # 0.0 stored as the seed means "no real limit set" but we expose it as-is;
    # callers that want "unlimited" should PUT monthly_budget_usd=null.
    limit: float | None = raw_limit if raw_limit > 0.0 else None
    alert_pct = float(settings.get("budget_alert_pct", "0.8"))
    action = settings.get("budget_action", "alert")
    spend = await _org_monthly_spend(session)

    return {
        "monthly_budget_usd": limit,
        "budget_alert_pct": alert_pct,
        "budget_action": action,
        "current_spend_usd": spend,
        "budget_remaining_usd": _remaining(spend, limit),
        "pct_used": _safe_pct(spend, limit),
    }


@router.put("/org/budget")
async def set_org_budget(
    body: OrgBudgetBody,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    limit_str = str(body.monthly_budget_usd) if body.monthly_budget_usd is not None else "0"

    await session.execute(
        text(
            "INSERT INTO org_settings (key, value, updated_at) VALUES (:key, :value, NOW()) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()"
        ),
        {"key": "monthly_budget_usd", "value": limit_str},
    )
    await session.execute(
        text(
            "INSERT INTO org_settings (key, value, updated_at) VALUES (:key, :value, NOW()) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()"
        ),
        {"key": "budget_alert_pct", "value": str(body.budget_alert_pct)},
    )
    await session.execute(
        text(
            "INSERT INTO org_settings (key, value, updated_at) VALUES (:key, :value, NOW()) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()"
        ),
        {"key": "budget_action", "value": body.budget_action},
    )

    await audit.record(
        session, request, "set_org_budget", "org_settings", resource_id=None,
        details={
            "monthly_budget_usd": body.monthly_budget_usd,
            "budget_alert_pct": body.budget_alert_pct,
            "budget_action": body.budget_action,
        },
    )
    await session.commit()

    await _redis_set_org_budget(request, body.monthly_budget_usd, body.budget_action, body.budget_alert_pct)

    spend = await _org_monthly_spend(session)

    # Seed org spend counter
    redis = request.app.state.redis
    month = _current_month()
    await redis.set(f"budget:org:{month}", str(spend), exat=_end_of_month())

    return {
        "monthly_budget_usd": body.monthly_budget_usd,
        "budget_alert_pct": body.budget_alert_pct,
        "budget_action": body.budget_action,
        "current_spend_usd": spend,
        "budget_remaining_usd": _remaining(spend, body.monthly_budget_usd),
        "pct_used": _safe_pct(spend, body.monthly_budget_usd),
    }


# ---------------------------------------------------------------------------
# Budget status — combined dashboard view
# ---------------------------------------------------------------------------

@router.get("/budget/status")
async def budget_status(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    # Org summary
    org_settings = await _read_org_settings(session)
    raw_org_limit = float(org_settings.get("monthly_budget_usd", "0"))
    org_limit: float | None = raw_org_limit if raw_org_limit > 0.0 else None
    org_alert_pct = float(org_settings.get("budget_alert_pct", "0.8"))
    org_action = org_settings.get("budget_action", "alert")
    org_spend = await _org_monthly_spend(session)

    # All teams with their spend
    result = await session.execute(
        text(
            "SELECT t.id, t.name, t.slug, t.monthly_budget_usd, t.budget_alert_pct, t.budget_action, "
            "       COALESCE(SUM(cr.cost_usd), 0) AS spend "
            "FROM teams t "
            "LEFT JOIN cost_records cr "
            "       ON cr.team_id = t.id "
            "      AND cr.created_at >= date_trunc('month', NOW()) "
            "GROUP BY t.id, t.name, t.slug, t.monthly_budget_usd, t.budget_alert_pct, t.budget_action "
            "ORDER BY t.name"
        )
    )
    teams_rows = result.mappings().all()

    teams_summary = []
    for row in teams_rows:
        t_limit = float(row["monthly_budget_usd"]) if row["monthly_budget_usd"] is not None else None
        t_spend = float(row["spend"])
        teams_summary.append(
            {
                "team_id": str(row["id"]),
                "name": row["name"],
                "slug": row["slug"],
                "monthly_budget_usd": t_limit,
                "budget_alert_pct": float(row["budget_alert_pct"]),
                "budget_action": row["budget_action"],
                "current_spend_usd": t_spend,
                "budget_remaining_usd": _remaining(t_spend, t_limit),
                "pct_used": _safe_pct(t_spend, t_limit),
            }
        )

    return {
        "org": {
            "monthly_budget_usd": org_limit,
            "budget_alert_pct": org_alert_pct,
            "budget_action": org_action,
            "current_spend_usd": org_spend,
            "budget_remaining_usd": _remaining(org_spend, org_limit),
            "pct_used": _safe_pct(org_spend, org_limit),
        },
        "teams": teams_summary,
        "team_count": len(teams_summary),
        "teams_over_alert": sum(
            1
            for t in teams_summary
            if t["pct_used"] is not None and t["pct_used"] >= t["budget_alert_pct"]
        ),
    }
