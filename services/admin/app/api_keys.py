"""Scoped API key issuance + revocation for workflow runs.

Issues short-lived keys that inherit the parent caller's team/project so
agent containers can call cache:8002 without privilege escalation.

Plaintext is stored in Redis at `workflow:scoped_key:{run_id}` for the
duration of the run so the workflow-worker can pass it to agent containers
as AIGW_API_KEY. The Redis entry expires with the same TTL as the DB key.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_log = logging.getLogger(__name__)
_KEY_PREFIX = "aigw_run_"  # human-recognisable prefix; not authoritative
_REDIS_KEY_PREFIX = "workflow:scoped_key:"


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
    run_id: uuid.UUID | None = None,
    redis=None,
) -> tuple[str, uuid.UUID]:
    """Issue a scoped key. Returns (plaintext, key_id).

    If run_id and redis are provided, the plaintext is stored in Redis
    at workflow:scoped_key:{run_id} so the workflow-worker can retrieve
    and inject it as AIGW_API_KEY for agent containers.
    """
    plaintext, key_hash = _new_key()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    row = (
        await session.execute(
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
        )
    ).first()
    key_id = row[0]

    if run_id is not None and redis is not None:
        try:
            await redis.setex(
                f"{_REDIS_KEY_PREFIX}{run_id}",
                ttl_seconds + 60,  # 60s grace period beyond key expiry
                plaintext,
            )
        except Exception as exc:
            _log.warning("failed to store scoped key in Redis for run %s: %s", run_id, exc)

    return plaintext, key_id


async def revoke_key(session: AsyncSession, key_id: uuid.UUID) -> None:
    await session.execute(
        text("UPDATE api_keys SET revoked_at = NOW() WHERE id = :id AND revoked_at IS NULL"),
        {"id": key_id},
    )


async def delete_scoped_key_from_redis(redis, run_id: uuid.UUID) -> None:
    """Remove the plaintext from Redis when a run reaches terminal state."""
    try:
        await redis.delete(f"{_REDIS_KEY_PREFIX}{run_id}")
    except Exception as exc:
        _log.debug("Redis delete for run %s key: %s", run_id, exc)
