import calendar
import time
from datetime import datetime, timezone

import asyncpg

from app.models import GatewayEvent

_PRICING_TTL = 300  # seconds before re-fetching from DB
_pricing_cache: dict[str, tuple[float, float]] = {}
_pricing_fetched_at: float = 0.0


async def _load_pricing(pool: asyncpg.Pool) -> dict[str, tuple[float, float]]:
    rows = await pool.fetch(
        "SELECT model_prefix, price_input_per_1k, price_output_per_1k FROM model_pricing"
    )
    return {
        r["model_prefix"]: (float(r["price_input_per_1k"]), float(r["price_output_per_1k"]))
        for r in rows
    }


def _estimate_cost(
    model: str,
    tokens_input: int,
    tokens_output: int,
    prices: dict[str, tuple[float, float]],
) -> float:
    for prefix, (price_in, price_out) in prices.items():
        if model.startswith(prefix):
            return (tokens_input * price_in + tokens_output * price_out) / 1000
    return 0.0


def _end_of_month() -> int:
    """Unix timestamp of the last second of the current UTC month."""
    now = datetime.now(timezone.utc)
    last_day = calendar.monthrange(now.year, now.month)[1]
    end = datetime(now.year, now.month, last_day, 23, 59, 59, tzinfo=timezone.utc)
    return int(end.timestamp())


async def _update_budget_counters(redis, team_id: str, key_id: str | None, cost_usd: float) -> None:
    """Increment Redis spend counters for team, key, and org. Fail silently."""
    if cost_usd <= 0:
        return
    try:
        month = datetime.utcnow().strftime("%Y-%m")
        expiry = _end_of_month()

        pipe = redis.pipeline()

        # Team spend counter
        pipe.incrbyfloat(f"budget:team:{team_id}:{month}", cost_usd)
        pipe.expireat(f"budget:team:{team_id}:{month}", expiry)

        # Key spend counter
        if key_id:
            pipe.incrbyfloat(f"budget:key:{key_id}:{month}", cost_usd)
            pipe.expireat(f"budget:key:{key_id}:{month}", expiry)

        # Org spend counter
        pipe.incrbyfloat(f"budget:org:{month}", cost_usd)
        pipe.expireat(f"budget:org:{month}", expiry)

        await pipe.execute()
    except Exception:
        pass  # Redis unavailable — counters best-effort only


async def make_handler(db_url: str, redis=None):
    global _pricing_cache, _pricing_fetched_at
    pool = await asyncpg.create_pool(db_url)

    async def handle(event: GatewayEvent) -> None:
        global _pricing_cache, _pricing_fetched_at
        now = time.monotonic()
        if now - _pricing_fetched_at > _PRICING_TTL:
            try:
                _pricing_cache = await _load_pricing(pool)
                _pricing_fetched_at = now
            except Exception:
                pass  # keep stale cache on DB error

        cost = event.cost_usd or _estimate_cost(
            event.model or "", event.tokens_input, event.tokens_output, _pricing_cache
        )

        # Convert key_id string to UUID for the DB column (None is fine too)
        import uuid
        key_uuid = None
        if event.key_id:
            try:
                key_uuid = uuid.UUID(event.key_id)
            except ValueError:
                key_uuid = None

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO cost_records
                    (team_id, project_id, model, tokens_input, tokens_output,
                     cost_usd, cache_hit, latency_ms, api_key_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                event.team_id,
                event.project_id,
                event.model or "unknown",
                event.tokens_input,
                event.tokens_output,
                cost,
                event.cache_hit,
                event.latency_ms,
                key_uuid,
            )

        # Update Redis spend counters after successful DB write
        if redis is not None:
            await _update_budget_counters(redis, event.team_id, event.key_id, cost)

    return handle, pool
