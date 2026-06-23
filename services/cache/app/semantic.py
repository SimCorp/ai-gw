import asyncio
import json
import random
from datetime import datetime, timedelta, timezone

import asyncpg
from openai import AsyncOpenAI
from redis.asyncio import Redis

from app.config import settings as _settings

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


def _emb_to_str(embedding: list[float]) -> str:
    """Encode a float list as a pgvector literal '[x,y,...]'.

    Avoids requiring the pgvector Python package — asyncpg accepts the string
    literal and casts it with $n::vector.
    """
    return "[" + ",".join(map(str, embedding)) + "]"


async def embed(text: str, model: str | None = None) -> list[float]:
    resp = await _client.embeddings.create(
        input=text,
        model=model or _settings.embedding_model,
    )
    return resp.data[0].embedding


async def get(
    embedding: list[float],
    threshold: float,
    pool: asyncpg.Pool,
    redis: Redis,
    team_id: str = "",
    project_id: str = "",
) -> tuple[dict | None, float]:
    """Return (cached_response, best_similarity_score).

    Uses a single HNSW-indexed query to find the nearest neighbor, then checks
    the score in Python.  This replaces the previous O(N) Redis key scan.

    similarity_score is 0.0 when the circuit is open or no live entries exist
    for the team/project.  When response is None and score > 0, it is a
    near-miss (below threshold) — the caller can log it for baseline metrics.
    """
    if await is_circuit_open(redis):
        return None, 0.0

    row = await pool.fetchrow(
        """
        SELECT response, 1 - (embedding <=> $1::vector) AS similarity
        FROM cache_entries
        WHERE team_id = $2
          AND project_id = $3
          AND expires_at > NOW()
        ORDER BY embedding <=> $1::vector
        LIMIT 1
        """,
        _emb_to_str(embedding),
        team_id,
        project_id,
    )
    if row is None:
        return None, 0.0

    score = float(row["similarity"])
    response_raw = row["response"]
    # asyncpg may return JSONB as str or dict depending on codec configuration;
    # normalise to dict unconditionally.
    if isinstance(response_raw, str):
        response_raw = json.loads(response_raw)
    if score >= threshold:
        return response_raw, score
    return None, score  # near-miss: caller logs score for P2 instrumentation


async def set(
    embedding: list[float],
    response: dict,
    ttl: int,
    pool: asyncpg.Pool,
    redis: Redis,
    team_id: str = "",
    project_id: str = "",
) -> None:
    if await is_circuit_open(redis):
        return

    # ±10% jitter prevents thundering-herd expiry
    jitter = random.randint(-ttl // 10, ttl // 10)
    jittered_ttl = max(1, ttl + jitter)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=jittered_ttl)

    await pool.execute(
        """
        INSERT INTO cache_entries (team_id, project_id, embedding, response, expires_at)
        VALUES ($1, $2, $3::vector, $4::jsonb, $5)
        """,
        team_id,
        project_id,
        _emb_to_str(embedding),
        json.dumps(response),
        expires_at,
    )
