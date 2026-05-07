import hashlib

import asyncpg
from fastapi import HTTPException


async def validate_api_key(key: str, db: asyncpg.Connection) -> dict:
    """SHA-256 hash the key, look up in api_keys table, return {team_id, project_id}."""
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    row = await db.fetchrow(
        """
        SELECT id, team_id, project_id
        FROM api_keys
        WHERE key_hash = $1 AND revoked_at IS NULL
        """,
        key_hash,
    )
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid or revoked API key")
    return {
        "team_id": str(row["team_id"]),
        "project_id": str(row["project_id"]) if row["project_id"] else None,
        "key_id": str(row["id"]),
    }
