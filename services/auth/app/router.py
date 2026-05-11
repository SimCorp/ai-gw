import json
import logging
import os
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from redis.asyncio import Redis

from app.config import settings
from app.rate_limiter import check_rate_limit
from app.validators.api_key import validate_api_key
from app.validators.jwt import validate_jwt

_log = logging.getLogger(__name__)

router = APIRouter()


class ValidateRequest(BaseModel):
    token: str
    model: str = ""


class ValidateResponse(BaseModel):
    team_id: str
    project_id: str | None = None
    key_id: str | None = None
    scope: str | None = None


async def check_budget(team_id: str, key_id: str | None, redis: Redis) -> tuple[bool, str]:
    """Returns (allowed, reason). Checks key → team → org budgets.

    Fails open by default (BUDGET_REDIS_FAILOPEN=true) so agents are never blocked by
    Redis infra outages. Set BUDGET_REDIS_FAILOPEN=false for strict fail-closed behaviour.
    """
    try:
        month = datetime.utcnow().strftime("%Y-%m")

        # Check key-level budget (only when we have a key_id from an API key auth)
        if key_id is not None:
            key_limit_raw = await redis.get(f"budget_limit:key:{key_id}")
            if key_limit_raw:
                key_limit = json.loads(key_limit_raw)
                if key_limit.get("limit"):
                    key_spend_raw = await redis.get(f"budget:key:{key_id}:{month}")
                    key_spend = float(key_spend_raw or 0)
                    if key_spend >= float(key_limit["limit"]):
                        return False, f"API key monthly budget of ${float(key_limit['limit']):.4g} exhausted"

        # Check team-level budget
        team_limit_raw = await redis.get(f"budget_limit:team:{team_id}")
        if team_limit_raw:
            team_limit = json.loads(team_limit_raw)
            if team_limit.get("limit"):
                team_spend_raw = await redis.get(f"budget:team:{team_id}:{month}")
                team_spend = float(team_spend_raw or 0)
                if team_spend >= float(team_limit["limit"]):
                    action = team_limit.get("action", "alert")
                    if action == "block":
                        return False, f"Team monthly budget of ${float(team_limit['limit']):.4g} exhausted"
                    # action == "alert": allow through but log it

        # Check org-level budget
        org_limit_raw = await redis.get("budget_limit:org")
        if org_limit_raw:
            org_limit = json.loads(org_limit_raw)
            if org_limit.get("limit") and float(org_limit["limit"]) > 0:
                org_spend_raw = await redis.get(f"budget:org:{month}")
                org_spend = float(org_spend_raw or 0)
                if org_spend >= float(org_limit["limit"]):
                    action = org_limit.get("action", "alert")
                    if action == "block":
                        return False, "Organisation monthly budget exhausted"

        return True, ""
    except Exception as exc:
        if os.getenv("BUDGET_REDIS_FAILOPEN", "true").lower() != "false":
            _log.warning("Redis unavailable during budget check — failing open: %s", exc)
            return True, ""
        _log.error("Redis unavailable during budget check — failing closed: %s", exc)
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Budget enforcement temporarily unavailable")


@router.post("/validate", response_model=ValidateResponse)
async def validate(body: ValidateRequest, request: Request):
    redis = request.app.state.redis
    db = request.app.state.db

    token = body.token.removeprefix("Bearer ").strip()
    if not token:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Missing token")

    if token.startswith("sk-"):
        identity = await validate_api_key(token, db, redis)
    else:
        identity = await validate_jwt(token, settings, redis)

    rpm_limit = settings.rate_limit_default_rpm
    try:
        policy_key = f"policy:{identity['team_id']}"
        raw = await redis.hget(policy_key, "rate_limit_rpm")
        if raw is not None:
            rpm_limit = int(raw)
    except Exception:
        pass  # Redis failure → use global default

    await check_rate_limit(identity["team_id"], body.model, redis, rpm_limit)

    allowed, reason = await check_budget(identity["team_id"], identity.get("key_id"), redis)
    if not allowed:
        return JSONResponse({"error": "budget_exhausted", "message": reason}, status_code=429)

    return ValidateResponse(**identity)
