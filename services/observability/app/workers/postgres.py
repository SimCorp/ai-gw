import calendar
import time
import uuid
from datetime import date, datetime, timezone

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


async def _resolve_developer_id(pool: asyncpg.Pool, key_uuid: uuid.UUID | None) -> uuid.UUID | None:
    """Look up developer_id via the api_key → developer link."""
    if not key_uuid:
        return None
    try:
        row = await pool.fetchrow(
            "SELECT developer_id FROM api_keys WHERE id = $1", key_uuid
        )
        return row["developer_id"] if row else None
    except Exception:
        return None


def _session_quality_score(turn_count: int, retry_count: int, error_count: int, avg_inter_s: float | None) -> int:
    """Rule-based session quality score 1–5 based on DX Agent Experience signals."""
    score = 3
    total = max(1, turn_count)
    retry_rate = retry_count / total
    error_rate = error_count / total

    if retry_rate < 0.1:
        score += 1
    elif retry_rate > 0.3:
        score -= 1

    if error_rate < 0.1:
        score += 1
    elif error_rate > 0.3:
        score -= 1

    # Focused session (3–10 turns) = good; very long = possible struggle
    if 3 <= turn_count <= 10:
        score += 0
    elif turn_count > 20:
        score -= 1
    elif turn_count == 1:
        score -= 1  # single-turn = likely abandoned

    # Inter-request timing: long gaps suggest flow (developer applying AI output)
    if avg_inter_s is not None:
        if avg_inter_s > 120:
            score += 1
        elif avg_inter_s < 10 and turn_count > 3:
            score -= 1  # rapid-fire = possible struggle

    return max(1, min(5, score))


async def _upsert_session(pool: asyncpg.Pool, event: GatewayEvent, developer_id: uuid.UUID | None, cost: float) -> None:
    """Upsert session aggregates keyed by session_trace_id. Fail silently."""
    if not event.session_trace_id:
        return
    try:
        now = event.timestamp
        row = await pool.fetchrow(
            "SELECT turn_count, retry_count, error_count, first_request_at, total_tokens FROM sessions WHERE session_trace_id = $1",
            event.session_trace_id,
        )
        if row:
            new_turns = row["turn_count"] + 1
            elapsed = (now - row["first_request_at"]).total_seconds()
            avg_inter = elapsed / max(1, new_turns - 1)
            new_retries = row["retry_count"] + event.retry_count
            new_errors = row["error_count"] + (1 if event.request_error_type else 0)
            quality = _session_quality_score(new_turns, new_retries, new_errors, avg_inter)
            await pool.execute(
                """
                UPDATE sessions SET
                    last_request_at = $1, turn_count = $2, total_tokens = total_tokens + $3,
                    total_cost = total_cost + $4, retry_count = $5, error_count = $6,
                    tool_invocations = tool_invocations + $7,
                    quality_score = $8, avg_inter_request_s = $9,
                    dominant_intent = COALESCE($10, dominant_intent),
                    updated_at = NOW()
                WHERE session_trace_id = $11
                """,
                now, new_turns, event.tokens_input + event.tokens_output,
                cost, new_retries, new_errors, event.tool_invocation_count,
                quality, avg_inter, event.request_intent, event.session_trace_id,
            )
        else:
            await pool.execute(
                """
                INSERT INTO sessions
                    (session_trace_id, developer_id, team_id, first_request_at, last_request_at,
                     turn_count, total_tokens, total_cost, retry_count, error_count,
                     tool_invocations, session_purpose, repo, primary_model,
                     quality_score, avg_inter_request_s, dominant_intent)
                VALUES ($1, $2, $3, $4, $4, 1, $5, $6, $7, $8, $9, $10, $11, $12, $13, NULL, $14)
                """,
                event.session_trace_id, developer_id, event.team_id, now,
                event.tokens_input + event.tokens_output, cost,
                event.retry_count, 1 if event.request_error_type else 0,
                event.tool_invocation_count, event.session_purpose, event.repo,
                event.model,
                _session_quality_score(1, event.retry_count, 1 if event.request_error_type else 0, None),
                event.request_intent,
            )
    except Exception:
        pass


async def _upsert_activity_log(pool: asyncpg.Pool, developer_id: uuid.UUID, cost_usd: float, event: GatewayEvent) -> None:
    """Upsert daily activity rollup for the developer. Fail silently."""
    try:
        today = date.today()
        await pool.execute(
            """
            INSERT INTO developer_activity_log
                (developer_id, date, request_count, tokens_input, tokens_output,
                 cost_usd, cache_hits, tool_invocations, error_count)
            VALUES ($1, $2, 1, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (developer_id, date) DO UPDATE SET
                request_count      = developer_activity_log.request_count + 1,
                tokens_input       = developer_activity_log.tokens_input + EXCLUDED.tokens_input,
                tokens_output      = developer_activity_log.tokens_output + EXCLUDED.tokens_output,
                cost_usd           = developer_activity_log.cost_usd + EXCLUDED.cost_usd,
                cache_hits         = developer_activity_log.cache_hits + EXCLUDED.cache_hits,
                tool_invocations   = developer_activity_log.tool_invocations + EXCLUDED.tool_invocations,
                error_count        = developer_activity_log.error_count + EXCLUDED.error_count
            """,
            developer_id,
            today,
            event.tokens_input,
            event.tokens_output,
            cost_usd,
            1 if event.cache_hit else 0,
            event.tool_invocation_count,
            1 if event.request_error_type else 0,
        )
    except Exception:
        pass  # Fail silently — activity log is best-effort


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

        key_uuid = None
        if event.key_id:
            try:
                key_uuid = uuid.UUID(event.key_id)
            except ValueError:
                key_uuid = None

        developer_id = await _resolve_developer_id(pool, key_uuid)

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO cost_records
                    (team_id, project_id, model, tokens_input, tokens_output,
                     cost_usd, cache_hit, latency_ms, api_key_id,
                     developer_id, session_trace_id, tool_invocation_count,
                     retry_count, request_error_type, cache_namespace,
                     repo, session_purpose)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9,
                        $10, $11, $12, $13, $14, $15, $16, $17)
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
                developer_id,
                event.session_trace_id,
                event.tool_invocation_count,
                event.retry_count,
                event.request_error_type,
                event.cache_namespace,
                event.repo,
                event.session_purpose,
            )

        if redis is not None:
            await _update_budget_counters(redis, event.team_id, event.key_id, cost)

        await _upsert_session(pool, event, developer_id, cost)

        if developer_id:
            await _upsert_activity_log(pool, developer_id, cost, event)

    return handle, pool
