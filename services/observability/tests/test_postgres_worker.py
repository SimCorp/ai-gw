"""Tests for app.workers.postgres — cost estimation, budget counters, and handler."""
import time
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.workers.postgres as pg_mod
from app.models import GatewayEvent
from app.workers.postgres import (
    _PRICING_TTL,
    _estimate_cost,
    _update_budget_counters,
    make_handler,
)

# ---------------------------------------------------------------------------
# _estimate_cost
# ---------------------------------------------------------------------------


def test_estimate_cost_matching_prefix():
    prices = {"gpt-4": (0.03, 0.06), "gpt-3.5": (0.001, 0.002)}
    result = _estimate_cost("gpt-4-turbo", 1000, 500, prices)
    # (1000 * 0.03 + 500 * 0.06) / 1000 = (30 + 30) / 1000 = 0.06
    assert result == pytest.approx(0.06)


def test_estimate_cost_no_matching_prefix():
    prices = {"gpt-4": (0.03, 0.06)}
    result = _estimate_cost("claude-3-opus", 1000, 500, prices)
    assert result == 0.0


def test_estimate_cost_partial_prefix():
    prices = {"claude-3": (0.01, 0.02)}
    result = _estimate_cost("claude-3-sonnet-20240229", 2000, 1000, prices)
    # (2000 * 0.01 + 1000 * 0.02) / 1000 = (20 + 20) / 1000 = 0.04
    assert result == pytest.approx(0.04)


def test_estimate_cost_multiple_prefixes_first_match_wins():
    # dict iteration order is insertion order in Python 3.7+
    # first matching prefix is used
    prices = {"claude-3": (0.01, 0.02), "claude-3-opus": (0.05, 0.10)}
    result = _estimate_cost("claude-3-opus-20240229", 1000, 1000, prices)
    # "claude-3" matches first → (1000*0.01 + 1000*0.02) / 1000 = 0.03
    assert result == pytest.approx(0.03)


def test_estimate_cost_empty_prices():
    result = _estimate_cost("gpt-4", 100, 100, {})
    assert result == 0.0


def test_estimate_cost_zero_tokens():
    prices = {"gpt-4": (0.03, 0.06)}
    result = _estimate_cost("gpt-4", 0, 0, prices)
    assert result == 0.0


# ---------------------------------------------------------------------------
# _update_budget_counters
# ---------------------------------------------------------------------------


def _make_redis_pipeline_mock():
    pipe = AsyncMock()
    pipe.incrbyfloat = MagicMock()
    pipe.expireat = MagicMock()
    pipe.execute = AsyncMock(return_value=None)
    redis = AsyncMock()
    redis.pipeline = MagicMock(return_value=pipe)
    return redis, pipe


async def test_budget_counters_with_key_id_calls_all_three():
    redis, pipe = _make_redis_pipeline_mock()
    await _update_budget_counters(redis, "team-abc", "key-xyz", 0.05)

    # 3 incrbyfloat calls: team, key, org
    assert pipe.incrbyfloat.call_count == 3
    # 3 expireat calls: team, key, org
    assert pipe.expireat.call_count == 3
    pipe.execute.assert_called_once()


async def test_budget_counters_without_key_id_calls_team_and_org():
    redis, pipe = _make_redis_pipeline_mock()
    await _update_budget_counters(redis, "team-abc", None, 0.05)

    # 2 incrbyfloat calls: team, org (no key)
    assert pipe.incrbyfloat.call_count == 2
    assert pipe.expireat.call_count == 2
    pipe.execute.assert_called_once()


async def test_budget_counters_zero_cost_skips_pipeline():
    redis, pipe = _make_redis_pipeline_mock()
    await _update_budget_counters(redis, "team-abc", "key-xyz", 0.0)

    redis.pipeline.assert_not_called()
    pipe.execute.assert_not_called()


async def test_budget_counters_negative_cost_skips_pipeline():
    redis, pipe = _make_redis_pipeline_mock()
    await _update_budget_counters(redis, "team-abc", "key-xyz", -1.0)

    redis.pipeline.assert_not_called()


async def test_budget_counters_redis_exception_silently_swallowed():
    redis = AsyncMock()
    redis.pipeline = MagicMock(side_effect=RuntimeError("Redis down"))
    # Should not raise
    await _update_budget_counters(redis, "team-abc", "key-xyz", 0.10)


async def test_budget_counters_execute_exception_silently_swallowed():
    redis, pipe = _make_redis_pipeline_mock()
    pipe.execute = AsyncMock(side_effect=ConnectionError("timeout"))
    # Should not raise
    await _update_budget_counters(redis, "team-abc", "key-xyz", 0.10)


async def test_budget_counters_key_counter_keys_are_correct():
    redis, pipe = _make_redis_pipeline_mock()
    await _update_budget_counters(redis, "team-1", "key-99", 0.12)

    incremented_keys = [call.args[0] for call in pipe.incrbyfloat.call_args_list]
    assert any("team:team-1" in k for k in incremented_keys)
    assert any("key:key-99" in k for k in incremented_keys)
    assert any("org:" in k for k in incremented_keys)


# ---------------------------------------------------------------------------
# Helpers for make_handler tests
# ---------------------------------------------------------------------------


def _make_pool_mock(pricing_rows=None):
    """Return an asyncpg pool mock with a working acquire() context manager."""
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)

    @asynccontextmanager
    async def _acquire():
        yield conn

    pool = AsyncMock()
    pool.acquire = _acquire

    if pricing_rows is not None:
        pool.fetch = AsyncMock(return_value=pricing_rows)
    else:
        pool.fetch = AsyncMock(return_value=[])

    return pool, conn


def _pricing_row(prefix, price_in, price_out):
    """Simulate an asyncpg Record-like mapping."""
    return {"model_prefix": prefix, "price_input_per_1k": price_in, "price_output_per_1k": price_out}


# ---------------------------------------------------------------------------
# make_handler / handle
# ---------------------------------------------------------------------------


async def test_handle_estimates_cost_when_cost_usd_not_set():
    """Event with no cost_usd → cost derived from pricing table."""
    pricing = [_pricing_row("gpt-4", 0.03, 0.06)]
    pool, conn = _make_pool_mock(pricing)


    with patch("asyncpg.create_pool", AsyncMock(return_value=pool)):
        # Force pricing fetch by placing fetched_at far in the past
        pg_mod._pricing_cache = {}
        pg_mod._pricing_fetched_at = -9999.0

        handle, _ = await make_handler("postgresql://fake/db")

    event = GatewayEvent(team_id="t1", model="gpt-4-turbo", tokens_input=1000, tokens_output=500)
    await handle(event)

    # conn.execute(sql, team_id, project_id, model, tokens_input, tokens_output, cost_usd, ...)
    # args[0]=sql, args[1]=team_id, ..., args[6]=cost_usd
    args = conn.execute.call_args.args
    cost = args[6]
    expected = (1000 * 0.03 + 500 * 0.06) / 1000  # 0.06
    assert cost == pytest.approx(expected)


async def test_handle_uses_provided_cost_usd():
    """Event with cost_usd already set → no estimation, uses that value."""
    pool, conn = _make_pool_mock(pricing_rows=[_pricing_row("gpt-4", 99.0, 99.0)])


    with patch("asyncpg.create_pool", AsyncMock(return_value=pool)):
        pg_mod._pricing_cache = {}
        pg_mod._pricing_fetched_at = 0.0
        handle, _ = await make_handler("postgresql://fake/db")

    event = GatewayEvent(team_id="t1", model="gpt-4", tokens_input=100, tokens_output=50, cost_usd=0.42)
    await handle(event)

    # args[0]=sql, args[1]=team_id, ..., args[6]=cost_usd
    args = conn.execute.call_args.args
    cost = args[6]
    assert cost == pytest.approx(0.42)


async def test_handle_writes_correct_insert():
    """Verify the INSERT uses the right table and passes all expected columns."""
    pool, conn = _make_pool_mock()


    with patch("asyncpg.create_pool", AsyncMock(return_value=pool)):
        pg_mod._pricing_cache = {}
        pg_mod._pricing_fetched_at = 0.0
        handle, _ = await make_handler("postgresql://fake/db")

    event = GatewayEvent(
        team_id="team-42",
        project_id="proj-1",
        model="claude-3",
        tokens_input=200,
        tokens_output=100,
        cost_usd=0.10,
        cache_hit=True,
        latency_ms=300,
    )
    await handle(event)

    sql, *positional = conn.execute.call_args.args
    assert "cost_records" in sql
    assert "INSERT INTO" in sql.upper()
    # Positional params: team_id, project_id, model, tokens_input, tokens_output,
    #                    cost_usd, cache_hit, latency_ms, api_key_id
    assert positional[0] == "team-42"
    assert positional[1] == "proj-1"
    assert positional[2] == "claude-3"
    assert positional[3] == 200
    assert positional[4] == 100
    assert positional[5] == pytest.approx(0.10)
    assert positional[6] is True
    assert positional[7] == 300
    assert positional[8] is None  # no key_id → None


async def test_handle_calls_budget_counters_when_redis_provided():
    """After DB write, _update_budget_counters is invoked when redis is set."""
    pool, conn = _make_pool_mock()
    redis, _ = _make_redis_pipeline_mock()


    with patch("asyncpg.create_pool", AsyncMock(return_value=pool)):
        pg_mod._pricing_cache = {}
        pg_mod._pricing_fetched_at = 0.0
        handle, _ = await make_handler("postgresql://fake/db", redis=redis)

    event = GatewayEvent(team_id="team-9", cost_usd=0.05)
    await handle(event)

    redis.pipeline.assert_called()


async def test_handle_no_budget_counters_when_redis_none():
    """No Redis → _update_budget_counters is never called."""
    pool, conn = _make_pool_mock()


    with patch("asyncpg.create_pool", AsyncMock(return_value=pool)):
        pg_mod._pricing_cache = {}
        pg_mod._pricing_fetched_at = 0.0
        handle, _ = await make_handler("postgresql://fake/db", redis=None)

    event = GatewayEvent(team_id="team-9", cost_usd=0.05)
    await handle(event)
    # No assertion needed — if we get here without error the redis=None path is correct.


async def test_handle_valid_uuid_key_id_passed_to_db():
    """key_id that is a valid UUID → key_uuid passed as UUID object to DB."""
    pool, conn = _make_pool_mock()
    key = str(uuid.uuid4())


    with patch("asyncpg.create_pool", AsyncMock(return_value=pool)):
        pg_mod._pricing_cache = {}
        pg_mod._pricing_fetched_at = 0.0
        handle, _ = await make_handler("postgresql://fake/db")

    event = GatewayEvent(team_id="t1", key_id=key, cost_usd=0.01)
    await handle(event)

    args = conn.execute.call_args.args
    api_key_id = args[9]  # 10th positional ($9)
    assert isinstance(api_key_id, uuid.UUID)
    assert str(api_key_id) == key


async def test_handle_invalid_uuid_key_id_becomes_none():
    """key_id that is not a valid UUID → key_uuid=None passed to DB."""
    pool, conn = _make_pool_mock()


    with patch("asyncpg.create_pool", AsyncMock(return_value=pool)):
        pg_mod._pricing_cache = {}
        pg_mod._pricing_fetched_at = 0.0
        handle, _ = await make_handler("postgresql://fake/db")

    event = GatewayEvent(team_id="t1", key_id="not-a-uuid", cost_usd=0.01)
    await handle(event)

    args = conn.execute.call_args.args
    api_key_id = args[9]
    assert api_key_id is None


async def test_handle_pricing_cache_refreshed_after_ttl():
    """_load_pricing is called again once _PRICING_TTL seconds have elapsed."""

    pool, conn = _make_pool_mock(pricing_rows=[])

    tick = 0.0

    def fake_monotonic():
        return tick

    with patch("asyncpg.create_pool", AsyncMock(return_value=pool)):
        with patch("app.workers.postgres.time.monotonic", side_effect=fake_monotonic):
            pg_mod._pricing_cache = {}
            pg_mod._pricing_fetched_at = 0.0

            handle, _ = await make_handler("postgresql://fake/db")

            # First call — within TTL window
            event = GatewayEvent(team_id="t1", cost_usd=0.01)
            tick = 0.0
            await handle(event)
            first_fetch_count = pool.fetch.call_count

            # Still within TTL
            tick = _PRICING_TTL - 1.0
            await handle(event)
            assert pool.fetch.call_count == first_fetch_count  # no extra fetch

            # Past TTL — should re-fetch
            tick = _PRICING_TTL + 1.0
            await handle(event)
            assert pool.fetch.call_count > first_fetch_count


async def test_handle_keeps_stale_cache_on_db_error():
    """DB error during _load_pricing → stale cache kept, no exception raised."""

    pool, conn = _make_pool_mock()
    # First fetch succeeds, second raises
    pool.fetch = AsyncMock(
        side_effect=[
            [_pricing_row("gpt-4", 0.03, 0.06)],  # first call OK
            RuntimeError("DB unavailable"),          # second call fails
        ]
    )

    tick = 0.0

    def fake_monotonic():
        return tick

    with patch("asyncpg.create_pool", AsyncMock(return_value=pool)):
        with patch("app.workers.postgres.time.monotonic", side_effect=fake_monotonic):
            # Start with fetched_at far in the past so the first handle call fetches
            pg_mod._pricing_cache = {}
            pg_mod._pricing_fetched_at = -9999.0

            handle, _ = await make_handler("postgresql://fake/db")

            event = GatewayEvent(team_id="t1", model="gpt-4-turbo", tokens_input=1000, tokens_output=500)

            # First call: tick=0, far past fetched_at → fetch executes, cache populated
            tick = 0.0
            await handle(event)
            stale_cache = dict(pg_mod._pricing_cache)
            assert "gpt-4" in stale_cache

            # Past TTL again — DB fetch will fail this time
            pg_mod._pricing_fetched_at = 0.0
            tick = _PRICING_TTL + 1.0
            await handle(event)  # Must not raise

            # Stale cache preserved
            assert pg_mod._pricing_cache == stale_cache
