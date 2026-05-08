import secrets

from fastapi import Header, HTTPException, Request

from app.config import settings


async def require_admin_auth(
    request: Request,
    x_admin_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    """Accept either X-Admin-Token (static) or Authorization: Bearer <session> (admin session).

    Returns a dict with at least {"actor": str} for use in audit logging.
    """
    if settings.dev_bypass_auth:
        request.state.admin_auth = {"actor": "dev-bypass"}
        return {"actor": "dev-bypass"}

    # ── Path 1: static admin token (CI, automation) ──────────────────────────
    if x_admin_token and settings.admin_token:
        if secrets.compare_digest(x_admin_token, settings.admin_token):
            import hashlib
            digest = hashlib.sha256(x_admin_token.encode()).hexdigest()[:12]
            result = {"actor": f"token:{digest}"}
            request.state.admin_auth = result
            return result

    # ── Path 2: bearer session token (admin portal login) ────────────────────
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        redis = getattr(request.app.state, "redis", None)
        if redis:
            raw = await redis.get(f"admin_session:{token}")
            if raw:
                import json
                data = json.loads(raw)
                result = {"actor": data.get("email", "unknown"), "session": data}
                request.state.admin_auth = result
                return result

    if not settings.admin_token and not authorization:
        raise HTTPException(status_code=500, detail="ADMIN_TOKEN not configured")

    raise HTTPException(status_code=401, detail="Invalid or missing admin credentials")
