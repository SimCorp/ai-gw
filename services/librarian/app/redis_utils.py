"""Redis client factory — supports both standalone URL and Sentinel HA mode.

Standalone (default / dev):
    REDIS_URL=redis://localhost:6379/0

Sentinel (production HA):
    REDIS_SENTINEL_HOSTS=sentinel-1:26379,sentinel-2:26379,sentinel-3:26379
    REDIS_SENTINEL_MASTER=mymaster   (default: mymaster)
"""

import os

from redis.asyncio import Redis


def make_redis(redis_url: str) -> Redis:
    """Return an async Redis client, using Sentinel when configured."""
    sentinel_hosts_env = os.getenv("REDIS_SENTINEL_HOSTS", "")
    if sentinel_hosts_env:
        from redis.asyncio.sentinel import Sentinel

        hosts = [
            (h.split(":")[0], int(h.split(":")[1]))
            for h in sentinel_hosts_env.split(",")
            if ":" in h
        ]
        master_name = os.getenv("REDIS_SENTINEL_MASTER", "mymaster")
        sentinel = Sentinel(hosts, socket_timeout=0.5)
        return sentinel.master_for(master_name, decode_responses=True)

    return Redis.from_url(redis_url, decode_responses=True)
