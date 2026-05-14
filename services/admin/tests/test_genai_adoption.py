"""Tests for the /genai-adoption endpoints."""

from unittest.mock import AsyncMock, MagicMock
import pytest


def _make_mapping(data: dict):
    """Return a mock that behaves like a SQLAlchemy RowMapping."""
    m = MagicMock()
    m.__getitem__ = lambda self, key: data[key]
    m.keys = lambda: data.keys()
    return m


def _scalar_result(value):
    result = AsyncMock()
    result.scalar = MagicMock(return_value=value)
    return result


def _mappings_result(rows: list[dict]):
    mapping_list = [_make_mapping(r) for r in rows]

    one_mock = MagicMock()
    one_mock.__getitem__ = lambda self, key: rows[0][key]

    mappings = MagicMock()
    mappings.all = MagicMock(return_value=mapping_list)
    mappings.one = MagicMock(return_value=one_mock)

    result = MagicMock()
    result.mappings = MagicMock(return_value=mappings)
    result.scalar = MagicMock(return_value=None)
    return result


# ── Adoption ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_adoption_summary(client, mock_session):
    call_count = 0

    async def side_effect(stmt, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Total developers count
            r = MagicMock()
            r.scalar = MagicMock(return_value=100)
            return r
        # Active devs CTE
        return _mappings_result([{
            "active_users": 62, "rare": 10, "occasional": 22, "regular": 30,
        }])

    mock_session.execute = AsyncMock(side_effect=side_effect)

    resp = await client.get("/genai-adoption/adoption/summary?period_days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert data["active_users"] == 62
    assert data["total_licensed_developers"] == 100
    assert data["adoption_rate_pct"] == 62.0
    assert data["frequency_buckets"]["regular"] == 30


@pytest.mark.asyncio
async def test_adoption_by_team(client, mock_session):
    mock_session.execute = AsyncMock(return_value=_mappings_result([
        {
            "team_id": "00000000-0000-0000-0000-000000000001",
            "team_name": "Backend",
            "licensed_count": 20,
            "active_users": 15,
            "rare": 2, "occasional": 5, "regular": 8,
        }
    ]))

    resp = await client.get("/genai-adoption/adoption/by-team?period_days=30")
    assert resp.status_code == 200
    teams = resp.json()
    assert len(teams) == 1
    assert teams[0]["team_name"] == "Backend"
    assert teams[0]["adoption_rate_pct"] == 75.0


@pytest.mark.asyncio
async def test_adoption_trend(client, mock_session):
    from datetime import datetime, timezone
    week = datetime(2026, 5, 5, tzinfo=timezone.utc)

    row = MagicMock()
    row.__getitem__ = lambda self, key: {"week_start": week, "active_users": 55}[key]

    mappings = MagicMock()
    mappings.all = MagicMock(return_value=[row])
    result = MagicMock()
    result.mappings = MagicMock(return_value=mappings)
    mock_session.execute = AsyncMock(return_value=result)

    resp = await client.get("/genai-adoption/adoption/trend?period_days=90")
    assert resp.status_code == 200
    trend = resp.json()
    assert trend[0]["active_users"] == 55
    assert "week_start" in trend[0]


# ── Productivity ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_productivity_summary(client, mock_session):
    mock_session.execute = AsyncMock(return_value=_mappings_result([
        {
            "cohort": "high",
            "avg_quality_score": 3.9,
            "avg_inter_request_s": 145,
            "avg_turn_count": 6.2,
            "avg_tool_invocations": 4.1,
            "session_count": 8420,
        },
        {
            "cohort": "low",
            "avg_quality_score": 2.8,
            "avg_inter_request_s": 62,
            "avg_turn_count": 4.1,
            "avg_tool_invocations": 1.2,
            "session_count": 3210,
        },
    ]))

    resp = await client.get("/genai-adoption/productivity/summary?period_days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert data["high_adoption"]["avg_quality_score"] == 3.9
    assert data["low_adoption"]["session_count"] == 3210


@pytest.mark.asyncio
async def test_productivity_by_team(client, mock_session):
    mock_session.execute = AsyncMock(return_value=_mappings_result([
        {
            "team_id": "00000000-0000-0000-0000-000000000001",
            "team_name": "Platform",
            "avg_quality_score": 4.1,
            "avg_inter_request_s": 160,
            "avg_turn_count": 7.0,
            "session_count": 500,
        }
    ]))

    resp = await client.get("/genai-adoption/productivity/by-team?period_days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["avg_quality_score"] == 4.1


# ── Quality ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_quality_summary(client, mock_session):
    mock_session.execute = AsyncMock(return_value=_mappings_result([
        {
            "cohort": "high",
            "avg_error_rate_pct": 4.1,
            "avg_retry_rate_pct": 6.3,
            "cache_hit_rate_pct": 38.0,
        },
        {
            "cohort": "low",
            "avg_error_rate_pct": 9.8,
            "avg_retry_rate_pct": 14.2,
            "cache_hit_rate_pct": 12.0,
        },
    ]))

    resp = await client.get("/genai-adoption/quality/summary?period_days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert data["high_adoption"]["avg_error_rate_pct"] == 4.1
    assert data["low_adoption"]["cache_hit_rate_pct"] == 12.0


@pytest.mark.asyncio
async def test_quality_by_team(client, mock_session):
    mock_session.execute = AsyncMock(return_value=_mappings_result([
        {
            "team_id": "00000000-0000-0000-0000-000000000001",
            "team_name": "Risk",
            "avg_error_rate_pct": 12.5,
            "avg_retry_rate_pct": 8.0,
            "cache_hit_rate_pct": 20.0,
            "session_count": 200,
        }
    ]))

    resp = await client.get("/genai-adoption/quality/by-team?period_days=30")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["high_error_flag"] is True
    assert data[0]["team_name"] == "Risk"


@pytest.mark.asyncio
async def test_period_validation(client, mock_session):
    """period_days outside [7, 365] should return 422."""
    resp = await client.get("/genai-adoption/adoption/summary?period_days=3")
    assert resp.status_code == 422

    resp = await client.get("/genai-adoption/adoption/summary?period_days=400")
    assert resp.status_code == 422


# ── AI Insights ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_insights_returns_structured_data(client, mock_session):
    """Insights endpoint returns summary/highlights/recommendations/risks when LLM responds."""
    from unittest.mock import patch, AsyncMock as AM
    import json

    # All DB calls return empty data so _gather_metrics completes without error
    mock_session.execute = AsyncMock(return_value=_mappings_result([
        {"active_days": 15, "active_users": 0, "rare": 0, "occasional": 0, "regular": 0,
         "cohort": "high", "avg_quality_score": 4.0, "avg_inter_request_s": 120,
         "avg_turn_count": 6.0, "session_count": 100,
         "avg_error_rate_pct": 3.0, "avg_retry_rate_pct": 5.0, "cache_hit_rate_pct": 35.0,
         "team_name": "Backend", "licensed_count": 20, "active_users": 15,
         "avg_quality": 4.0, "error_rate_pct": 3.0}
    ]))

    ai_reply = json.dumps({
        "summary": "Adoption is healthy at 75%.",
        "highlights": ["75% adoption rate", "High cohort quality score 4.0"],
        "recommendations": ["Onboard low-adoption teams"],
        "risks": ["Backend team error rate elevated"],
    })

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={
        "choices": [{"message": {"content": ai_reply}}]
    })
    mock_response.raise_for_status = MagicMock()

    with patch("app.routers.genai_adoption.httpx.AsyncClient") as mock_client_cls:
        mock_http = AM()
        mock_http.__aenter__ = AM(return_value=mock_http)
        mock_http.__aexit__ = AM(return_value=False)
        mock_http.post = AM(return_value=mock_response)
        mock_client_cls.return_value = mock_http

        resp = await client.get("/genai-adoption/insights?period_days=30")

    assert resp.status_code == 200
    data = resp.json()
    assert data["insights"]["summary"] == "Adoption is healthy at 75%."
    assert len(data["insights"]["highlights"]) == 2
    assert len(data["insights"]["recommendations"]) == 1
    assert len(data["insights"]["risks"]) == 1


@pytest.mark.asyncio
async def test_insights_graceful_degradation(client, mock_session):
    """Insights endpoint returns a stub when the LLM call fails."""
    from unittest.mock import patch, AsyncMock as AM

    mock_session.execute = AsyncMock(return_value=_mappings_result([
        {"active_days": 0, "active_users": 0, "rare": 0, "occasional": 0, "regular": 0,
         "cohort": "low", "avg_quality_score": None, "avg_inter_request_s": None,
         "avg_turn_count": None, "session_count": 0,
         "avg_error_rate_pct": None, "avg_retry_rate_pct": None, "cache_hit_rate_pct": None,
         "team_name": "Backend", "licensed_count": 5, "active_users": 0,
         "avg_quality": None, "error_rate_pct": None}
    ]))

    with patch("app.routers.genai_adoption.httpx.AsyncClient") as mock_client_cls:
        mock_http = AM()
        mock_http.__aenter__ = AM(return_value=mock_http)
        mock_http.__aexit__ = AM(return_value=False)
        mock_http.post = AM(side_effect=Exception("connection refused"))
        mock_client_cls.return_value = mock_http

        resp = await client.get("/genai-adoption/insights?period_days=30")

    assert resp.status_code == 200
    data = resp.json()
    assert "unavailable" in data["insights"]["summary"].lower()
