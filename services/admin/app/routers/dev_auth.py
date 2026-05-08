"""
Developer portal authentication.
Provides register / login / me / logout for the developer portal (localhost:3002).
Sessions are UUID tokens stored in Redis with a 7-day TTL.
Passwords are hashed with PBKDF2-HMAC-SHA256 (standard library, no extra deps).
"""

import hashlib
import json
import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session

router = APIRouter(prefix="/dev-auth", tags=["developer-auth"])

_SESSION_TTL = int(timedelta(days=7).total_seconds())
_ITERATIONS = 390_000  # NIST SP 800-132 recommended minimum for PBKDF2-HMAC-SHA256


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _ITERATIONS)
    return f"pbkdf2:sha256:{_ITERATIONS}:{salt}:{dk.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        parts = stored_hash.split(":")
        if parts[0] != "pbkdf2" or parts[1] != "sha256":
            return False
        iterations, salt, expected_hex = int(parts[2]), parts[3], parts[4]
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations)
        return secrets.compare_digest(dk.hex(), expected_hex)
    except Exception:
        return False


def _session_key(token: str) -> str:
    return f"dev_session:{token}"


async def _get_current_developer(
    authorization: str | None = Header(default=None),
    request: Request = None,
) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.removeprefix("Bearer ").strip()
    redis = request.app.state.redis
    raw = await redis.get(_session_key(token))
    if not raw:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: str
    display_name: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class ProfileUpdate(BaseModel):
    display_name: str | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/register", status_code=201)
async def register(
    body: RegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    # Normalise email
    email = body.email.lower().strip()
    if not email or "@" not in email:
        raise HTTPException(status_code=422, detail="Invalid email address")
    if len(body.password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")

    # Check uniqueness
    exists = (await session.execute(
        text("SELECT id FROM developers WHERE email = :email"),
        {"email": email},
    )).first()
    if exists:
        raise HTTPException(status_code=409, detail="Email already registered")

    dev_id = str(uuid.uuid4())
    pw_hash = _hash_password(body.password)
    await session.execute(
        text("""
            INSERT INTO developers (id, email, display_name, password_hash, status)
            VALUES (CAST(:id AS uuid), :email, :display_name, :password_hash, 'active')
        """),
        {"id": dev_id, "email": email, "display_name": body.display_name.strip(), "password_hash": pw_hash},
    )
    await session.commit()

    # Issue session
    token = secrets.token_urlsafe(32)
    payload = {"developer_id": dev_id, "email": email, "display_name": body.display_name.strip(), "team_id": None, "team_name": None}
    await request.app.state.redis.setex(_session_key(token), _SESSION_TTL, json.dumps(payload))

    return {"token": token, **payload}


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    email = body.email.lower().strip()
    row = (await session.execute(
        text("""
            SELECT d.id, d.email, d.display_name, d.password_hash, d.status,
                   d.team_id, t.name AS team_name
            FROM developers d
            LEFT JOIN teams t ON t.id = d.team_id
            WHERE d.email = :email
        """),
        {"email": email},
    )).mappings().first()

    if not row or not _verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if row["status"] not in ("active", "pending"):
        raise HTTPException(status_code=403, detail="Account is disabled")

    token = secrets.token_urlsafe(32)
    payload = {
        "developer_id": str(row["id"]),
        "email": row["email"],
        "display_name": row["display_name"],
        "team_id": str(row["team_id"]) if row["team_id"] else None,
        "team_name": row["team_name"],
    }
    await request.app.state.redis.setex(_session_key(token), _SESSION_TTL, json.dumps(payload))

    return {"token": token, **payload}


@router.get("/me")
async def me(developer: dict = Depends(_get_current_developer)):
    return developer


@router.patch("/profile")
async def update_profile(
    body: ProfileUpdate,
    request: Request,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    developer = await _get_current_developer(authorization, request)
    updates: dict = {}
    params: dict = {"id": developer["developer_id"]}

    if body.display_name is not None:
        updates["display_name"] = body.display_name.strip()
        params["display_name"] = updates["display_name"]

    if not updates:
        return developer

    await session.execute(
        text("UPDATE developers SET display_name = :display_name WHERE id = CAST(:id AS uuid)"),
        params,
    )
    await session.commit()

    # Refresh session payload
    token = (authorization or "").removeprefix("Bearer ").strip()
    new_payload = {**developer, **updates}
    await request.app.state.redis.setex(_session_key(token), _SESSION_TTL, json.dumps(new_payload))
    return new_payload


@router.post("/select-team")
async def select_team(
    team_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    """Let a developer associate themselves with a team (dev convenience)."""
    developer = await _get_current_developer(authorization, request)
    row = (await session.execute(
        text("SELECT id, name FROM teams WHERE id = CAST(:id AS uuid)"),
        {"id": team_id},
    )).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Team not found")

    await session.execute(
        text("UPDATE developers SET team_id = CAST(:team_id AS uuid) WHERE id = CAST(:id AS uuid)"),
        {"team_id": team_id, "id": developer["developer_id"]},
    )
    await session.commit()

    token = (authorization or "").removeprefix("Bearer ").strip()
    new_payload = {**developer, "team_id": team_id, "team_name": row["name"]}
    await request.app.state.redis.setex(_session_key(token), _SESSION_TTL, json.dumps(new_payload))
    return new_payload


@router.post("/logout")
async def logout(
    request: Request,
    authorization: str | None = Header(default=None),
):
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        await request.app.state.redis.delete(_session_key(token))
    return {"ok": True}
