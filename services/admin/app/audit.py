from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


def _actor(request: Request) -> str:
    """Resolve audit actor from request state."""
    # New unified auth: get_current_user sets this
    user = getattr(request.state, "current_user", None)
    if user:
        return user.get("email", "unknown")

    # Legacy: admin_auth set by require_admin_auth
    auth_info = getattr(request.state, "admin_auth", None)
    if auth_info:
        return auth_info.get("actor", "unknown")

    # Fallback: check X-Admin-Token header directly (for callers that bypassed the dep)
    import hashlib

    token = request.headers.get("x-admin-token")
    if token:
        digest = hashlib.sha256(token.encode()).hexdigest()[:12]
        return f"token:{digest}"

    return "dev-bypass"


async def record(
    session: AsyncSession,
    request: Request,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: Any = None,
) -> None:
    entry = AuditLog(
        actor=_actor(request),
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id else None,
        details=details,
    )
    session.add(entry)
    # Caller commits; this is added within the same transaction.
