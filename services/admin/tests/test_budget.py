"""Tests for budget helper functions and /teams/{id}/budget,
/keys/{id}/budget, /org/budget, and /budget/status endpoints."""

import uuid
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Pure helper function tests
# ---------------------------------------------------------------------------
from app.routers.budget import _remaining, _safe_pct


def test_safe_pct_normal():
    assert _safe_pct(50, 100) == pytest.approx(0.5)


def test_safe_pct_zero_limit():
    assert _safe_pct(0, 0) is None


def test_safe_pct_none_limit():
    assert _safe_pct(50, None) is None


def test_remaining_normal():
    assert _remaining(50, 100) == pytest.approx(50.0)


def test_remaining_clamped_at_zero():
    assert _remaining(150, 100) == pytest.approx(0.0)


def test_remaining_none_limit():
    assert _remaining(50, None) is None


# ---------------------------------------------------------------------------
# Helpers for mocking execute chains
# ---------------------------------------------------------------------------


def _make_key_orm(team_id, revoked=False, budget=None):
    from unittest.mock import MagicMock

    k = MagicMock()
    k.id = uuid.uuid4()
    k.team_id = team_id
    k.name = "test key"
    k.created_at = None
    k.revoked_at = MagicMock() if revoked else None
    k.monthly_budget_usd = budget
    return k


def _scalar_result(value):
    result = MagicMock()
    result.scalar_one.return_value = value
    return result


def _mappings_all(rows):
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    return result


def _row_dict(**kwargs):
    """Return a MagicMock that acts as a mapping with the given keys."""
    row = MagicMock()
    row.__getitem__ = lambda self, k: kwargs[k]
    row.get = lambda k, default=None: kwargs.get(k, default)
    # Support dict(row) — mappings() returns objects that can be iterated
    row.keys = lambda: kwargs.keys()
    return row


# ---------------------------------------------------------------------------
# /teams/{id}/budget tests REMOVED — the per-team budget routes were superseded
# by GET/PUT /nodes/{id}/budget (organization_nodes) in migration 0025.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# GET /keys/{id}/budget
# ---------------------------------------------------------------------------


async def test_get_key_budget_found(client, mock_session):
    team_id = uuid.uuid4()
    key = _make_key_orm(team_id)
    mock_session.get.return_value = key
    mock_session.execute.return_value = _scalar_result(0.0)

    resp = await client.get(f"/keys/{key.id}/budget")

    assert resp.status_code == 200
    body = resp.json()
    assert body["key_id"] == str(key.id)


async def test_get_key_budget_revoked_returns_404(client, mock_session):
    team_id = uuid.uuid4()
    key = _make_key_orm(team_id, revoked=True)
    mock_session.get.return_value = key

    resp = await client.get(f"/keys/{key.id}/budget")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /keys/{id}/budget
# ---------------------------------------------------------------------------


async def test_set_key_budget_returns_200(client, mock_session):
    team_id = uuid.uuid4()
    key = _make_key_orm(team_id)
    mock_session.get.return_value = key
    mock_session.execute.return_value = _scalar_result(0.0)

    resp = await client.put(
        f"/keys/{key.id}/budget",
        json={"monthly_budget_usd": 50.0},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["key_id"] == str(key.id)


# ---------------------------------------------------------------------------
# GET /org/budget
# ---------------------------------------------------------------------------


async def test_get_org_budget_returns_200(client, mock_session):
    # _read_org_settings iterates over rows from execute; _org_monthly_spend also calls execute.
    # Use side_effect to return different mock results per call.

    org_settings_rows = [
        MagicMock(key="monthly_budget_usd", value="1000.0"),
        MagicMock(key="budget_alert_pct", value="0.8"),
        MagicMock(key="budget_action", value="alert"),
    ]

    org_settings_result = MagicMock()
    # _read_org_settings iterates the result directly (not via mappings)
    org_settings_result.__iter__ = lambda self: iter(org_settings_rows)

    spend_result = _scalar_result(0.0)

    mock_session.execute.side_effect = [org_settings_result, spend_result]

    resp = await client.get("/org/budget")

    assert resp.status_code == 200
    body = resp.json()
    assert "monthly_budget_usd" in body
    assert "current_spend_usd" in body


# ---------------------------------------------------------------------------
# PUT /org/budget
# ---------------------------------------------------------------------------


async def test_set_org_budget_returns_200(client, mock_session):
    # 3 upsert executes + 1 audit add + 1 spend query
    upsert_result = MagicMock()
    spend_result = _scalar_result(0.0)

    # side_effect list: first 3 calls return upsert_result, 4th returns spend
    mock_session.execute.side_effect = [upsert_result, upsert_result, upsert_result, spend_result]

    resp = await client.put(
        "/org/budget",
        json={"monthly_budget_usd": 10000.0, "budget_alert_pct": 0.85, "budget_action": "block"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["monthly_budget_usd"] == 10000.0


# ---------------------------------------------------------------------------
# GET /budget/status
# ---------------------------------------------------------------------------


async def test_budget_status_returns_200(client, mock_session):
    org_settings_rows = [
        MagicMock(key="monthly_budget_usd", value="0"),
        MagicMock(key="budget_alert_pct", value="0.8"),
        MagicMock(key="budget_action", value="alert"),
    ]
    org_settings_result = MagicMock()
    org_settings_result.__iter__ = lambda self: iter(org_settings_rows)

    spend_result = _scalar_result(0.0)

    # Teams list with budget+spend columns
    teams_row = MagicMock()
    teams_row.__getitem__ = lambda self, k: {
        "id": uuid.uuid4(),
        "name": "Engineering",
        "slug": "engineering",
        "monthly_budget_usd": None,
        "budget_alert_pct": 0.8,
        "budget_action": "alert",
        "spend": 0.0,
    }[k]
    teams_result = MagicMock()
    teams_result.mappings.return_value.all.return_value = [teams_row]

    mock_session.execute.side_effect = [
        org_settings_result,  # _read_org_settings
        spend_result,  # _org_monthly_spend
        teams_result,  # teams + spend join
    ]

    resp = await client.get("/budget/status")

    assert resp.status_code == 200
    body = resp.json()
    assert "org" in body
    assert "teams" in body
    assert "team_count" in body
