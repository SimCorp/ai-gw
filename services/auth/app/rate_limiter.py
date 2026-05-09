import logging

from fastapi import HTTPException
from redis.asyncio import Redis

_log = logging.getLogger(__name__)


async def check_rate_limit(team_id: str, model: str, redis: Redis, rpm_limit: int) -> None:
    """Fixed-window rate limit. Fails open on Redis errors so agents are never blocked by infra."""
    key = f"ratelimit:{team_id}:{model}"
    try:
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
    except HTTPException:
        raise  # re-raise legitimate 429s
    except Exception as exc:
        # Redis unavailable — fail open so agents are never blocked by infra failures.
        _log.warning("Rate limiter Redis error (fail-open): %s", exc)
