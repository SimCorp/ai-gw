import pytest
from unittest.mock import AsyncMock, MagicMock


def _approved_target(scan_types=None):
    return {
        "id": "dddddddd-0000-0000-0000-000000000001",
        "node_id": "aaaaaaaa-0000-0000-0000-000000000001",
        "status": "approved",
        "allowed_scan_types": scan_types or ["ai", "api", "network"],
        "url": "http://myapp.simcorp.internal",
        "openapi_spec_url": None,
    }


def _quota(daily_limit=3, max_tier="quick"):
    return {"daily_limit": daily_limit, "allow_external_targets": False, "max_tier": max_tier}


def _mock_execute(*return_values):
    """Returns a mock session where execute() returns each value in sequence."""
    session = AsyncMock()
    side_effects = []
    for v in return_values:
        result = MagicMock()
        result.mappings.return_value.first.return_value = v
        result.mappings.return_value.all.return_value = [v] if v else []
        side_effects.append(result)
    session.execute = AsyncMock(side_effect=side_effects)
    session.commit = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_submit_job_success(client, mock_redis):
    from app.db import get_session
    from app.main import app

    target = _approved_target()
    quota_row = {"scanner_quota": _quota()}
    job_row = {"id": "job-uuid-123"}

    mock_sess = _mock_execute(target, quota_row, {"n": 0}, job_row)
    app.dependency_overrides[get_session] = lambda: (x for x in [mock_sess])

    async def override():
        yield mock_sess
    app.dependency_overrides[get_session] = override

    async with client as c:
        resp = await c.post("/jobs", json={
            "target_id": "dddddddd-0000-0000-0000-000000000001",
            "tier": "quick",
        }, headers={"Authorization": "Bearer test-token"})

    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "queued"
    assert "job_id" in data


@pytest.mark.asyncio
async def test_submit_job_blocked_by_kill_switch(client, mock_redis):
    mock_redis.get = AsyncMock(return_value="1")
    async with client as c:
        resp = await c.post("/jobs", json={
            "target_id": "dddddddd-0000-0000-0000-000000000001",
            "tier": "quick",
        }, headers={"Authorization": "Bearer test-token"})
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_submit_job_target_not_approved(client, mock_redis):
    from app.db import get_session
    from app.main import app
    mock_sess = _mock_execute(None)
    async def override():
        yield mock_sess
    app.dependency_overrides[get_session] = override
    mock_redis.get = AsyncMock(return_value=None)
    async with client as c:
        resp = await c.post("/jobs", json={
            "target_id": "dddddddd-0000-0000-0000-000000000001",
            "tier": "quick",
        }, headers={"Authorization": "Bearer test-token"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_submit_job_quota_exceeded(client, mock_redis):
    from app.db import get_session
    from app.main import app
    target = _approved_target()
    quota_row = {"scanner_quota": _quota(daily_limit=3)}
    concurrent_row = {"n": 0}
    mock_sess = _mock_execute(target, quota_row, concurrent_row)
    async def override():
        yield mock_sess
    app.dependency_overrides[get_session] = override
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.incr = AsyncMock(return_value=4)  # over limit
    async with client as c:
        resp = await c.post("/jobs", json={
            "target_id": "dddddddd-0000-0000-0000-000000000001",
            "tier": "quick",
        }, headers={"Authorization": "Bearer test-token"})
    assert resp.status_code == 429
    assert "X-Quota-Resets-At" in resp.headers


@pytest.mark.asyncio
async def test_submit_job_tier_not_allowed(client, mock_redis):
    from app.db import get_session
    from app.main import app
    target = _approved_target()
    quota_row = {"scanner_quota": _quota(max_tier="quick")}
    concurrent_row = {"n": 0}
    mock_sess = _mock_execute(target, quota_row, concurrent_row)
    async def override():
        yield mock_sess
    app.dependency_overrides[get_session] = override
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.incr = AsyncMock(return_value=1)
    async with client as c:
        resp = await c.post("/jobs", json={
            "target_id": "dddddddd-0000-0000-0000-000000000001",
            "tier": "deep",
        }, headers={"Authorization": "Bearer test-token"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_internal_endpoint_rejects_bad_secret():
    from app.main import app
    from httpx import AsyncClient, ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/internal/jobs/some-id/complete",
            json={"status": "completed"},
            headers={"Authorization": "Bearer wrong-secret"},
        )
    assert resp.status_code == 403
