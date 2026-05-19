import hashlib
import json
import logging

import asyncpg
from fastapi import HTTPException

_log = logging.getLogger(__name__)
_CACHE_TTL = 300  # seconds — 5-minute survivability window during Postgres restarts


async def validate_api_key(key: str, db: asyncpg.Connection, redis=None) -> dict:
    """SHA-256 hash the key, look up in api_keys table, return {team_id, project_id, key_id}.

    Redis read-through cache: on Postgres failure with a warm cache hit, serves from Redis
    so agents survive DB restarts without interruption.
    """
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    cache_key = f"api_key_cache:{key_hash}"

    # Try Postgres first (authoritative — catches revocations immediately)
    try:
        row = await db.fetchrow(
            """
            SELECT id, team_id, project_id, scope,
                   COALESCE(scopes, ARRAY['ai-gw:inference:*']) AS scopes
            FROM api_keys
            WHERE key_hash = $1
              AND revoked_at IS NULL
              AND (expires_at IS NULL OR expires_at > NOW())
            """,
            key_hash,
        )
        if row is None:
            # Valid Postgres response: key does not exist or is revoked — evict cache
            if redis is not None:
                try:
                    await redis.delete(cache_key)
                except Exception:
                    pass
            raise HTTPException(status_code=401, detail="Invalid or revoked API key")

        identity = {
            "team_id": str(row["team_id"]),
            "project_id": str(row["project_id"]) if row["project_id"] else None,
            "key_id": str(row["id"]),
            "scope": row["scope"] if "scope" in row else "standard",
            "scopes": list(row["scopes"]) if row["scopes"] else ["ai-gw:inference:*"],
        }

        # Populate Redis cache for Postgres-outage survivability
        if redis is not None:
            try:
                await redis.setex(cache_key, _CACHE_TTL, json.dumps(identity))
            except Exception:
                pass  # cache write failure is non-fatal

        return identity

    except HTTPException:
        raise  # re-raise 401 from key-not-found above

    except Exception as pg_exc:
        # Postgres unavailable — try Redis stale cache before failing
        if redis is not None:
            try:
                cached = await redis.get(cache_key)
                if cached:
                    _log.warning(
                        "Postgres unavailable, serving API key from Redis cache (key_hash=%.8s...): %s",
                        key_hash, pg_exc,
                    )
                    return json.loads(cached)
            except Exception:
                pass

        _log.error("Postgres unavailable and no Redis cache for API key validation: %s", pg_exc)
        raise HTTPException(status_code=503, detail="Authentication service temporarily unavailable")
