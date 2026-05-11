import secrets

from fastapi import Depends, Header, HTTPException, Request

from app.config import settings

# Role hierarchy: superadmin > admin > viewer
_ROLE_RANK = {"viewer": 0, "admin": 1, "superadmin": 2}


async def require_admin_auth(
    request: Request,
    x_admin_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    """Accept either X-Admin-Token (static) or Authorization: Bearer <session> (admin session).

    Returns a dict with at least {"actor": str, "role": str} for use in audit logging
    and downstream role checks.
    """
    if settings.dev_bypass_auth:
        result = {"actor": "dev-bypass", "role": "superadmin"}
        request.state.admin_auth = result
        return result

    # ── Path 1: static admin token (CI, automation) ──────────────────────────
    if x_admin_token and settings.admin_token:
        if secrets.compare_digest(x_admin_token, settings.admin_token):
            import hashlib
            digest = hashlib.sha256(x_admin_token.encode()).hexdigest()[:12]
            result = {"actor": f"token:{digest}", "role": "superadmin"}
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
                role = data.get("role", "viewer")
                result = {"actor": data.get("email", "unknown"), "role": role, "session": data}
                request.state.admin_auth = result
                return result

    if not settings.admin_token and not authorization:
        raise HTTPException(status_code=500, detail="ADMIN_TOKEN not configured")

    raise HTTPException(status_code=401, detail="Invalid or missing admin credentials")


def _check_role(auth: dict, minimum_role: str) -> None:
    role = auth.get("role", "viewer")
    if _ROLE_RANK.get(role, 0) < _ROLE_RANK.get(minimum_role, 0):
        raise HTTPException(
            status_code=403,
            detail=f"Requires role '{minimum_role}' or higher (you have '{role}')",
        )


async def require_admin_role(auth: dict = Depends(require_admin_auth)) -> dict:
    """Gate to admin or superadmin. Viewers are denied."""
    _check_role(auth, "admin")
    return auth


async def require_superadmin_role(auth: dict = Depends(require_admin_auth)) -> dict:
    """Gate to superadmin only."""
    _check_role(auth, "superadmin")
    return auth
