import json
import uuid

import numpy as np
from openai import AsyncOpenAI
from redis.asyncio import Redis

from app.config import Settings

_INDEX = "sem_cache_idx"
_PREFIX = "sem:"


def _cosine(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    return float(np.dot(va, vb) / denom) if denom else 0.0


async def embed(text: str, settings: Settings) -> list[float]:
    # Direct client — never routes through this service to avoid recursion.
    client = AsyncOpenAI(api_key=settings.embedding_api_key, base_url=settings.embedding_base_url)
    resp = await client.embeddings.create(input=text, model=settings.embedding_model)
    return resp.data[0].embedding


async def get(embedding: list[float], threshold: float, redis: Redis) -> dict | None:
    """Brute-force cosine scan over stored embeddings. Replace with RediSearch KNN in prod."""
    keys = await redis.keys(f"{_PREFIX}*:emb")
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


async def set(embedding: list[float], response: dict, ttl: int, redis: Redis) -> None:
    entry_id = str(uuid.uuid4())
    await redis.setex(f"{_PREFIX}{entry_id}:emb", ttl, json.dumps(embedding))
    await redis.setex(f"{_PREFIX}{entry_id}:resp", ttl, json.dumps(response))
