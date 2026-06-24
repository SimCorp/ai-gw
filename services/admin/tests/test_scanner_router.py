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

    resp = await client.post(
        "/scanner/targets",
        json={
            "url": "https://external.example.com/api",
            "label": "External",
            "node_id": "aaaaaaaa-0000-0000-0000-000000000001",
            "created_by": "bbbbbbbb-0000-0000-0000-000000000001",
        },
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_register_target_success(client, mock_session):
    from unittest.mock import MagicMock

    row = {
        "id": "tttttttt-0000-0000-0000-000000000001",
        "node_id": "aaaaaaaa-0000-0000-0000-000000000001",
        "url": "http://myapp.simcorp.internal",
        "label": "My App",
        "status": "pending_approval",
        "allowed_scan_types": ["ai", "api", "network"],
        "openapi_spec_url": None,
        "created_by": "bbbbbbbb-0000-0000-0000-000000000001",
        "created_at": "2026-01-01T00:00:00+00:00",
        "approved_at": None,
        "approved_by": None,
        "notes": None,
    }
    result = MagicMock()
    result.mappings.return_value.first.return_value = row
    mock_session.execute.return_value = result

    resp = await client.post(
        "/scanner/targets",
        json={
            "url": "http://myapp.simcorp.internal",
            "label": "My App",
            "node_id": "aaaaaaaa-0000-0000-0000-000000000001",
            "created_by": "bbbbbbbb-0000-0000-0000-000000000001",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "pending_approval"


@pytest.mark.asyncio
async def test_approve_target_success(client, mock_session):
    from unittest.mock import AsyncMock, MagicMock

    found = MagicMock()
    found.mappings.return_value.first.return_value = {"id": "tttttttt-0000-0000-0000-000000000001"}
    updated = MagicMock()
    mock_session.execute = AsyncMock(side_effect=[found, updated])

    resp = await client.post(
        "/scanner/targets/tttttttt-0000-0000-0000-000000000001/approve",
        json={"allowed_scan_types": ["ai", "api"]},
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "approved"}


@pytest.mark.asyncio
async def test_revoke_target_success(client, mock_session):
    from unittest.mock import MagicMock

    result = MagicMock()
    result.mappings.return_value.first.return_value = {"id": "tttttttt-0000-0000-0000-000000000001"}
    mock_session.execute.return_value = result

    resp = await client.post(
        "/scanner/targets/tttttttt-0000-0000-0000-000000000001/revoke",
        json={},
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "revoked"}


@pytest.mark.asyncio
async def test_revoke_target_not_found(client, mock_session):
    from unittest.mock import MagicMock

    result = MagicMock()
    result.mappings.return_value.first.return_value = None
    mock_session.execute.return_value = result

    resp = await client.post("/scanner/targets/nonexistent/revoke", json={})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_quotas(client, mock_session):
    from unittest.mock import MagicMock

    quota_row = {
        "id": "aaaaaaaa-0000-0000-0000-000000000001",
        "name": "Platform",
        "scanner_quota": {"daily_limit": 3, "max_tier": "quick", "allow_external_targets": False},
    }
    result = MagicMock()
    result.mappings.return_value.all.return_value = [quota_row]
    mock_session.execute.return_value = result

    resp = await client.get("/scanner/quotas")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Platform"


@pytest.mark.asyncio
async def test_update_quota_success(client, mock_session):
    from unittest.mock import MagicMock

    result = MagicMock()
    result.mappings.return_value.first.return_value = {
        "scanner_quota": {"daily_limit": 5, "max_tier": "quick", "allow_external_targets": False}
    }
    mock_session.execute.return_value = result

    resp = await client.patch(
        "/scanner/quotas/aaaaaaaa-0000-0000-0000-000000000001",
        json={"daily_limit": 5},
    )
    assert resp.status_code == 200
    assert resp.json()["scanner_quota"]["daily_limit"] == 5


@pytest.mark.asyncio
async def test_update_quota_empty_body(client):
    resp = await client.patch(
        "/scanner/quotas/aaaaaaaa-0000-0000-0000-000000000001",
        json={},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_kill_switch_enable(client):
    from app.main import app

    resp = await client.post("/scanner/kill-switch?enabled=true")
    assert resp.status_code == 200
    assert resp.json() == {"scanner_disabled": True}
    app.state.redis.set.assert_called_once_with("scanner:disabled", "1")


@pytest.mark.asyncio
async def test_kill_switch_disable(client):
    from app.main import app

    resp = await client.post("/scanner/kill-switch?enabled=false")
    assert resp.status_code == 200
    assert resp.json() == {"scanner_disabled": False}
    app.state.redis.delete.assert_called_once_with("scanner:disabled")


@pytest.mark.asyncio
async def test_list_scan_jobs(client, mock_session):
    from unittest.mock import MagicMock

    job = {
        "id": "jjjjjjjj-0000-0000-0000-000000000001",
        "status": "running",
        "tier": "quick",
        "node_id": "aaaaaaaa-0000-0000-0000-000000000001",
        "queued_at": "2026-01-01T00:00:00+00:00",
    }
    result = MagicMock()
    result.mappings.return_value.all.return_value = [job]
    mock_session.execute.return_value = result

    resp = await client.get("/scanner/jobs")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "jjjjjjjj-0000-0000-0000-000000000001"


@pytest.mark.asyncio
async def test_admin_cancel_scan_job(client):
    resp = await client.delete("/scanner/jobs/jjjjjjjj-0000-0000-0000-000000000001")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
