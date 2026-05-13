"""
Admin portal authentication — shim over unified_auth.

Delegates to the users table. Kept for backwards-compatibility with
the admin portal frontend which calls /admin-auth/login etc.
Session key: session:{token}  (unified format)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.routers.unified_auth import (
    LoginRequest,
    ChangePasswordRequest,
    get_current_user,
    login as _unified_login,
    logout as _unified_logout,
    change_password as _unified_change_password,
    require_platform_admin,
    _session_key,
)

router = APIRouter(prefix="/admin-auth", tags=["admin-auth"])


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Admin portal login — delegates to unified auth, enforces admin role."""
    result = await _unified_login(body, request, session)

    # Verify the user has admin-level access
    roles = [r["role"] for r in result["user"].get("roles", [])]
    if not any(r in roles for r in ("platform_admin", "area_owner", "team_admin")):
        # Revoke the session immediately
        token = result["token"]
        await request.app.state.redis.delete(_session_key(token))
        raise HTTPException(status_code=403, detail="Admin portal access requires an admin role")

    # Flatten roles to legacy single role for admin portal frontend
    if "platform_admin" in roles:
        result["user"]["role"] = "superadmin"
    elif any(r in roles for r in ("area_owner", "team_admin")):
        result["user"]["role"] = "admin"
    else:
        result["user"]["role"] = "viewer"

    return result


@router.get("/me")
async def me(admin: dict = Depends(require_platform_admin)):
    return admin


@router.post("/logout")
async def logout(
    request: Request,
    authorization: str | None = Header(default=None),
):
    return await _unified_logout(request, authorization)


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    return await _unified_change_password(body, request, authorization, session)


async def get_admin_session(
    authorization: str | None = Header(default=None),
    request: Request = None,
) -> dict:
    """Backwards-compat dependency used by other routers."""
    user = await get_current_user(authorization, request)
    roles = [r["role"] for r in user.get("roles", [])]
    if not any(r in roles for r in ("platform_admin", "area_owner", "team_admin")):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
