from fastapi import HTTPException
from redis.asyncio import Redis


async def check_rate_limit(team_id: str, model: str, redis: Redis, rpm_limit: int) -> None:
    """Sliding-window rate limit using a pipeline to batch INCR + EXPIRE atomically."""
    key = f"ratelimit:{team_id}:{model}"
    async with redis.pipeline(transaction=False) as pipe:
        pipe.incr(key)
        pipe.expire(key, 60)
        results = await pipe.execute()
    count = results[0]
    if count > rpm_limit:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": "60"},
        )
