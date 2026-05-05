from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.config import settings
from app.rate_limiter import check_rate_limit
from app.validators.api_key import validate_api_key
from app.validators.jwt import validate_jwt

router = APIRouter()


class ValidateRequest(BaseModel):
    token: str
    model: str = ""


class ValidateResponse(BaseModel):
    team_id: str
    project_id: str | None = None


@router.post("/validate", response_model=ValidateResponse)
async def validate(body: ValidateRequest, request: Request):
    redis = request.app.state.redis
    db = request.app.state.db

    token = body.token.removeprefix("Bearer ").strip()

    if token.startswith("sk-"):
        identity = await validate_api_key(token, db)
    else:
        identity = await validate_jwt(token, settings)

    rpm_limit = settings.rate_limit_default_rpm
    try:
        policy_key = f"policy:{identity['team_id']}"
        raw = await redis.hget(policy_key, "rate_limit_rpm")
        if raw is not None:
            rpm_limit = int(raw)
    except Exception:
        pass  # Redis failure → use global default

    await check_rate_limit(identity["team_id"], body.model, redis, rpm_limit)
    return ValidateResponse(**identity)
