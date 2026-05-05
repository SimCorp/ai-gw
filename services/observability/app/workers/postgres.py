import asyncpg

from app.models import GatewayEvent

# (input $/1k tokens, output $/1k tokens) — update as provider pricing changes.
_PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-4-7": (0.015, 0.075),
    "claude-sonnet-4-6": (0.003, 0.015),
    "claude-haiku-4-5": (0.0008, 0.004),
    "gpt-4o": (0.0025, 0.01),
    "gpt-4o-mini": (0.00015, 0.0006),
    "gemini-1.5-pro": (0.00125, 0.005),
    "gemini-1.5-flash": (0.000075, 0.0003),
}


def _estimate_cost(model: str, tokens_input: int, tokens_output: int) -> float:
    for prefix, (price_in, price_out) in _PRICES.items():
        if model.startswith(prefix):
            return (tokens_input * price_in + tokens_output * price_out) / 1000
    return 0.0


async def make_handler(db_url: str):
    pool = await asyncpg.create_pool(db_url)

    async def handle(event: GatewayEvent) -> None:
        cost = event.cost_usd or _estimate_cost(
            event.model or "", event.tokens_input, event.tokens_output
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
