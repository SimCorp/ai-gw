import json
import secrets

from fastapi import Header, HTTPException, Request

from app.config import settings


async def require_dev_auth(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict:
    """Validate developer session from shared Redis."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization required")

    token = authorization.removeprefix("Bearer ").strip()
    redis = request.app.state.redis
    raw = await redis.get(f"session:{token}")
    if not raw:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    data = json.loads(raw)
    return {"user_id": data["user_id"], "email": data.get("email", "")}


async def require_admin_auth(
    request: Request,
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
) -> dict:
    """Validate admin token: static X-Admin-Token or session with admin role."""
    if x_admin_token and settings.admin_token:
        if secrets.compare_digest(x_admin_token, settings.admin_token):
            return {"user_id": "token", "role": "platform_admin"}

    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        redis = request.app.state.redis
        raw = await redis.get(f"session:{token}")
        if raw:
            data = json.loads(raw)
            roles = [r["role"] for r in data.get("roles", [])]
            if any(r in roles for r in ("platform_admin", "area_owner", "team_admin")):
                return {"user_id": data["user_id"], "role": "platform_admin"}

    raise HTTPException(status_code=403, detail="Admin access required")
