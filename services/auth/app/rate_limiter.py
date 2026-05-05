from fastapi import HTTPException
from redis.asyncio import Redis


async def check_rate_limit(team_id: str, model: str, redis: Redis, rpm_limit: int) -> None:
    """Sliding-window rate limit: increment a per-team/model counter with 60s TTL."""
    key = f"ratelimit:{team_id}:{model}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 60)
    if count > rpm_limit:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": "60"},
        )
