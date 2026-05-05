import secrets

from fastapi import Header, HTTPException

from app.config import settings


async def require_admin_auth(x_admin_token: str | None = Header(default=None)) -> None:
    if settings.dev_bypass_auth:
        return
    if not settings.admin_token:
        raise HTTPException(status_code=500, detail="ADMIN_TOKEN not configured")
    if x_admin_token is None or not secrets.compare_digest(x_admin_token, settings.admin_token):
        raise HTTPException(status_code=401, detail="Invalid admin token")
