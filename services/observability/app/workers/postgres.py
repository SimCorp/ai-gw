import asyncpg

from app.models import GatewayEvent


async def make_handler(db_url: str):
    pool = await asyncpg.create_pool(db_url)

    async def handle(event: GatewayEvent) -> None:
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
                event.cost_usd,
                event.cache_hit,
                event.latency_ms,
            )

    return handle, pool
