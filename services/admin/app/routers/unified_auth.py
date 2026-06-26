"""
Unified authentication and authorisation.

Single /auth/* surface for all user types. Roles determine portal access.

Session Redis key: session:{token}
Payload: {user_id, email, display_name, roles, primary_node_id}

Roles are now path-scoped via role_assignments + organization_nodes.
Permission check (pure Python, zero DB):
  can_access(user, target_path, min_role) — startswith match + role power

NOTE: The following endpoints still reference the old user_roles table and
will return errors until a follow-up migration is applied:
  - grant_role / revoke_role / list_users (admin role management UI)
  - create_invitation / accept_invitation / bulk_invite
  - create_service_account / list_service_accounts
"""

from __future__ import annotations

import csv as _csv
import hashlib
import io as _io
import json
import logging
import re
import secrets
from datetime import timedelta
from uuid import UUID

import bcrypt
from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session_maker, get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# ---------------------------------------------------------------------------
# Path-based permission model
# ---------------------------------------------------------------------------

_ROLE_POWER = {
    "gateway_admin": 6,
    "platform_admin": 6,  # alias — old sessions in Redis
    "area_owner": 5,
    "unit_lead": 4,
    "team_admin": 3,
    "engineer": 2,
    "developer": 2,  # alias — old sessions in Redis
    "reporter": 1,
    "viewer": 1,  # alias — old sessions in Redis
}

# Sets used for role checks that must work with both old and new session names
_GATEWAY_ADMIN_ROLES = {"gateway_admin", "platform_admin"}
_ENGINEER_ROLES = {"developer", "engineer"}


def can_access(user: dict, target_path: str, min_role: str) -> bool:
    """Return True if user has at least min_role power on any node whose path
    is a prefix of target_path (i.e. the role is at or above the target node).

    "/" is the root sentinel used by callers to mean "global root access".
    Root nodes are stored with UUID-based paths ("/uuid"), not literal "/",
    so we treat "/" specially: it matches any role held at a root-level node
    (path of the form "/uuid" — exactly one slash).
    """
    required = _ROLE_POWER.get(min_role, 0)
    for r in user.get("roles", []):
        node_path = r.get("node_path", "")
        if not node_path:
            continue
        if target_path == "/":
            # Root sentinel: role must be at a root node (single-segment path).
            if node_path.count("/") == 1 and _ROLE_POWER.get(r.get("role", ""), 0) >= required:
                return True
        elif target_path.startswith(node_path):
            if _ROLE_POWER.get(r.get("role", ""), 0) >= required:
                return True
    return False


def max_role_power(user: dict, target_path: str) -> int:
    """Highest role power the user holds on any node that is a prefix of
    target_path (using the same "/" root-sentinel rule as can_access).

    Used to prevent privilege amplification: a grantor must not assign a role
    more powerful than the one they themselves hold on the node.
    """
    best = 0
    for r in user.get("roles", []):
        node_path = r.get("node_path", "")
        if not node_path:
            continue
        if target_path == "/":
            matches = node_path.count("/") == 1
        else:
            matches = target_path.startswith(node_path)
        if matches:
            best = max(best, _ROLE_POWER.get(r.get("role", ""), 0))
    return best


def _team_admin_scope_ids(user: dict) -> list[str]:
    """team_id scope_ids on which the user holds the team_admin role."""
    return [
        r.get("scope_id")
        for r in user.get("roles", [])
        if r.get("role") == "team_admin" and r.get("scope_id")
    ]


def require_node_role(min_role: str = "viewer"):
    """FastAPI dependency: validates that the current user has at least
    min_role on the node identified by the `node_id` path parameter.

    Returns {"id": str, "path": str} on success.
    """

    async def _dep(
        node_id: str,
        current_user: dict = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        row = (
            await session.execute(
                text("SELECT id, path FROM organization_nodes WHERE id = CAST(:nid AS uuid)"),
                {"nid": node_id},
            )
        ).first()
        if not row:
            raise HTTPException(404, "Node not found")
        if not can_access(current_user, row[1], min_role):
            raise HTTPException(403, "Insufficient permissions for this node")
        return {"id": str(row[0]), "path": row[1]}

    return _dep


_SESSION_TTL = int(timedelta(hours=8).total_seconds())
_SESSION_TTL_REMEMBER = int(timedelta(days=30).total_seconds())
_SESSION_TTL_DEV = int(timedelta(days=7).total_seconds())
_PBKDF2_ITERS = 390_000

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


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
        # Fallback: legacy admin_session:{token} issued before the unified auth migration
        raw = await redis.get(f"admin_session:{token}")
    if not raw:
        return None
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


async def get_current_user(
    authorization: str | None = Header(default=None),
    request: Request = None,
    x_admin_token: str | None = Header(default=None),
) -> dict:
    """Validate session token. Returns unified session payload.

    Also accepts the static X-Admin-Token (same credential require_admin_auth
    honours) as a synthetic platform_admin scoped to "/", so admin tooling and
    CI that authenticate with the admin token can reach these session-based
    endpoints. This does NOT bypass auth wholesale: requests with no valid
    Bearer session and no matching admin token still get 401.
    """
    from app.config import settings as _cfg

    # When called directly (not via FastAPI DI) — e.g. _get_current_developer,
    # admin_auth.me — the Header(default=None) params arrive as their FieldInfo
    # sentinel rather than a resolved value. Normalize non-str to None.
    if not isinstance(x_admin_token, str):
        x_admin_token = None
    if not isinstance(authorization, str):
        authorization = None
    if (
        x_admin_token
        and _cfg.admin_token
        and secrets.compare_digest(x_admin_token, _cfg.admin_token)
    ):
        data = {
            "user_id": None,
            "email": "admin-token@local",
            "display_name": "Admin Token",
            "roles": [
                {"role": "platform_admin", "node_path": "/", "node_id": None, "node_name": "root"}
            ],
            "primary_node_id": None,
        }
        if request is not None:
            request.state.current_user = data
        return data

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    token = authorization.removeprefix("Bearer ").strip()
    redis = request.app.state.redis
    data = await _get_session_data(token, redis)
    if not data:
        raise HTTPException(status_code=401, detail="Session expired or invalid")

    # Reject sessions issued before a password change (D3)
    if data.get("issued_at"):
        import datetime as _dt

        cached = await redis.get(f"pwd_changed:{data['user_id']}")
        if cached:
            changed_ts = _dt.datetime.fromisoformat(
                cached if isinstance(cached, str) else cached.decode()
            ).timestamp()
            if data["issued_at"] < changed_ts:
                raise HTTPException(
                    status_code=401, detail="Session invalidated — password changed"
                )

    # Contractor access expiry check
    if data.get("access_expires_at"):
        import datetime as _dt2

        try:
            expires = _dt2.datetime.fromisoformat(data["access_expires_at"])
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=_dt2.timezone.utc)
            if _dt2.datetime.now(_dt2.timezone.utc) > expires:
                raise HTTPException(status_code=401, detail="Contractor access has expired")
        except ValueError:
            pass

    # Reload session payload from DB if node assignment changed
    if await redis.get(f"user_node_changed:{data['user_id']}") or await redis.get(
        f"user_team_changed:{data['user_id']}"
    ):
        async with async_session_maker() as db_session:
            row = (
                (
                    await db_session.execute(
                        text("""
                    SELECT u.id, u.email, u.display_name, u.status, u.primary_node_id,
                           n.name AS node_name
                    FROM users u
                    LEFT JOIN organization_nodes n ON n.id = u.primary_node_id
                    WHERE u.id = CAST(:uid AS uuid)
                """),
                        {"uid": data["user_id"]},
                    )
                )
                .mappings()
                .first()
            )
            if row:
                # Re-use existing roles from session (group IDs not available without re-login)
                roles = data.get("roles", [])
                new_payload = await _build_session_payload(row, roles)
                new_payload["node_name"] = row["node_name"]
                new_payload["issued_at"] = data.get("issued_at", 0)
                await redis.setex(_session_key(token), _SESSION_TTL, json.dumps(new_payload))
                data = new_payload
        await redis.delete(f"user_node_changed:{data['user_id']}")
        await redis.delete(f"user_team_changed:{data['user_id']}")

    if request is not None:
        request.state.current_user = data

    return data


def require_platform_admin(user: dict = Depends(get_current_user)) -> dict:
    roles = {r["role"] for r in user.get("roles", [])}
    if not roles & _GATEWAY_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Platform admin access required")
    return user


def require_developer(user: dict = Depends(get_current_user)) -> dict:
    roles = {r["role"] for r in user.get("roles", [])}
    allowed = _ENGINEER_ROLES | _GATEWAY_ADMIN_ROLES | {"team_admin", "area_owner", "unit_lead"}
    if not roles & allowed:
        raise HTTPException(status_code=403, detail="Developer access required")
    return user


def has_role(user: dict, role: str, scope_id: str | None = None) -> bool:
    for r in user.get("roles", []):
        if r.get("role") == role:
            if scope_id is None or r.get("scope_id") == scope_id:
                return True
    return False


# ---------------------------------------------------------------------------
# Deprecated stubs — kept for import compatibility with legacy routers
# (areas.py, teams.py, units.py) that are no longer registered in main.py.
# These will be removed once legacy routers are fully deleted.
# ---------------------------------------------------------------------------


async def _can_manage_team(user: dict, team_id: str, session=None) -> bool:
    """Deprecated. Use can_access() with organization_nodes paths."""
    return has_role(user, "platform_admin")


async def _can_manage_unit(user: dict, unit_id: str, session=None) -> bool:
    """Deprecated. Use can_access() with organization_nodes paths."""
    return has_role(user, "platform_admin")


async def _can_manage_area(user: dict, area_id: str) -> bool:
    """Deprecated. Use can_access() with organization_nodes paths."""
    return has_role(user, "platform_admin")


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


class ForgotPasswordRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def normalise(cls, v: str) -> str:
        return v.lower().strip()


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_strength(cls, v: str) -> str:
        _validate_password_strength(v)
        return v


class ForceResetRequest(BaseModel):
    user_id: str
    temporary_password: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _load_role_assignments(
    session: AsyncSession, group_ids: list[str], user_id: str | None = None
) -> list[dict]:
    """Load role assignments for a list of group IDs plus optional direct user assignments.

    Returns a list of {role, node_path, node_id, node_name} dicts.
    """
    results: list[dict] = []

    if group_ids:
        rows = (
            (
                await session.execute(
                    text("""
                SELECT ra.role, n.path AS node_path, n.id::text AS node_id, n.name AS node_name
                FROM role_assignments ra
                JOIN organization_nodes n ON n.id = ra.node_id
                WHERE ra.entra_group_id = ANY(:gids)
            """),
                    {"gids": group_ids},
                )
            )
            .mappings()
            .all()
        )
        results.extend(dict(r) for r in rows)

    if user_id:
        rows = (
            (
                await session.execute(
                    text("""
                SELECT ra.role, n.path AS node_path, n.id::text AS node_id, n.name AS node_name
                FROM role_assignments ra
                JOIN organization_nodes n ON n.id = ra.node_id
                WHERE ra.user_id = CAST(:uid AS uuid)
            """),
                    {"uid": user_id},
                )
            )
            .mappings()
            .all()
        )
        results.extend(dict(r) for r in rows)

    return results


# Keep legacy alias so any remaining callers don't break immediately
async def _load_user_roles(session: AsyncSession, user_id: str) -> list[dict]:
    """Legacy shim — returns empty list. Callers that need real roles
    should use _load_role_assignments() with Entra group IDs."""
    return []


async def _build_session_payload(row, roles: list[dict]) -> dict:
    is_platform_admin = any(r.get("role") in _GATEWAY_ADMIN_ROLES for r in roles)
    access_expires = row.get("access_expires_at")
    return {
        "user_id": str(row["id"]),
        "email": row["email"],
        "display_name": row["display_name"] or "",
        "roles": roles,
        "primary_node_id": str(row["primary_node_id"]) if row.get("primary_node_id") else None,
        # Legacy field kept for backwards compat with in-flight Redis sessions
        "primary_team_id": None,
        "is_platform_admin": is_platform_admin,
        "is_contractor": bool(row.get("is_contractor", False)),
        "access_expires_at": access_expires.isoformat() if access_expires else None,
        "allowed_models": list(row["allowed_models"]) if row.get("allowed_models") else None,
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
    await _check_rate_limit(
        request.app.state.redis, request.client.host if request.client else "unknown"
    )

    row = (
        (
            await session.execute(
                text("""
            SELECT u.id, u.email, u.display_name, u.password_hash, u.hash_type,
                   u.status, u.must_change_password, u.primary_node_id,
                   u.is_contractor, u.access_expires_at, u.allowed_models,
                   n.name AS node_name
            FROM users u
            LEFT JOIN organization_nodes n ON n.id = u.primary_node_id
            WHERE u.email = :email
        """),
                {"email": body.email},
            )
        )
        .mappings()
        .first()
    )

    # Constant-time dummy verify on miss
    _dummy = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TiGkn3mK3KH0K2aIvFVe7sGOHMCC"
    stored_hash = row["password_hash"] if row else _dummy
    hash_type = row["hash_type"] if row else "bcrypt"

    if not _verify_password(body.password, stored_hash, hash_type) or not row:
        from app import audit as _audit

        try:
            await _audit.record(
                session,
                request,
                "login_failure",
                "user",
                None,
                {
                    "email": body.email,
                    "ip": str(request.client.host) if request and request.client else None,
                },
            )
            await session.commit()
        except Exception:
            pass
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if row["status"] != "active":
        raise HTTPException(status_code=403, detail="Account is not active")

    # Transparently re-hash pbkdf2 → bcrypt on first login
    if hash_type == "pbkdf2":
        new_hash = _hash_bcrypt(body.password)
        await session.execute(
            text(
                "UPDATE users SET password_hash = :h, hash_type = 'bcrypt', updated_at = NOW() WHERE id = CAST(:id AS uuid)"
            ),
            {"h": new_hash, "id": str(row["id"])},
        )

    await session.execute(
        text("UPDATE users SET last_login_at = NOW() WHERE id = CAST(:id AS uuid)"),
        {"id": str(row["id"])},
    )
    await session.commit()

    from app import audit as _audit

    await _audit.record(
        session,
        request,
        "login_success",
        "user",
        str(row["id"]),
        {
            "email": body.email,
            "ip": str(request.client.host) if request and request.client else None,
        },
    )

    # Local accounts get roles via local-group membership: each local group is
    # bound to a node through a role_assignments row (entra_group_id = the
    # lcl-... group id). Entra users instead get groups from token claims.
    group_ids = [
        r[0]
        for r in (
            await session.execute(
                text("SELECT group_id FROM local_group_members WHERE user_id = CAST(:uid AS uuid)"),
                {"uid": str(row["id"])},
            )
        ).all()
    ]
    roles = await _load_role_assignments(session, group_ids, user_id=str(row["id"]))

    payload = await _build_session_payload(row, roles)
    payload["node_name"] = row["node_name"]

    # TTL: admins get 8h/30d, engineers get 7d/30d
    is_admin = any(r.get("role") in _GATEWAY_ADMIN_ROLES for r in roles)
    if body.remember_me:
        ttl = _SESSION_TTL_REMEMBER
    elif is_admin:
        ttl = _SESSION_TTL
    else:
        ttl = _SESSION_TTL_DEV

    import time as _time

    payload["issued_at"] = _time.time()

    token = await _issue_session(request.app.state.redis, payload, ttl)

    # Track session in per-user sorted set for session listing (D4)
    token_prefix = hashlib.sha256(token.encode()).hexdigest()[:16]
    sessions_key = f"user_sessions:{payload['user_id']}"
    await request.app.state.redis.zadd(sessions_key, {token_prefix: _time.time()})
    await request.app.state.redis.expire(sessions_key, ttl)

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
    await _check_rate_limit(
        request.app.state.redis, request.client.host if request.client else "unknown"
    )

    exists = (
        await session.execute(
            text("SELECT id FROM users WHERE email = :email"),
            {"email": body.email},
        )
    ).first()
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
        {
            "id": user_id,
            "email": body.email,
            "display_name": body.display_name.strip(),
            "hash": pw_hash,
        },
    )
    await session.commit()

    # Self-service registrants get the base `engineer` role so they can use the
    # developer portal. Elevated/node-scoped roles still come from an admin
    # assigning their Entra group to a node (role_assignments).
    roles: list[dict] = [
        {"role": "engineer", "node_path": "/", "node_id": None, "node_name": "root"}
    ]
    payload = {
        "user_id": user_id,
        "email": body.email,
        "display_name": body.display_name.strip(),
        "roles": roles,
        "primary_node_id": None,
        "primary_team_id": None,  # legacy compat
        "is_platform_admin": False,
        "is_contractor": False,
        "access_expires_at": None,
        "allowed_models": None,
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
    # No auth dependency: logout just invalidates the supplied token. Derive the
    # user from the session itself (this is also called directly by
    # admin_auth.logout, where a Depends-injected current_user wouldn't resolve).
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        redis = request.app.state.redis
        data = await _get_session_data(token, redis)
        await redis.delete(_session_key(token))
        # Remove from user sessions sorted set (D4)
        if data and data.get("user_id"):
            token_prefix = hashlib.sha256(token.encode()).hexdigest()[:16]
            sessions_key = f"user_sessions:{data['user_id']}"
            await redis.zrem(sessions_key, token_prefix)
    return {"ok": True}


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    user = await get_current_user(authorization, request)

    row = (
        (
            await session.execute(
                text("SELECT id, password_hash, hash_type FROM users WHERE id = CAST(:id AS uuid)"),
                {"id": user["user_id"]},
            )
        )
        .mappings()
        .first()
    )

    if not row or not _verify_password(
        body.current_password, row["password_hash"], row["hash_type"]
    ):
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
    rows = (
        (
            await session.execute(
                text("""
        SELECT u.id, u.email, u.display_name, u.status, u.must_change_password,
               u.last_login_at, u.created_at,
               COALESCE(
                   json_agg(DISTINCT jsonb_build_object(
                       'role', nm.role, 'scope_type', 'node', 'scope_id', nm.node_id::text))
                   FILTER (WHERE nm.role IS NOT NULL), '[]'
               ) AS roles
        FROM users u
        LEFT JOIN node_members nm ON nm.user_id = u.id::text
        GROUP BY u.id
        ORDER BY u.created_at DESC
    """)
            )
        )
        .mappings()
        .all()
    )
    import json as _json

    return [
        {
            **dict(r),
            "id": str(r["id"]),
            "roles": _json.loads(r["roles"]) if isinstance(r["roles"], str) else r["roles"],
        }
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
    # Per-user role grants were removed in migration 0025 (the user_roles table
    # was dropped). Platform/area/team roles are now derived from Entra group
    # mappings stored in role_assignments. There is no longer a per-user write path.
    raise HTTPException(
        status_code=501,
        detail="Per-user role grants are managed via Entra group mappings "
        "(role_assignments) now; assign the user's Entra group to a node instead.",
    )


@router.delete("/users/{user_id}/roles/{role}")
async def revoke_role(
    user_id: str,
    role: str,
    admin: dict = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_session),
):
    # Per-user role revocation was removed in migration 0025 (user_roles dropped).
    # Roles are now derived from Entra group mappings (role_assignments).
    raise HTTPException(
        status_code=501,
        detail="Per-user role revocation is managed via Entra group mappings "
        "(role_assignments) now; remove the user's Entra group from the node instead.",
    )


@router.patch("/users/{user_id}/status")
async def set_user_status(
    user_id: str,
    status: str,
    request: Request,
    admin: dict = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_session),
):
    if status not in ("active", "suspended"):
        raise HTTPException(status_code=422, detail="status must be 'active' or 'suspended'")
    await session.execute(
        text("UPDATE users SET status = :status, updated_at = NOW() WHERE id = CAST(:uid AS uuid)"),
        {"status": status, "uid": user_id},
    )
    # Invalidate all sessions for suspended users (D3)
    if status == "suspended":
        import datetime as _dt

        await request.app.state.redis.setex(
            f"pwd_changed:{user_id}",
            86400,
            _dt.datetime.now(_dt.timezone.utc).isoformat(),
        )
    await session.commit()
    return {"ok": True}


@router.patch("/users/{user_id}/profile")
async def update_user_profile(
    user_id: str,
    body: dict,
    current_user: dict = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_session),
):
    allowed = {"display_name", "primary_node_id"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=422, detail="No valid fields to update")
    # Build static SET clause from hardcoded column names — no user input in template.
    _clause_map = {
        "display_name": "display_name = :display_name",
        "primary_node_id": "primary_node_id = :primary_node_id",
    }
    set_clause = ", ".join(_clause_map[k] for k in updates)
    await session.execute(
        text("UPDATE users SET " + set_clause + ", updated_at=NOW() WHERE id = CAST(:uid AS uuid)"),
        {**updates, "uid": user_id},
    )
    await session.commit()
    return {"updated": list(updates.keys())}


# ---------------------------------------------------------------------------
# D3 — Password reset (forgot / reset / force-reset)
# ---------------------------------------------------------------------------


@router.post("/forgot-password")
async def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Always returns 200 to prevent email enumeration."""
    import os

    redis = request.app.state.redis
    row = (
        (
            await session.execute(
                text(
                    "SELECT id, display_name, email FROM users WHERE email = :e AND status = 'active'"
                ),
                {"e": body.email},
            )
        )
        .mappings()
        .first()
    )

    raw_token = None
    reset_url = None
    if row:
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        await redis.setex(f"reset:{token_hash}", 3600, str(row["id"]))

        portal_url = os.getenv("PORTAL_BASE_URL", "http://localhost:3001")
        reset_url = f"{portal_url}/reset-password?token={raw_token}"

        from app.email import password_reset_html, send_email

        await send_email(
            row["email"],
            "Reset your AI Gateway password",
            password_reset_html(portal_url, reset_url, row["display_name"] or row["email"]),
        )

    return {"message": "If that email exists, a reset link has been sent"}


@router.post("/reset-password")
async def reset_password(
    body: ResetPasswordRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    import datetime as _dt
    import os

    redis = request.app.state.redis
    token_hash = hashlib.sha256(body.token.encode()).hexdigest()
    user_id = await redis.get(f"reset:{token_hash}")
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user_id_str = user_id if isinstance(user_id, str) else user_id.decode()
    new_hash = _hash_bcrypt(body.new_password)
    await session.execute(
        text("""
            UPDATE users
            SET password_hash = :h, hash_type = 'bcrypt',
                must_change_password = FALSE,
                password_changed_at = NOW()
            WHERE id = CAST(:uid AS uuid)
        """),
        {"h": new_hash, "uid": user_id_str},
    )
    await session.commit()
    await redis.delete(f"reset:{token_hash}")

    # Cache the new timestamp so get_current_user can reject stale sessions fast
    await redis.setex(
        f"pwd_changed:{user_id_str}", 7200, _dt.datetime.now(_dt.timezone.utc).isoformat()
    )

    row = (
        (
            await session.execute(
                text("SELECT email, display_name FROM users WHERE id = CAST(:uid AS uuid)"),
                {"uid": user_id_str},
            )
        )
        .mappings()
        .first()
    )
    if row:
        portal_url = os.getenv("PORTAL_BASE_URL", "http://localhost:3001")
        from app.email import password_changed_html, send_email

        await send_email(
            row["email"],
            "Your password was changed",
            password_changed_html(portal_url, row["display_name"] or row["email"]),
        )

    return {"message": "Password reset successfully"}


@router.post("/admin/force-password-reset")
async def force_password_reset(
    body: ForceResetRequest,
    request: Request,
    current_user: dict = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_session),
):
    import datetime as _dt

    redis = request.app.state.redis

    if body.temporary_password:
        _validate_password_strength(body.temporary_password)
        new_hash = _hash_bcrypt(body.temporary_password)
        await session.execute(
            text("""UPDATE users SET must_change_password=TRUE, password_changed_at=NOW(),
                    password_hash=:h, hash_type='bcrypt'
                    WHERE id = CAST(:uid AS uuid)"""),
            {"h": new_hash, "uid": body.user_id},
        )
    else:
        await session.execute(
            text(
                "UPDATE users SET must_change_password=TRUE, password_changed_at=NOW() WHERE id = CAST(:uid AS uuid)"
            ),
            {"uid": body.user_id},
        )

    # Generate an out-of-band reset token
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    await redis.setex(f"reset:{token_hash}", 3600, body.user_id)

    # Cache invalidation — force logout of all existing sessions
    await redis.setex(
        f"pwd_changed:{body.user_id}", 7200, _dt.datetime.now(_dt.timezone.utc).isoformat()
    )

    await session.commit()
    return {"reset_token": raw_token, "message": "User must change password on next login"}


# ---------------------------------------------------------------------------
# D4 — Session visibility & management
# ---------------------------------------------------------------------------


@router.get("/sessions")
async def list_sessions(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    redis = request.app.state.redis
    sessions_key = f"user_sessions:{current_user['user_id']}"
    # Use zrange with WITHSCORES — returns all sessions sorted by score (login time)
    entries = await redis.zrange(sessions_key, 0, -1, withscores=True)
    result = []
    for sid_raw, score in entries:
        sid = sid_raw if isinstance(sid_raw, str) else sid_raw.decode()
        result.append(
            {
                "session_id": sid,
                "issued_at": score,
            }
        )
    return result


@router.delete("/sessions")
async def logout_all_other_sessions(
    request: Request,
    authorization: str | None = Header(default=None),
    current_user: dict = Depends(get_current_user),
):
    """Expire all sessions for current user except the current one."""
    redis = request.app.state.redis
    current_token = (authorization or "").removeprefix("Bearer ").strip()
    current_prefix = hashlib.sha256(current_token.encode()).hexdigest()[:16]
    sessions_key = f"user_sessions:{current_user['user_id']}"
    all_sessions = await redis.zrange(sessions_key, 0, -1)
    for sid_raw in all_sessions:
        sid = sid_raw if isinstance(sid_raw, str) else sid_raw.decode()
        if sid != current_prefix:
            await redis.zrem(sessions_key, sid)
    return {"message": "All other sessions revoked"}


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    redis = request.app.state.redis
    sessions_key = f"user_sessions:{current_user['user_id']}"
    await redis.zrem(sessions_key, session_id)
    return {"message": "Session revoked"}


# ---------------------------------------------------------------------------
# Contractor settings
# ---------------------------------------------------------------------------


class ContractorUpdateRequest(BaseModel):
    is_contractor: bool | None = None
    access_expires_at: str | None = None
    allowed_models: list[str] | None = None


@router.patch("/users/{user_id}/contractor")
async def update_contractor_settings(
    user_id: str,
    body: ContractorUpdateRequest,
    current_user: dict = Depends(require_platform_admin),
    session: AsyncSession = Depends(get_session),
):
    updates = {}
    if body.is_contractor is not None:
        updates["is_contractor"] = body.is_contractor
    if body.access_expires_at is not None:
        updates["access_expires_at"] = body.access_expires_at
    if body.allowed_models is not None:
        updates["allowed_models"] = body.allowed_models
    if not updates:
        raise HTTPException(422, "No fields to update")
    set_parts = []
    params: dict = {"uid": user_id}
    for k, v in updates.items():
        if k == "allowed_models":
            set_parts.append(f"{k} = CAST(:{k} AS text[])")
            params[k] = v
        else:
            set_parts.append(f"{k} = :{k}")
            params[k] = v
    await session.execute(
        text(f"UPDATE users SET {', '.join(set_parts)} WHERE id = CAST(:uid AS uuid)"),
        params,
    )
    await session.commit()
    return {"updated": list(updates.keys())}


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------

_VALID_ROLES = {"gateway_admin", "area_owner", "unit_lead", "team_admin", "engineer", "reporter"}
_INVITE_TTL = int(timedelta(hours=48).total_seconds())


class CreateInviteRequest(BaseModel):
    email: str
    role: str = "developer"
    scope_type: str = "global"
    scope_id: str | None = None

    @field_validator("email")
    @classmethod
    def normalise(cls, v: str) -> str:
        return v.lower().strip()

    @field_validator("role")
    @classmethod
    def check_role(cls, v: str) -> str:
        if v not in _VALID_ROLES:
            raise ValueError(f"role must be one of {sorted(_VALID_ROLES)}")
        return v


class AcceptInviteRequest(BaseModel):
    token: str
    display_name: str = Field(..., min_length=1, max_length=200)
    password: str = Field(..., min_length=12, max_length=128)

    @field_validator("password")
    @classmethod
    def strength(cls, v: str) -> str:
        _validate_password_strength(v)
        return v


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@router.post("/invitations", status_code=201)
async def create_invitation(
    body: CreateInviteRequest,
    request: Request,
    caller: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    roles = {r["role"] for r in caller.get("roles", [])}
    is_platform_admin = bool(roles & _GATEWAY_ADMIN_ROLES)
    is_team_admin = "team_admin" in roles

    # team_admin can only invite engineers/reporters to their own team
    if not is_platform_admin:
        if not is_team_admin:
            raise HTTPException(status_code=403, detail="Insufficient permissions to invite users")
        if body.role not in ("engineer", "reporter"):
            raise HTTPException(
                status_code=403, detail="Team admins can only invite engineers or reporters"
            )
        if body.scope_type != "team":
            raise HTTPException(status_code=403, detail="Team admins must invite to team scope")
        # Verify they admin that specific team
        team_scopes = [
            r.get("scope_id") for r in caller.get("roles", []) if r["role"] == "team_admin"
        ]
        if str(body.scope_id).lower() not in [str(s).lower() for s in team_scopes if s]:
            raise HTTPException(status_code=403, detail="You do not manage that team")

    import uuid as _uuid

    token = secrets.token_urlsafe(32)
    token_hash = _hash_token(token)
    invite_id = str(_uuid.uuid4())
    from datetime import UTC as _UTC
    from datetime import datetime
    from datetime import timedelta as _td

    expires_at = datetime.now(_UTC) + _td(hours=48)

    await session.execute(
        text("""
            INSERT INTO user_invitations
                (id, email, role, scope_type, scope_id, token_hash, invited_by, expires_at)
            VALUES
                (CAST(:id AS uuid), :email, :role, :scope_type,
                 CAST(:scope_id AS uuid), :token_hash,
                 CAST(:by AS uuid), :expires_at)
        """),
        {
            "id": invite_id,
            "email": body.email,
            "role": body.role,
            "scope_type": body.scope_type,
            "scope_id": body.scope_id,
            "token_hash": token_hash,
            "by": caller["user_id"],
            "expires_at": expires_at,
        },
    )
    await session.commit()

    # Return the raw token once — caller copies the link
    base = request.base_url
    accept_url = f"{base}auth/invitations/accept?token={token}"
    return {
        "invite_id": invite_id,
        "email": body.email,
        "role": body.role,
        "expires_at": expires_at.isoformat(),
        "accept_url": accept_url,
        "token": token,
    }


@router.get("/invitations")
async def list_invitations(
    caller: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    roles = {r["role"] for r in caller.get("roles", [])}
    is_platform_admin = bool(roles & _GATEWAY_ADMIN_ROLES)

    if is_platform_admin:
        rows = (
            (
                await session.execute(
                    text("""
            SELECT i.id, i.email, i.role, i.scope_type, i.scope_id::text,
                   i.expires_at, i.accepted_at, i.created_at,
                   u.email AS invited_by_email
            FROM user_invitations i
            LEFT JOIN users u ON u.id = i.invited_by
            ORDER BY i.created_at DESC
        """)
                )
            )
            .mappings()
            .all()
        )
    elif "team_admin" in roles:
        team_scopes = [
            r.get("scope_id") for r in caller.get("roles", []) if r["role"] == "team_admin"
        ]
        rows = (
            (
                await session.execute(
                    text("""
                SELECT i.id, i.email, i.role, i.scope_type, i.scope_id::text,
                       i.expires_at, i.accepted_at, i.created_at,
                       u.email AS invited_by_email
                FROM user_invitations i
                LEFT JOIN users u ON u.id = i.invited_by
                WHERE i.scope_id = ANY(CAST(:scopes AS uuid[]))
                ORDER BY i.created_at DESC
            """),
                    {"scopes": [s for s in team_scopes if s]},
                )
            )
            .mappings()
            .all()
        )
    else:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    return [dict(r) for r in rows]


@router.delete("/invitations/{invite_id}")
async def revoke_invitation(
    invite_id: str,
    caller: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    roles = {r["role"] for r in caller.get("roles", [])}
    if not (roles & _GATEWAY_ADMIN_ROLES) and "team_admin" not in roles:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    await session.execute(
        text("DELETE FROM user_invitations WHERE id = CAST(:id AS uuid) AND accepted_at IS NULL"),
        {"id": invite_id},
    )
    await session.commit()
    return {"ok": True}


@router.post("/invitations/accept", status_code=201)
async def accept_invitation(
    body: AcceptInviteRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    await _check_rate_limit(
        request.app.state.redis, request.client.host if request.client else "unknown"
    )
    token_hash = _hash_token(body.token)

    invite = (
        (
            await session.execute(
                text("""
            SELECT id, email, role, scope_type, scope_id::text
            FROM user_invitations
            WHERE token_hash = :th
              AND accepted_at IS NULL
              AND expires_at > NOW()
        """),
                {"th": token_hash},
            )
        )
        .mappings()
        .first()
    )

    if not invite:
        raise HTTPException(status_code=404, detail="Invitation not found or expired")

    # Check email not already registered
    existing = (
        await session.execute(
            text("SELECT id FROM users WHERE email = :email"),
            {"email": invite["email"]},
        )
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    import uuid as _uuid

    user_id = str(_uuid.uuid4())
    pw_hash = _hash_bcrypt(body.password)

    await session.execute(
        text("""
            INSERT INTO users (id, email, display_name, password_hash, hash_type, status)
            VALUES (CAST(:id AS uuid), :email, :display_name, :hash, 'bcrypt', 'active')
        """),
        {
            "id": user_id,
            "email": invite["email"],
            "display_name": body.display_name.strip(),
            "hash": pw_hash,
        },
    )
    # Migration 0025 dropped user_roles; the invite's role is no longer persisted
    # per-user. Role membership is now derived from Entra group mappings
    # (role_assignments). The account is created above; roles resolve at login.
    await session.execute(
        text("UPDATE user_invitations SET accepted_at = NOW() WHERE id = CAST(:id AS uuid)"),
        {"id": str(invite["id"])},
    )
    await session.commit()

    roles = await _load_user_roles(session, user_id)
    payload = {
        "user_id": user_id,
        "email": invite["email"],
        "display_name": body.display_name.strip(),
        "roles": roles,
        "primary_team_id": invite["scope_id"] if invite["scope_type"] == "team" else None,
        "team_name": None,
    }
    token = await _issue_session(request.app.state.redis, payload, _SESSION_TTL_DEV)
    return {"token": token, "user": payload}


# ---------------------------------------------------------------------------
# Bulk invite (CSV upload)
# ---------------------------------------------------------------------------


@router.post("/invitations/bulk")
async def bulk_invite(
    file: UploadFile | None = File(None),
    current_user: dict = Depends(require_platform_admin),
    request: Request = None,
    session: AsyncSession = Depends(get_session),
):
    """CSV columns: email, role, scope_type (optional), scope_id (optional)."""
    import os
    import uuid as _uuid
    from datetime import datetime
    from datetime import timedelta as _td
    from datetime import timezone as _tz

    if file is None:
        raise HTTPException(422, "No file uploaded")
    content = await file.read()
    try:
        reader = _csv.DictReader(_io.StringIO(content.decode("utf-8-sig")))
    except Exception:
        raise HTTPException(422, "Could not decode CSV — ensure UTF-8 encoding")

    sent, skipped, errors = 0, 0, []
    for i, row in enumerate(reader, start=2):
        email = (row.get("email") or "").strip().lower()
        role = (row.get("role") or "developer").strip()
        scope_type = (row.get("scope_type") or "global").strip()
        scope_id = (row.get("scope_id") or "").strip() or None

        if not email or not _EMAIL_RE.match(email):
            errors.append({"row": i, "reason": f"Invalid email: {email!r}"})
            continue
        if role not in _VALID_ROLES:
            errors.append({"row": i, "reason": f"Invalid role: {role!r}"})
            continue

        existing = (
            await session.execute(
                text(
                    "SELECT 1 FROM users WHERE email=:e UNION SELECT 1 FROM user_invitations WHERE email=:e AND accepted_at IS NULL"
                ),
                {"e": email},
            )
        ).first()
        if existing:
            skipped += 1
            continue

        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        expires_at = datetime.now(_tz.utc) + _td(days=7)

        await session.execute(
            text("""
                INSERT INTO user_invitations
                    (id, email, role, scope_type, scope_id, token_hash, invited_by, expires_at)
                VALUES (CAST(:id AS uuid), :email, :role, :scope_type,
                        CAST(:scope_id AS uuid), :token_hash, CAST(:by AS uuid), :expires_at)
            """),
            {
                "id": str(_uuid.uuid4()),
                "email": email,
                "role": role,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "token_hash": token_hash,
                "by": current_user["user_id"],
                "expires_at": expires_at,
            },
        )

        portal_url = os.getenv("PORTAL_BASE_URL", "http://localhost:3001")
        invite_link = f"{portal_url}/accept-invite?token={raw_token}"
        try:
            from app.email import send_email

            await send_email(
                email,
                "You've been invited to AI Gateway",
                f"<html><body><p>Invited as <strong>{role}</strong>. "
                f"<a href='{invite_link}'>Accept invitation</a> (expires 7 days).</p></body></html>",
            )
        except Exception:
            pass
        sent += 1

    await session.commit()
    return {"sent": sent, "skipped": skipped, "errors": errors}


# ---------------------------------------------------------------------------
# Service accounts
# ---------------------------------------------------------------------------


class CreateServiceAccountRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    team_id: str | None = None


async def _assert_sa_in_scope(session: AsyncSession, sa_id: str, caller: dict) -> None:
    """Ensure the caller may act on this service account.

    platform_admin may act on any SA. A team_admin may act only on SAs whose
    team_id is in their team_admin scope. Raises 404 if the SA does not exist,
    403 otherwise.
    """
    roles = {r["role"] for r in caller.get("roles", [])}
    if roles & _GATEWAY_ADMIN_ROLES:
        return
    if "team_admin" not in roles:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    row = (
        (
            await session.execute(
                text(
                    "SELECT team_id::text AS team_id FROM service_accounts WHERE id = CAST(:id AS uuid)"
                ),
                {"id": sa_id},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Service account not found")
    if row["team_id"] not in _team_admin_scope_ids(caller):
        raise HTTPException(status_code=403, detail="Insufficient permissions")


@router.post("/service-accounts", status_code=201)
async def create_service_account(
    body: CreateServiceAccountRequest,
    caller: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    roles = {r["role"] for r in caller.get("roles", [])}
    if not (roles & _GATEWAY_ADMIN_ROLES):
        # A team_admin may only create a service account scoped to a team they
        # administer; a bare team_id outside their scope is rejected.
        if "team_admin" not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        if not body.team_id or body.team_id not in _team_admin_scope_ids(caller):
            raise HTTPException(
                status_code=403, detail="Cannot create a service account outside your team"
            )

    import hashlib as _hl
    import uuid as _uuid

    sa_id = str(_uuid.uuid4())
    raw_key = f"sa_{secrets.token_urlsafe(32)}"
    key_prefix = raw_key[:12]
    key_hash = _hl.sha256(raw_key.encode()).hexdigest()

    await session.execute(
        text("""
            INSERT INTO service_accounts
                (id, name, description, key_hash, key_prefix,
                 owner_user_id, team_id, created_by)
            VALUES
                (CAST(:id AS uuid), :name, :desc, :kh, :kp,
                 CAST(:owner AS uuid), CAST(:team AS uuid), CAST(:by AS uuid))
        """),
        {
            "id": sa_id,
            "name": body.name,
            "desc": body.description,
            "kh": key_hash,
            "kp": key_prefix,
            "owner": caller["user_id"],
            "team": body.team_id,
            "by": caller["user_id"],
        },
    )
    await session.commit()

    return {
        "id": sa_id,
        "name": body.name,
        "key_prefix": key_prefix,
        "api_key": raw_key,  # shown once only
        "team_id": body.team_id,
    }


@router.get("/service-accounts")
async def list_service_accounts(
    team_id: str | None = None,
    caller: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if team_id is not None:
        try:
            UUID(team_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="team_id must be a valid UUID")

    roles = {r["role"] for r in caller.get("roles", [])}
    is_platform_admin = bool(roles & _GATEWAY_ADMIN_ROLES)

    if is_platform_admin:
        rows = (
            (
                await session.execute(
                    text("""
            SELECT sa.id, sa.name, sa.description, sa.key_prefix, sa.status,
                   sa.team_id::text, t.name AS team_name,
                   sa.last_used_at, sa.created_at,
                   u.email AS owner_email
            FROM service_accounts sa
            LEFT JOIN organization_nodes t ON t.id = sa.team_id
            LEFT JOIN users u ON u.id = sa.owner_user_id
            WHERE (CAST(:team_id AS uuid) IS NULL OR sa.team_id = CAST(:team_id AS uuid))
            ORDER BY sa.created_at DESC
        """),
                    {"team_id": team_id},
                )
            )
            .mappings()
            .all()
        )
    elif "team_admin" in roles:
        team_scopes = [
            r.get("scope_id") for r in caller.get("roles", []) if r["role"] == "team_admin"
        ]
        if team_id:
            if str(team_id).lower() not in [str(s).lower() for s in team_scopes if s]:
                raise HTTPException(status_code=403, detail="Not authorized for this team")
            effective_scopes = [team_id]
        else:
            effective_scopes = [s for s in team_scopes if s]
        rows = (
            (
                await session.execute(
                    text("""
                SELECT sa.id, sa.name, sa.description, sa.key_prefix, sa.status,
                       sa.team_id::text, t.name AS team_name,
                       sa.last_used_at, sa.created_at,
                       u.email AS owner_email
                FROM service_accounts sa
                LEFT JOIN organization_nodes t ON t.id = sa.team_id
                LEFT JOIN users u ON u.id = sa.owner_user_id
                WHERE sa.team_id = ANY(CAST(:scopes AS uuid[]))
                ORDER BY sa.created_at DESC
            """),
                    {"scopes": effective_scopes},
                )
            )
            .mappings()
            .all()
        )
    else:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    return [dict(r) for r in rows]


@router.patch("/service-accounts/{sa_id}/status")
async def set_service_account_status(
    sa_id: str,
    status: str,
    caller: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _assert_sa_in_scope(session, sa_id, caller)
    if status not in ("active", "suspended", "revoked"):
        raise HTTPException(status_code=422, detail="Invalid status")
    await session.execute(
        text(
            "UPDATE service_accounts SET status = :s, updated_at = NOW() WHERE id = CAST(:id AS uuid)"
        ),
        {"s": status, "id": sa_id},
    )
    await session.commit()
    return {"ok": True}


@router.post("/service-accounts/{sa_id}/rotate-key")
async def rotate_service_account_key(
    sa_id: str,
    caller: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _assert_sa_in_scope(session, sa_id, caller)

    import hashlib as _hl

    raw_key = f"sa_{secrets.token_urlsafe(32)}"
    key_prefix = raw_key[:12]
    key_hash = _hl.sha256(raw_key.encode()).hexdigest()

    await session.execute(
        text("""
            UPDATE service_accounts
            SET key_hash = :kh, key_prefix = :kp, updated_at = NOW()
            WHERE id = CAST(:id AS uuid)
        """),
        {"kh": key_hash, "kp": key_prefix, "id": sa_id},
    )
    await session.commit()
    return {"api_key": raw_key, "key_prefix": key_prefix}


# ---------------------------------------------------------------------------
# OIDC / SSO
# ---------------------------------------------------------------------------

oidc_router = APIRouter(prefix="/auth", tags=["auth-oidc"])

_OIDC_STATE_TTL = 300  # 5 minutes


def _oidc_redirect_uri(request: Request) -> str:
    """Return the OIDC callback URI.

    Uses OIDC_BASE_URL when set (required in production). In non-production
    environments (ENVIRONMENT=development|test|ci) falls back to request.base_url
    so local dev works without explicit configuration. In production, raises 500
    if OIDC_BASE_URL is unset to prevent Host-header manipulation.
    """
    from app.config import settings as _cfg

    if _cfg.oidc_base_url:
        return _cfg.oidc_base_url.rstrip("/") + "/auth/oidc/callback"

    if _cfg.environment.lower() in ("development", "test", "ci"):
        return str(request.base_url).rstrip("/") + "/auth/oidc/callback"

    raise HTTPException(
        status_code=500,
        detail="OIDC_BASE_URL is not configured. Required in production to prevent Host-header manipulation.",
    )


@oidc_router.get("/oidc/login")
async def oidc_login(request: Request):
    """Redirect to the configured OIDC provider (Dex / Entra ID)."""
    import urllib.parse as _up

    from app.config import settings as _cfg

    state = secrets.token_urlsafe(16)
    await request.app.state.redis.setex(f"oidc_state:{state}", _OIDC_STATE_TTL, "1")

    redirect_uri = _oidc_redirect_uri(request)
    params = _up.urlencode(
        {
            "client_id": _cfg.oidc_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
        }
    )
    from fastapi.responses import RedirectResponse as _RR

    return _RR(f"{_cfg.oidc_issuer}/auth?{params}")


@oidc_router.get("/oidc/callback")
async def oidc_callback(
    code: str,
    state: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):

    import httpx as _httpx

    from app.config import settings as _cfg

    # Validate state
    stored = await request.app.state.redis.get(f"oidc_state:{state}")
    if not stored:
        logger.warning("OIDC state validation failed", extra={"state_prefix": state[:8]})
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")
    await request.app.state.redis.delete(f"oidc_state:{state}")

    redirect_uri = _oidc_redirect_uri(request)

    import jwt as _jwt
    from jwt.algorithms import ECAlgorithm as _ECAlg
    from jwt.algorithms import RSAAlgorithm as _RSAAlg

    # Exchange code for tokens; fetch OIDC JWKS in the same connection for id_token verification
    async with _httpx.AsyncClient() as client:
        token_resp = await client.post(
            f"{_cfg.oidc_issuer}/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": _cfg.oidc_client_id,
                "client_secret": _cfg.oidc_client_secret,
            },
            headers={"Accept": "application/json"},
        )
        if token_resp.status_code != 200:
            raise HTTPException(status_code=502, detail="OIDC token exchange failed")

        id_token_raw = token_resp.json().get("id_token")
        if not id_token_raw:
            raise HTTPException(status_code=502, detail="No id_token in OIDC response")

        disco_resp = await client.get(f"{_cfg.oidc_issuer}/.well-known/openid-configuration")
        if disco_resp.status_code != 200:
            raise HTTPException(status_code=502, detail="OIDC discovery endpoint unavailable")
        jwks_resp = await client.get(disco_resp.json()["jwks_uri"])
        if jwks_resp.status_code != 200:
            raise HTTPException(status_code=502, detail="OIDC JWKS endpoint unavailable")

    # Verify id_token: signature, issuer, audience, and expiry
    _header = _jwt.get_unverified_header(id_token_raw)
    _alg = _header.get("alg", "RS256")
    _kid = _header.get("kid")
    _key_data = next(
        (k for k in jwks_resp.json().get("keys", []) if _kid is None or k.get("kid") == _kid),
        None,
    )
    if _key_data is None:
        raise HTTPException(status_code=502, detail="No matching OIDC signing key found")
    try:
        _signing_key = (
            _ECAlg.from_jwk(_key_data) if _alg.startswith("ES") else _RSAAlg.from_jwk(_key_data)
        )
        claims = _jwt.decode(
            id_token_raw,
            _signing_key,
            algorithms=[_alg],
            audience=_cfg.oidc_client_id,
            issuer=_cfg.oidc_issuer,
        )
    except _jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="OIDC id_token expired")
    except Exception as exc:
        logger.warning("OIDC id_token verification failed: %s", exc)
        raise HTTPException(status_code=401, detail="OIDC id_token verification failed")

    email = claims.get("email", "").lower().strip()
    display_name = claims.get("name") or claims.get("preferred_username") or email.split("@")[0]

    if not email:
        raise HTTPException(status_code=502, detail="No email in OIDC claims")

    # Find or create user
    row = (
        (
            await session.execute(
                text("""
            SELECT u.id, u.status, u.display_name, u.primary_node_id,
                   n.name AS node_name
            FROM users u
            LEFT JOIN organization_nodes n ON n.id = u.primary_node_id
            WHERE u.email = :email
        """),
                {"email": email},
            )
        )
        .mappings()
        .first()
    )

    if not row:
        import uuid as _uuid

        user_id = str(_uuid.uuid4())
        await session.execute(
            text("""
                INSERT INTO users (id, email, display_name, password_hash, hash_type, status)
                VALUES (CAST(:id AS uuid), :email, :dn, '', 'bcrypt', 'active')
            """),
            {"id": user_id, "email": email, "dn": display_name},
        )
        await session.commit()
        user_id_str = user_id
        node_name = None
    else:
        if row["status"] != "active":
            raise HTTPException(status_code=403, detail="Account is not active")
        user_id_str = str(row["id"])
        node_name = row["node_name"]

    await session.execute(
        text("UPDATE users SET last_login_at = NOW() WHERE id = CAST(:id AS uuid)"),
        {"id": user_id_str},
    )
    await session.commit()

    # Load role assignments from Entra group membership (pure read, no writes to DB)
    group_ids = claims.get("groups", [])
    roles = await _load_role_assignments(session, group_ids)

    payload = {
        "user_id": user_id_str,
        "email": email,
        "display_name": display_name,
        "roles": roles,
        "primary_node_id": None,
        "primary_team_id": None,  # legacy compat
        "node_name": node_name,
        "group_ids": group_ids,
        "is_platform_admin": any(r.get("role") in _GATEWAY_ADMIN_ROLES for r in roles),
        "is_contractor": False,
        "access_expires_at": None,
        "allowed_models": None,
    }
    token = await _issue_session(request.app.state.redis, payload, _SESSION_TTL_DEV)

    # Redirect to the appropriate portal with token in fragment
    role_names = {r["role"] for r in roles}
    if role_names & (_GATEWAY_ADMIN_ROLES | {"area_owner", "team_admin"}):
        frontend = f"http://localhost:3001/admin?sso_token={token}"
    else:
        frontend = f"http://localhost:3002/portal?sso_token={token}"

    from fastapi.responses import RedirectResponse as _RR

    return _RR(frontend)
