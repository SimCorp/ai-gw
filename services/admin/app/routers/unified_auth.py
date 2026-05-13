"""
Unified authentication and authorisation.

Single /auth/* surface for all user types. Roles determine portal access.

Session Redis key: session:{token}
Payload: {user_id, email, display_name, roles, primary_team_id, team_name}

Roles:
  platform_admin  — full admin portal access
  area_owner      — manages an area + its teams (scoped)
  team_admin      — manages a single team (scoped)
  developer       — developer portal access
  viewer          — read-only portal access
  service_account — API key only, no portal
"""
from __future__ import annotations

import hashlib
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

router = APIRouter(prefix="/auth", tags=["auth"])

_SESSION_TTL = int(timedelta(hours=8).total_seconds())
_SESSION_TTL_REMEMBER = int(timedelta(days=30).total_seconds())
_SESSION_TTL_DEV = int(timedelta(days=7).total_seconds())
_PBKDF2_ITERS = 390_000

_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')


# ---------------------------------------------------------------------------
# Password helpers — support both bcrypt (admin) and pbkdf2 (legacy dev)
# ---------------------------------------------------------------------------

def _hash_bcrypt(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def _verify_password(password: str, stored_hash: str, hash_type: str) -> bool:
    try:
        if hash_type == "bcrypt":
            return bcrypt.checkpw(password.encode(), stored_hash.encode())
        else:  # pbkdf2
            parts = stored_hash.split(":")
            if len(parts) < 5 or parts[0] != "pbkdf2":
                return False
            iterations, salt, expected = int(parts[2]), parts[3], parts[4]
            dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations)
            return secrets.compare_digest(dk.hex(), expected)
    except Exception:
        return False


def _validate_password_strength(password: str) -> None:
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
    return f"session:{token}"


async def _get_session_data(token: str, redis) -> dict | None:
    raw = await redis.get(_session_key(token))
    if not raw:
        return None
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

async def get_current_user(
    authorization: str | None = Header(default=None),
    request: Request = None,
) -> dict:
    """Validate session token. Returns unified session payload."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    token = authorization.removeprefix("Bearer ").strip()
    redis = request.app.state.redis
    data = await _get_session_data(token, redis)
    if not data:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    return data


def require_platform_admin(user: dict = Depends(get_current_user)) -> dict:
    roles = [r["role"] for r in user.get("roles", [])]
    if "platform_admin" not in roles:
        raise HTTPException(status_code=403, detail="Platform admin access required")
    return user


def require_developer(user: dict = Depends(get_current_user)) -> dict:
    roles = [r["role"] for r in user.get("roles", [])]
    if not any(r in roles for r in ("developer", "platform_admin", "team_admin", "area_owner")):
        raise HTTPException(status_code=403, detail="Developer access required")
    return user


def has_role(user: dict, role: str, scope_id: str | None = None) -> bool:
    for r in user.get("roles", []):
        if r["role"] == role:
            if scope_id is None or r.get("scope_id") == scope_id:
                return True
    return False


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

async def _check_rate_limit(redis, identifier: str, max_attempts: int = 10, window: int = 60):
    key = f"login_rl:{identifier}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window)
    if count > max_attempts:
        raise HTTPException(status_code=429, detail="Too many attempts, try again later")


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


class RegisterRequest(BaseModel):
    email: str = Field(..., max_length=255)
    display_name: str = Field(..., max_length=200, min_length=1)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.lower().strip()
        if not _EMAIL_RE.match(v):
            raise ValueError("Invalid email address")
        return v


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_strength(cls, v: str) -> str:
        _validate_password_strength(v)
        return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _load_user_roles(session: AsyncSession, user_id: str) -> list[dict]:
    rows = (await session.execute(
        text("""
            SELECT role, scope_type, scope_id::text
            FROM user_roles
            WHERE user_id = CAST(:uid AS uuid)
        """),
        {"uid": user_id},
    )).mappings().all()
    return [dict(r) for r in rows]


async def _build_session_payload(row, roles: list[dict]) -> dict:
    return {
        "user_id": str(row["id"]),
        "email": row["email"],
        "display_name": row["display_name"] or "",
        "roles": roles,
        "primary_team_id": str(row["primary_team_id"]) if row.get("primary_team_id") else None,
    }


async def _issue_session(redis, payload: dict, ttl: int) -> str:
    token = secrets.token_urlsafe(32)
    await redis.setex(_session_key(token), ttl, json.dumps(payload))
    return token


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    await _check_rate_limit(request.app.state.redis, request.client.host if request.client else "unknown")

    row = (await session.execute(
        text("""
            SELECT u.id, u.email, u.display_name, u.password_hash, u.hash_type,
                   u.status, u.must_change_password, u.primary_team_id,
                   t.name AS team_name
            FROM users u
            LEFT JOIN teams t ON t.id = u.primary_team_id
            WHERE u.email = :email
        """),
        {"email": body.email},
    )).mappings().first()

    # Constant-time dummy verify on miss
    _dummy = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TiGkn3mK3KH0K2aIvFVe7sGOHMCC"
    stored_hash = row["password_hash"] if row else _dummy
    hash_type = row["hash_type"] if row else "bcrypt"

    if not _verify_password(body.password, stored_hash, hash_type) or not row:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if row["status"] != "active":
        raise HTTPException(status_code=403, detail="Account is not active")

    # Transparently re-hash pbkdf2 → bcrypt on first login
    if hash_type == "pbkdf2":
        new_hash = _hash_bcrypt(body.password)
        await session.execute(
            text("UPDATE users SET password_hash = :h, hash_type = 'bcrypt', updated_at = NOW() WHERE id = CAST(:id AS uuid)"),
            {"h": new_hash, "id": str(row["id"])},
        )

    await session.execute(
        text("UPDATE users SET last_login_at = NOW() WHERE id = CAST(:id AS uuid)"),
        {"id": str(row["id"])},
    )
    await session.commit()

    roles = await _load_user_roles(session, str(row["id"]))
    payload = await _build_session_payload(row, roles)
    payload["team_name"] = row["team_name"]

    # TTL: admins get 8h/30d, developers get 7d/30d
    is_admin = any(r["role"] == "platform_admin" for r in roles)
    if body.remember_me:
        ttl = _SESSION_TTL_REMEMBER
    elif is_admin:
        ttl = _SESSION_TTL
    else:
        ttl = _SESSION_TTL_DEV

    token = await _issue_session(request.app.state.redis, payload, ttl)

    return {
        "token": token,
        "user": payload,
        "must_change_password": bool(row["must_change_password"]),
    }


@router.post("/register", status_code=201)
async def register(
    body: RegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Self-service developer registration."""
    await _check_rate_limit(request.app.state.redis, request.client.host if request.client else "unknown")

    exists = (await session.execute(
        text("SELECT id FROM users WHERE email = :email"),
        {"email": body.email},
    )).first()
    if exists:
        raise HTTPException(status_code=409, detail="Email already registered")

    import uuid
    user_id = str(uuid.uuid4())
    pw_hash = _hash_bcrypt(body.password)
    await session.execute(
        text("""
            INSERT INTO users (id, email, display_name, password_hash, hash_type, status)
            VALUES (CAST(:id AS uuid), :email, :display_name, :hash, 'bcrypt', 'active')
        """),
        {"id": user_id, "email": body.email, "display_name": body.display_name.strip(), "hash": pw_hash},
    )
    await session.execute(
        text("INSERT INTO user_roles (user_id, role, scope_type) VALUES (CAST(:uid AS uuid), 'developer', 'global')"),
        {"uid": user_id},
    )
    await session.commit()

    roles = [{"role": "developer", "scope_type": "global", "scope_id": None}]
    payload = {
        "user_id": user_id,
        "email": body.email,
        "display_name": body.display_name.strip(),
        "roles": roles,
        "primary_team_id": None,
        "team_name": None,
    }
    token = await _issue_session(request.app.state.redis, payload, _SESSION_TTL_DEV)
    return {"token": token, "user": payload, "must_change_password": False}


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return user


@router.post("/logout")
async def logout(
    request: Request,
    authorization: str | None = Header(default=None),
):
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
    user = await get_current_user(authorization, request)

    row = (await session.execute(
        text("SELECT id, password_hash, hash_type FROM users WHERE id = CAST(:id AS uuid)"),
        {"id": user["user_id"]},
    )).mappings().first()

    if not row or not _verify_password(body.current_password, row["password_hash"], row["hash_type"]):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    new_hash = _hash_bcrypt(body.new_password)
    await session.execute(
        text("""
            UPDATE users
            SET password_hash = :hash, hash_type = 'bcrypt',
                must_change_password = FALSE, updated_at = NOW()
            WHERE id = CAST(:id AS uuid)
        """),
        {"hash": new_hash, "id": user["user_id"]},
    )
    await session.commit()

    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        await request.app.state.redis.delete(_session_key(token))

    return {"ok": True}


# ---------------------------------------------------------------------------
# User management (admin-only)
# ---------------------------------------------------------------------------

@router.get("/users")
async def list_users(
    admin: dict = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_session),
):
    rows = (await session.execute(text("""
        SELECT u.id, u.email, u.display_name, u.status, u.must_change_password,
               u.last_login_at, u.created_at,
               COALESCE(
                   json_agg(json_build_object('role', r.role, 'scope_type', r.scope_type, 'scope_id', r.scope_id::text))
                   FILTER (WHERE r.role IS NOT NULL), '[]'
               ) AS roles
        FROM users u
        LEFT JOIN user_roles r ON r.user_id = u.id
        GROUP BY u.id
        ORDER BY u.created_at DESC
    """))).mappings().all()
    import json as _json
    return [
        {**dict(r), "id": str(r["id"]), "roles": _json.loads(r["roles"]) if isinstance(r["roles"], str) else r["roles"]}
        for r in rows
    ]


class GrantRoleRequest(BaseModel):
    role: str
    scope_type: str = "global"
    scope_id: str | None = None


@router.post("/users/{user_id}/roles")
async def grant_role(
    user_id: str,
    body: GrantRoleRequest,
    admin: dict = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_session),
):
    await session.execute(
        text("""
            INSERT INTO user_roles (user_id, role, scope_type, scope_id, granted_by)
            VALUES (CAST(:uid AS uuid), :role, :scope_type,
                    CAST(:scope_id AS uuid), CAST(:by AS uuid))
            ON CONFLICT DO NOTHING
        """),
        {
            "uid": user_id, "role": body.role, "scope_type": body.scope_type,
            "scope_id": body.scope_id, "by": admin["user_id"],
        },
    )
    await session.commit()
    return {"ok": True}


@router.delete("/users/{user_id}/roles/{role}")
async def revoke_role(
    user_id: str,
    role: str,
    admin: dict = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_session),
):
    await session.execute(
        text("DELETE FROM user_roles WHERE user_id = CAST(:uid AS uuid) AND role = :role"),
        {"uid": user_id, "role": role},
    )
    await session.commit()
    return {"ok": True}
