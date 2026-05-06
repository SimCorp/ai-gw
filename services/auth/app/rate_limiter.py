from fastapi import HTTPException
from redis.asyncio import Redis


async def check_rate_limit(team_id: str, model: str, redis: Redis, rpm_limit: int) -> None:
    """Fixed-window rate limit. Window TTL is set only on first request, not reset each call."""
    key = f"ratelimit:{team_id}:{model}"
    async with redis.pipeline(transaction=True) as pipe:
        # SET NX with 60s TTL creates the key on first request of each window.
        # Subsequent INCRs within the window do not touch the TTL.
        await pipe.watch(key)
        pipe.multi()
        pipe.incr(key)
        pipe.expire(key, 60, nx=True)
        results = await pipe.execute()
    count = results[0]
    if count > rpm_limit:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": "60"},
        )
