"""Scoped API key issuance + revocation for workflow runs.

Issues short-lived keys that inherit the parent caller's team/project so
agent containers can call cache:8002 without privilege escalation.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


_KEY_PREFIX = "aigw_run_"  # human-recognisable prefix; not authoritative


def _new_key() -> tuple[str, str]:
    """Generate a (plaintext, sha256-hex) pair."""
    plaintext = _KEY_PREFIX + secrets.token_urlsafe(32)
    return plaintext, hashlib.sha256(plaintext.encode()).hexdigest()


async def issue_scoped_key(
    session: AsyncSession,
    *,
    team_id: uuid.UUID,
    project_id: uuid.UUID | None,
    name: str,
    ttl_seconds: int,
    scope: str = "workflow-run",
) -> tuple[str, uuid.UUID]:
    """Issue a scoped key. Returns (plaintext, key_id).

    Caller is responsible for ensuring the parent identity can scope down
    to (team_id, project_id) — this function does NOT verify privilege
    escalation; that check belongs in the route handler.
    """
    plaintext, key_hash = _new_key()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    row = (await session.execute(
        text(
            """
            INSERT INTO api_keys (team_id, project_id, name, key_hash, scope, expires_at)
            VALUES (:team_id, :project_id, :name, :key_hash, :scope, :expires_at)
            RETURNING id
            """
        ),
        {
            "team_id": team_id,
            "project_id": project_id,
            "name": name,
            "key_hash": key_hash,
            "scope": scope,
            "expires_at": expires_at,
        },
    )).first()
    return plaintext, row[0]


async def revoke_key(session: AsyncSession, key_id: uuid.UUID) -> None:
    await session.execute(
        text("UPDATE api_keys SET revoked_at = NOW() WHERE id = :id AND revoked_at IS NULL"),
        {"id": key_id},
    )
