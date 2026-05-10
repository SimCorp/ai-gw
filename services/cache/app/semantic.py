import asyncio
import json
import random
import uuid

import numpy as np
from openai import AsyncOpenAI
from redis.asyncio import Redis

from app.config import settings as _settings

_PREFIX = "sem:"
_CIRCUIT_KEY = "embedding:circuit_open"
_CIRCUIT_COOLDOWN = 120  # seconds before auto-reset

_client = AsyncOpenAI(
    api_key=_settings.embedding_api_key,
    base_url=_settings.embedding_base_url,
)

# In-process failure counter — used to decide when to trip the breaker.
# The open/closed state is written to Redis so all replicas share it.
_circuit_failures: int = 0


def record_embedding_failure(redis: Redis | None = None) -> None:
    global _circuit_failures
    _circuit_failures += 1
    if _circuit_failures >= 5 and redis is not None:
        asyncio.create_task(_open_circuit(redis))


async def _open_circuit(redis: Redis) -> None:
    await redis.set(_CIRCUIT_KEY, "1", ex=_CIRCUIT_COOLDOWN)


async def is_circuit_open(redis: Redis) -> bool:
    return bool(await redis.exists(_CIRCUIT_KEY))


async def reset_circuit(redis: Redis | None = None) -> None:
    global _circuit_failures
    _circuit_failures = 0
    if redis is not None:
        await redis.delete(_CIRCUIT_KEY)


def _cosine(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    return float(np.dot(va, vb) / denom) if denom else 0.0


async def embed(text: str, model: str | None = None) -> list[float]:
    resp = await _client.embeddings.create(
        input=text,
        model=model or _settings.embedding_model,
    )
    return resp.data[0].embedding


async def get(
    embedding: list[float],
    threshold: float,
    redis: Redis,
    team_id: str = "",
    project_id: str = "",
) -> dict | None:
    if await is_circuit_open(redis):
        return None

    pattern = f"{_PREFIX}{team_id}:{project_id}:*:emb"
    keys = await redis.keys(pattern)
    best_score, best_key = 0.0, None
    for key in keys:
        raw = await redis.get(key)
        if raw is None:
            continue
        stored = json.loads(raw)
        score = _cosine(embedding, stored)
        if score > best_score:
            best_score, best_key = score, key

    if best_score < threshold or best_key is None:
        return None

    resp_key = best_key.replace(":emb", ":resp")
    raw_resp = await redis.get(resp_key)
    return json.loads(raw_resp) if raw_resp else None


async def set(
    embedding: list[float],
    response: dict,
    ttl: int,
    redis: Redis,
    team_id: str = "",
    project_id: str = "",
) -> None:
    if await is_circuit_open(redis):
        return

    # ±10% jitter prevents thundering-herd expiry
    jittered_ttl = max(1, ttl + random.randint(-ttl // 10, ttl // 10))
    entry_id = str(uuid.uuid4())
    prefix = f"{_PREFIX}{team_id}:{project_id}:{entry_id}"
    await redis.setex(f"{prefix}:emb", jittered_ttl, json.dumps(embedding))
    await redis.setex(f"{prefix}:resp", jittered_ttl, json.dumps(response))
