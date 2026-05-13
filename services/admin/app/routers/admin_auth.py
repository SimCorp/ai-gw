"""
Admin portal authentication.

Provides login / me / logout / change-password for admin portal users.
Admin users are SEPARATE from developer portal users (developers table).

Sessions are random tokens stored in Redis:
  admin_session:{token} -> JSON {user_id, email, display_name, role}
  TTL: 8 hours (or 30 days with remember_me=True)

Passwords are hashed with bcrypt (12 rounds).
"""

import json
import re
import secrets
from datetime import timedelta

import bcrypt
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session

router = APIRouter(prefix="/admin-auth", tags=["admin-auth"])

_SESSION_TTL = int(timedelta(hours=8).total_seconds())
_SESSION_TTL_REMEMBER = int(timedelta(days=30).total_seconds())

_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')

# ---------------------------------------------------------------------------
# Rate limiting — Redis-backed so all replicas share the counter
# ---------------------------------------------------------------------------

async def _check_rate_limit(redis, identifier: str, max_attempts: int = 10, window_seconds: int = 60) -> None:
    key = f"login_rl:{identifier}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window_seconds)
    if count > max_attempts:
        raise HTTPException(status_code=429, detail="Too many attempts, try again later")


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------

def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), stored_hash.encode())
    except Exception:
        return False


def _validate_password_strength(password: str) -> None:
    """Raise ValueError if password does not meet strength requirements."""
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must contain at least one lowercase letter")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one digit")
    if not re.search(r"[^A-Za-z0-9]", password):
        raise ValueError("Password must contain at least one special character")


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def _session_key(token: str) -> str:
    return f"admin_session:{token}"


async def _get_session_data(token: str, redis) -> dict | None:
    raw = await redis.get(_session_key(token))
    if not raw:
        return None
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Auth dependency (reusable by other routers)
# ---------------------------------------------------------------------------

async def get_admin_session(
    authorization: str | None = Header(default=None),
    request: Request = None,
) -> dict:
    """Validate admin session token from Authorization: Bearer header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    token = authorization.removeprefix("Bearer ").strip()
    redis = request.app.state.redis
    data = await _get_session_data(token, redis)
    if not data:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    return data


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: str
    password: str
    remember_me: bool = False

    @field_validator("email")
    @classmethod
    def normalise_email(cls, v: str) -> str:
        return v.lower().strip()


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_strength(cls, v: str) -> str:
        _validate_password_strength(v)
        return v


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Authenticate an admin user and return a session token."""
    await _check_rate_limit(request.app.state.redis, request.client.host if request.client else "unknown")

    row = (await session.execute(
        text("""
            SELECT id, email, display_name, password_hash, role, must_change_password
            FROM admin_users
            WHERE email = :email
        """),
        {"email": body.email},
    )).mappings().first()

    # Constant-time: always verify even on miss (dummy hash) to prevent timing attacks
    _dummy_hash = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TiGkn3mK3KH0K2aIvFVe7sGOHMCC"
    stored_hash = row["password_hash"] if row else _dummy_hash

    if not _verify_password(body.password, stored_hash) or not row:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Update last_login_at
    await session.execute(
        text("UPDATE admin_users SET last_login_at = NOW() WHERE id = :id"),
        {"id": str(row["id"])},
    )
    await session.commit()

    token = secrets.token_urlsafe(32)
    ttl = _SESSION_TTL_REMEMBER if body.remember_me else _SESSION_TTL
    payload = {
        "user_id": str(row["id"]),
        "email": row["email"],
        "display_name": row["display_name"],
        "role": row["role"],
    }
    redis = request.app.state.redis
    await redis.setex(_session_key(token), ttl, json.dumps(payload))

    return {"token": token, "user": payload, "must_change_password": bool(row["must_change_password"])}


@router.get("/me")
async def me(admin: dict = Depends(get_admin_session)):
    """Return the current admin session info."""
    return admin


@router.post("/logout")
async def logout(
    request: Request,
    authorization: str | None = Header(default=None),
):
    """Invalidate the current session token."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        await request.app.state.redis.delete(_session_key(token))
    return {"ok": True}


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    """Change the admin user's password. Requires current password verification."""
    admin = await get_admin_session(authorization, request)

    row = (await session.execute(
        text("SELECT id, password_hash FROM admin_users WHERE id = CAST(:id AS uuid)"),
        {"id": admin["user_id"]},
    )).mappings().first()

    if not row or not _verify_password(body.current_password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    new_hash = _hash_password(body.new_password)
    await session.execute(
        text("""
            UPDATE admin_users
            SET password_hash = :hash, must_change_password = FALSE, updated_at = NOW()
            WHERE id = CAST(:id AS uuid)
        """),
        {"hash": new_hash, "id": admin["user_id"]},
    )
    await session.commit()

    # Invalidate current session so user must re-login
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        await request.app.state.redis.delete(_session_key(token))

    return {"ok": True, "message": "Password changed. Please log in again."}
