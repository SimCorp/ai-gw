"""
Tests for cost anomaly detection — pure detect_spikes function (Step 1)
and _check_once worker (Step 2).
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.workers.cost_anomaly import _check_once, detect_spikes

# ---------------------------------------------------------------------------
# Step 1: pure detect_spikes
# ---------------------------------------------------------------------------


def test_detect_spikes_fires_above_multiplier_and_floor():
    rows = [{"node_id": "abc", "team_name": "Alpha", "today_spend": 6.0, "rolling_avg": 1.0}]
    spikes = detect_spikes(rows, multiplier=3.0, floor=1.0)
    assert len(spikes) == 1
    assert spikes[0].node_id == "abc"
    assert spikes[0].team_name == "Alpha"
    assert spikes[0].daily_spend == 6.0
    assert spikes[0].rolling_avg == 1.0
    assert spikes[0].multiplier == 6.0  # round(6.0 / 1.0, 2)


def test_detect_spikes_does_not_fire_below_multiplier():
    # today_spend = 2.5, rolling_avg = 1.0 → ratio 2.5 < 3.0
    rows = [{"node_id": "abc", "team_name": "Alpha", "today_spend": 2.5, "rolling_avg": 1.0}]
    spikes = detect_spikes(rows, multiplier=3.0, floor=1.0)
    assert spikes == []


def test_detect_spikes_does_not_fire_below_floor():
    # today_spend = 0.5, rolling_avg = 0.1 → ratio 5.0 >= 3.0 but below floor $1.0
    rows = [{"node_id": "abc", "team_name": "Alpha", "today_spend": 0.5, "rolling_avg": 0.1}]
    spikes = detect_spikes(rows, multiplier=3.0, floor=1.0)
    assert spikes == []


def test_detect_spikes_skips_none_rolling_avg():
    rows = [{"node_id": "abc", "team_name": "Alpha", "today_spend": 10.0, "rolling_avg": None}]
    spikes = detect_spikes(rows, multiplier=3.0, floor=1.0)
    assert spikes == []


def test_detect_spikes_skips_zero_rolling_avg():
    rows = [{"node_id": "abc", "team_name": "Alpha", "today_spend": 10.0, "rolling_avg": 0.0}]
    spikes = detect_spikes(rows, multiplier=3.0, floor=1.0)
    assert spikes == []


def test_detect_spikes_skips_zero_rolling_avg_int():
    rows = [{"node_id": "abc", "team_name": "Alpha", "today_spend": 10.0, "rolling_avg": 0}]
    spikes = detect_spikes(rows, multiplier=3.0, floor=1.0)
    assert spikes == []


def test_detect_spikes_multiple_nodes_mixed():
    rows = [
        # fires: 9.0 >= 3.0 * 2.0 and >= 1.0
        {"node_id": "node-1", "team_name": "TeamA", "today_spend": 9.0, "rolling_avg": 2.0},
        # does not fire: 5.0 < 3.0 * 2.0
        {"node_id": "node-2", "team_name": "TeamB", "today_spend": 5.0, "rolling_avg": 2.0},
        # does not fire: below floor
        {"node_id": "node-3", "team_name": "TeamC", "today_spend": 0.5, "rolling_avg": 0.1},
        # fires: 12.0 >= 3.0 * 3.0 and >= 1.0
        {"node_id": "node-4", "team_name": "TeamD", "today_spend": 12.0, "rolling_avg": 3.0},
    ]
    spikes = detect_spikes(rows, multiplier=3.0, floor=1.0)
    assert len(spikes) == 2
    node_ids = {s.node_id for s in spikes}
    assert node_ids == {"node-1", "node-4"}


def test_detect_spikes_multiplier_rounded_two_dp():
    rows = [{"node_id": "x", "team_name": "T", "today_spend": 10.0, "rolling_avg": 3.0}]
    spikes = detect_spikes(rows, multiplier=3.0, floor=1.0)
    assert len(spikes) == 1
    assert spikes[0].multiplier == round(10.0 / 3.0, 2)


# ---------------------------------------------------------------------------
# Step 2: _check_once worker
# ---------------------------------------------------------------------------


def _make_pool(rows):
    """Return a mock asyncpg pool where .fetch() returns the given rows."""
    row_mocks = []
    for r in rows:
        rm = MagicMock()
        rm.__getitem__ = lambda self, key, _r=r: _r[key]
        row_mocks.append(rm)

    pool = MagicMock()
    pool.fetch = AsyncMock(side_effect=_make_fetch_side_effect(row_mocks))
    pool.execute = AsyncMock()
    pool.fetchrow = AsyncMock(return_value=None)  # org_settings: not configured → defaults
    return pool


def _make_fetch_side_effect(spike_rows):
    """First call = org_settings fetch (returns []), second call = spike SQL."""
    call_count = [0]

    async def side_effect(query, *args, **kwargs):
        call_count[0] += 1
        if "org_settings" in query:
            return []
        return spike_rows

    return side_effect


@pytest.mark.asyncio
async def test_check_once_inserts_audit_row_for_spike():
    """A spiking row should write an audit_log INSERT with budget_spike_alert."""
    rows = [
        {
            "node_id": "node-abc",
            "team_name": "Alpha",
            "today_spend": 9.0,
            "rolling_avg": 2.0,
        }
    ]
    pool = _make_pool(rows)
    redis = MagicMock()
    redis.exists = AsyncMock(return_value=0)  # not yet sent
    redis.setex = AsyncMock()

    await _check_once(pool, redis)

    # execute should have been called with an INSERT into audit_log
    assert pool.execute.called
    call_args = pool.execute.call_args
    # call signature: pool.execute(query, actor, action, resource_type, resource_id, details)
    args = call_args[0]
    query = args[0]
    assert "audit_log" in query
    assert args[2] == "budget_spike_alert"  # action bound param $2

    # The details JSON param should encode the right fields
    details_json = args[5]  # 6th positional param (after query + 4 others)
    details = json.loads(details_json)
    assert details["team_name"] == "Alpha"
    assert details["daily_spend"] == 9.0
    assert details["rolling_avg"] == 2.0
    assert "multiplier" in details

    # Redis dedup flag should have been set
    redis.setex.assert_called_once()
    setex_key = redis.setex.call_args[0][0]
    assert setex_key.startswith("cost_spike_sent:node-abc:")


@pytest.mark.asyncio
async def test_check_once_skips_insert_when_dedup_flag_set():
    """When Redis already has a dedup flag for this spike, no insert should occur."""
    rows = [
        {
            "node_id": "node-abc",
            "team_name": "Alpha",
            "today_spend": 9.0,
            "rolling_avg": 2.0,
        }
    ]
    pool = _make_pool(rows)
    redis = MagicMock()
    redis.exists = AsyncMock(return_value=1)  # already sent today
    redis.setex = AsyncMock()

    await _check_once(pool, redis)

    pool.execute.assert_not_called()
    redis.setex.assert_not_called()


@pytest.mark.asyncio
async def test_check_once_no_spikes_no_inserts():
    """When no rows spike, nothing should be written."""
    rows = [
        {
            "node_id": "node-xyz",
            "team_name": "Beta",
            "today_spend": 1.0,
            "rolling_avg": 2.0,  # below multiplier threshold
        }
    ]
    pool = _make_pool(rows)
    redis = MagicMock()
    redis.exists = AsyncMock(return_value=0)
    redis.setex = AsyncMock()

    await _check_once(pool, redis)

    pool.execute.assert_not_called()
    redis.setex.assert_not_called()


@pytest.mark.asyncio
async def test_check_once_uses_org_settings_multiplier():
    """When org_settings has a custom spike_multiplier, it should be used."""
    # With multiplier=10.0, a 9x spike should NOT fire
    org_row = MagicMock()
    org_row.__getitem__ = lambda self, key: json.dumps({"spike_multiplier": 10.0})

    spike_row_mock = MagicMock()
    spike_row_mock.__getitem__ = (
        lambda self, key, _r={"node_id": "n1", "team_name": "T", "today_spend": 9.0, "rolling_avg": 1.0}: (
            _r[key]
        )
    )

    call_count = [0]

    async def fetch_side_effect(query, *args, **kwargs):
        call_count[0] += 1
        if "org_settings" in query:
            return [org_row]
        return [spike_row_mock]

    pool = MagicMock()
    pool.fetch = AsyncMock(side_effect=fetch_side_effect)
    pool.execute = AsyncMock()
    pool.fetchrow = AsyncMock(return_value=None)

    redis = MagicMock()
    redis.exists = AsyncMock(return_value=0)
    redis.setex = AsyncMock()

    await _check_once(pool, redis)

    # 9.0 / 1.0 = 9x < 10x multiplier → should NOT fire
    pool.execute.assert_not_called()
