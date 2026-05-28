"""Tests for /scanner endpoints."""

import pytest


@pytest.mark.asyncio
async def test_list_targets_empty(client, mock_session):
    from unittest.mock import MagicMock
    result = MagicMock()
    result.mappings.return_value.all.return_value = []
    mock_session.execute.return_value = result

    resp = await client.get("/scanner/targets")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_approve_target_not_found(client, mock_session):
    from unittest.mock import MagicMock
    result = MagicMock()
    result.mappings.return_value.first.return_value = None
    mock_session.execute.return_value = result

    resp = await client.post(
        "/scanner/targets/nonexistent/approve",
        json={"allowed_scan_types": ["ai"]},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_register_external_target_blocked(client, mock_session):
    """External target blocked when team has allow_external_targets=False."""
    from unittest.mock import MagicMock
    result = MagicMock()
    result.mappings.return_value.first.return_value = {
        "scanner_quota": {"daily_limit": 3, "allow_external_targets": False, "max_tier": "quick"}
    }
    mock_session.execute.return_value = result

    resp = await client.post("/scanner/targets", json={
        "url": "https://external.example.com/api",
        "label": "External",
        "team_id": "aaaaaaaa-0000-0000-0000-000000000001",
        "created_by": "bbbbbbbb-0000-0000-0000-000000000001",
    })
    assert resp.status_code == 403
