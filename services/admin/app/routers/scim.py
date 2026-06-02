"""
SCIM 2.0 provisioning endpoint for Azure Entra ID.
Auth: Bearer token via SCIM_BEARER_TOKEN env var (not user sessions).
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session

router = APIRouter(prefix="/scim/v2", tags=["scim"])

SCIM_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"


def _require_scim_auth(authorization: str | None = Header(default=None)):
    expected = os.getenv("SCIM_BEARER_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="SCIM provisioning not configured")
    if not authorization or authorization.removeprefix("Bearer ").strip() != expected:
        raise HTTPException(status_code=401, detail="Invalid SCIM bearer token")


def _user_to_scim(row: dict) -> dict:
    return {
        "schemas": [SCIM_SCHEMA],
        "id": str(row["id"]),
        "externalId": row.get("scim_external_id"),
        "userName": row["email"],
        "name": {"formatted": row.get("display_name") or row["email"]},
        "emails": [{"value": row["email"], "primary": True}],
        "active": row["status"] == "active",
        "meta": {"resourceType": "User"},
    }


@router.get("/Users")
async def list_users(
    _: None = Depends(_require_scim_auth),
    session: AsyncSession = Depends(get_session),
    startIndex: int = 1,
    count: int = 100,
    filter: str | None = None,
):
    params: dict = {"limit": count, "offset": max(0, startIndex - 1)}
    where = "1=1"
    if filter and "userName eq" in filter:
        # Basic filter: userName eq "user@example.com"
        email = filter.split('"')[1] if '"' in filter else None
        if email:
            where = "email = :email"
            params["email"] = email

    rows = (
        (
            await session.execute(
                text(f"""
        SELECT id, email, display_name, status, scim_external_id
        FROM users WHERE {where}
        ORDER BY created_at LIMIT :limit OFFSET :offset
    """),
                params,
            )
        )
        .mappings()
        .all()
    )

    total = (
        await session.execute(
            text(f"SELECT COUNT(*) FROM users WHERE {where}"),
            {k: v for k, v in params.items() if k not in ("limit", "offset")},
        )
    ).scalar()

    return {
        "schemas": [LIST_SCHEMA],
        "totalResults": total,
        "startIndex": startIndex,
        "itemsPerPage": count,
        "Resources": [_user_to_scim(dict(r)) for r in rows],
    }


@router.get("/Users/{user_id}")
async def get_user(
    user_id: str,
    _: None = Depends(_require_scim_auth),
    session: AsyncSession = Depends(get_session),
):
    row = (
        (
            await session.execute(
                text(
                    "SELECT id, email, display_name, status, scim_external_id FROM users WHERE id = CAST(:uid AS uuid)"
                ),
                {"uid": user_id},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_to_scim(dict(row))


@router.post("/Users", status_code=201)
async def create_user(
    body: dict,
    _: None = Depends(_require_scim_auth),
    session: AsyncSession = Depends(get_session),
):
    email = body.get("userName") or ""
    display_name = body.get("name", {}).get("formatted") or email
    external_id = body.get("externalId")
    active = body.get("active", True)
    status = "active" if active else "suspended"

    existing = (
        await session.execute(text("SELECT id FROM users WHERE email = :e"), {"e": email})
    ).first()
    if existing:
        return _user_to_scim(
            {
                "id": str(existing[0]),
                "email": email,
                "display_name": display_name,
                "status": status,
                "scim_external_id": external_id,
            }
        )

    import secrets as _sec

    import bcrypt as _bc

    rand_pw = _sec.token_urlsafe(24)
    pw_hash = _bc.hashpw(rand_pw.encode(), _bc.gensalt(rounds=12)).decode()

    await session.execute(
        text("""
        INSERT INTO users (email, display_name, password_hash, hash_type, status,
                           must_change_password, scim_external_id)
        VALUES (:email, :dn, :ph, 'bcrypt', :status, TRUE, :eid)
    """),
        {"email": email, "dn": display_name, "ph": pw_hash, "status": status, "eid": external_id},
    )
    await session.commit()

    new_id = (
        await session.execute(text("SELECT id FROM users WHERE email=:e"), {"e": email})
    ).scalar()
    return _user_to_scim(
        {
            "id": str(new_id),
            "email": email,
            "display_name": display_name,
            "status": status,
            "scim_external_id": external_id,
        }
    )


@router.patch("/Users/{user_id}")
async def patch_user(
    user_id: str,
    body: dict,
    request: Request,
    _: None = Depends(_require_scim_auth),
    session: AsyncSession = Depends(get_session),
):
    """Handle Entra ID SCIM PATCH — primarily for deprovisioning (active=false)."""
    import datetime

    ops = body.get("Operations", [])
    for op in ops:
        op_type = op.get("op", "").lower()
        path = op.get("path", "")
        value = op.get("value")

        if op_type == "replace":
            if path == "active" or (isinstance(value, dict) and "active" in value):
                is_active = value if isinstance(value, bool) else value.get("active", True)
                new_status = "active" if is_active else "suspended"
                await session.execute(
                    text("UPDATE users SET status=:s WHERE id=CAST(:uid AS uuid)"),
                    {"s": new_status, "uid": user_id},
                )
                if not is_active:
                    # Kill all sessions immediately
                    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    await request.app.state.redis.setex(f"pwd_changed:{user_id}", 86400, now_iso)
                    # Revoke all API keys
                    await session.execute(
                        text(
                            "UPDATE api_keys SET status='revoked' WHERE owner_user_id=CAST(:uid AS uuid)"
                        ),
                        {"uid": user_id},
                    )

    await session.commit()

    row = (
        (
            await session.execute(
                text(
                    "SELECT id, email, display_name, status, scim_external_id FROM users WHERE id=CAST(:uid AS uuid)"
                ),
                {"uid": user_id},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_to_scim(dict(row))


@router.put("/Users/{user_id}")
async def replace_user(
    user_id: str,
    body: dict,
    _: None = Depends(_require_scim_auth),
    session: AsyncSession = Depends(get_session),
):
    display_name = body.get("name", {}).get("formatted", "")
    active = body.get("active", True)
    status = "active" if active else "suspended"
    await session.execute(
        text("UPDATE users SET display_name=:dn, status=:s WHERE id=CAST(:uid AS uuid)"),
        {"dn": display_name, "s": status, "uid": user_id},
    )
    await session.commit()
    row = (
        (
            await session.execute(
                text(
                    "SELECT id, email, display_name, status, scim_external_id FROM users WHERE id=CAST(:uid AS uuid)"
                ),
                {"uid": user_id},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_to_scim(dict(row))
