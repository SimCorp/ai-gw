import secrets
import json

from fastapi import Depends, Header, HTTPException, Request

from app.config import settings

# Role hierarchy for backwards-compat helpers
_ROLE_RANK = {"viewer": 0, "admin": 1, "superadmin": 2}

# New role → old rank mapping for _check_role compatibility
_NEW_TO_OLD_RANK = {
    "viewer": 0,
    "developer": 0,
    "service_account": 0,
    "team_admin": 1,
    "area_owner": 1,
    "platform_admin": 2,
}


async def require_admin_auth(
    request: Request,
    x_admin_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict:
    """Accept X-Admin-Token (static) or Authorization: Bearer <session>.

    Checks new unified session:{token} key first, then legacy admin_session:{token}.
    Returns a dict with at least {"actor": str, "role": str} for audit logging.
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

    # ── Path 2: bearer session token ────────────────────────────────────────
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        redis = getattr(request.app.state, "redis", None)
        if redis:
            # Try new unified session first
            raw = await redis.get(f"session:{token}")
            if raw:
                data = json.loads(raw)
                roles = [r["role"] for r in data.get("roles", [])]
                is_admin = any(r in roles for r in ("platform_admin", "area_owner", "team_admin"))
                if not is_admin:
                    raise HTTPException(status_code=403, detail="Admin access required")
                # Compute legacy role string for backwards compat
                if "platform_admin" in roles:
                    legacy_role = "superadmin"
                elif any(r in roles for r in ("area_owner", "team_admin")):
                    legacy_role = "admin"
                else:
                    legacy_role = "viewer"
                result = {
                    "actor": data.get("email", "unknown"),
                    "role": legacy_role,
                    "session": data,
                    "user_id": data.get("user_id"),
                }
                request.state.admin_auth = result
                return result

            # Fallback: legacy admin_session:{token}
            raw = await redis.get(f"admin_session:{token}")
            if raw:
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
    _check_role(auth, "admin")
    return auth


async def require_superadmin_role(auth: dict = Depends(require_admin_auth)) -> dict:
    _check_role(auth, "superadmin")
    return auth
