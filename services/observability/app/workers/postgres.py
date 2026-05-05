import time

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


async def make_handler(db_url: str):
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
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO cost_records
                    (team_id, project_id, model, tokens_input, tokens_output,
                     cost_usd, cache_hit, latency_ms)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                event.team_id,
                event.project_id,
                event.model or "unknown",
                event.tokens_input,
                event.tokens_output,
                cost,
                event.cache_hit,
                event.latency_ms,
            )

    return handle, pool
