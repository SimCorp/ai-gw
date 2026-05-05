import hashlib
import json

from redis.asyncio import Redis

_PREFIX = "exact:"


def _key(prompt: dict) -> str:
    normalised = json.dumps(prompt, sort_keys=True, ensure_ascii=False).strip()
    return _PREFIX + hashlib.sha256(normalised.encode()).hexdigest()


async def get(prompt: dict, redis: Redis) -> dict | None:
    raw = await redis.get(_key(prompt))
    if raw is None:
        return None
    return json.loads(raw)


async def set(prompt: dict, response: dict, ttl: int, redis: Redis) -> None:
    await redis.setex(_key(prompt), ttl, json.dumps(response))
