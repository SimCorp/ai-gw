from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


def _actor(request: Request) -> str:
    token = request.headers.get("x-admin-token")
    if token:
        return f"token:{token[:8]}..."
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
