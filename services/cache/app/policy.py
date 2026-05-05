from dataclasses import dataclass

from redis.asyncio import Redis

from app.config import settings as _defaults

_POLICY_PREFIX = "policy:"


@dataclass
class CachePolicy:
    ttl_seconds: int
    similarity_threshold: float
    opt_out: bool
    embedding_model: str


async def get_policy(team_id: str, project_id: str | None, redis: Redis) -> CachePolicy:
    """Read per-team policy written by admin service. Returns defaults on miss."""
    key = f"{_POLICY_PREFIX}{team_id}"
    if project_id:
        key = f"{key}:{project_id}"

    raw = await redis.hgetall(key)
    return CachePolicy(
        ttl_seconds=int(raw.get("ttl_seconds", _defaults.default_ttl_seconds)),
        similarity_threshold=float(raw.get("similarity_threshold", _defaults.default_similarity_threshold)),
        opt_out=raw.get("opt_out", "false").lower() == "true",
        embedding_model=raw.get("embedding_model", _defaults.embedding_model),
    )
