"""Developer identity resolution for the Memory Palace service.

Two-step fallback:
1. POST {AUTH_URL}/validate → get key_id → query DB for developer_id
2. GET {ADMIN_URL}/dev-auth/me with Bearer token → get developer_id directly
"""
from __future__ import annotations

import logging

import asyncpg
import httpx
from fastapi import HTTPException

from app.config import settings

_log = logging.getLogger(__name__)


async def resolve_developer(
    token: str,
    http: httpx.AsyncClient,
    pool: asyncpg.Pool,
) -> str:
    """Return developer_id (str UUID) for the given Bearer token.

    Raises HTTP 401 if the token cannot be resolved to a developer.
    """
    # Step 1: validate via auth service to get key_id
    try:
        resp = await http.post(
            f"{settings.auth_url}/validate",
            json={"token": token, "model": ""},
            timeout=5.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            key_id = data.get("key_id")
            if key_id:
                row = await pool.fetchrow(
                    "SELECT developer_id FROM api_keys WHERE id = $1::uuid",
                    key_id,
                )
                if row and row["developer_id"]:
                    return str(row["developer_id"])
    except Exception as exc:
        _log.debug("Auth /validate failed: %s", exc)

    # Step 2: fall back to admin dev-auth/me
    try:
        resp = await http.get(
            f"{settings.admin_url}/dev-auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            developer_id = data.get("developer_id")
            if developer_id:
                return str(developer_id)
    except Exception as exc:
        _log.debug("Admin /dev-auth/me failed: %s", exc)

    raise HTTPException(status_code=401, detail="Invalid or expired token")
