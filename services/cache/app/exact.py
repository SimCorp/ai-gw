import hashlib
import json

from redis.asyncio import Redis


def _key(prompt: dict, team_id: str, project_id: str) -> str:
    normalised = json.dumps(prompt, sort_keys=True, ensure_ascii=False).strip()
    digest = hashlib.sha256(normalised.encode()).hexdigest()
    return f"exact:{team_id}:{project_id}:{digest}"


async def get(prompt: dict, redis: Redis, team_id: str = "", project_id: str = "") -> dict | None:
    raw = await redis.get(_key(prompt, team_id, project_id))
    if raw is None:
        return None
    return json.loads(raw)


async def set(
    prompt: dict, response: dict, ttl: int, redis: Redis, team_id: str = "", project_id: str = ""
) -> None:
    await redis.setex(_key(prompt, team_id, project_id), ttl, json.dumps(response))
