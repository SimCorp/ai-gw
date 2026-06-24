from unittest.mock import AsyncMock, MagicMock

import pytest


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
        resp = await c.post(
            "/jobs",
            json={
                "target_id": "dddddddd-0000-0000-0000-000000000001",
                "tier": "quick",
            },
            headers={"Authorization": "Bearer test-token"},
        )

    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "queued"
    assert "job_id" in data


@pytest.mark.asyncio
async def test_submit_job_blocked_by_kill_switch(client, mock_redis):
    mock_redis.get = AsyncMock(return_value="1")
    async with client as c:
        resp = await c.post(
            "/jobs",
            json={
                "target_id": "dddddddd-0000-0000-0000-000000000001",
                "tier": "quick",
            },
            headers={"Authorization": "Bearer test-token"},
        )
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
        resp = await c.post(
            "/jobs",
            json={
                "target_id": "dddddddd-0000-0000-0000-000000000001",
                "tier": "quick",
            },
            headers={"Authorization": "Bearer test-token"},
        )
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
        resp = await c.post(
            "/jobs",
            json={
                "target_id": "dddddddd-0000-0000-0000-000000000001",
                "tier": "quick",
            },
            headers={"Authorization": "Bearer test-token"},
        )
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
        resp = await c.post(
            "/jobs",
            json={
                "target_id": "dddddddd-0000-0000-0000-000000000001",
                "tier": "deep",
            },
            headers={"Authorization": "Bearer test-token"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_disallowed_scan_type_does_not_burn_quota(client, mock_redis):
    """A submission rejected for a disallowed scan type (403) must NOT increment
    the Redis daily-quota counter — scan-type validation runs BEFORE _check_quota.
    """
    from app.db import get_session
    from app.main import app

    # Target only permits 'ai' scans; caller requests 'network' → disallowed.
    target = _approved_target(scan_types=["ai"])
    mock_sess = _mock_execute(target)  # only _load_target is reached

    async def override():
        yield mock_sess

    app.dependency_overrides[get_session] = override
    mock_redis.get = AsyncMock(return_value=None)  # kill switch off
    mock_redis.incr = AsyncMock(return_value=1)

    async with client as c:
        resp = await c.post(
            "/jobs",
            json={
                "target_id": "dddddddd-0000-0000-0000-000000000001",
                "scan_types": ["network"],
                "tier": "quick",
            },
            headers={"Authorization": "Bearer test-token"},
        )

    assert resp.status_code == 403
    # The daily-quota counter (incremented inside _check_quota) must never run.
    mock_redis.incr.assert_not_called()


@pytest.mark.asyncio
async def test_internal_endpoint_rejects_bad_secret():
    from app.main import app
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/internal/jobs/some-id/complete",
            json={"status": "completed"},
            headers={"Authorization": "Bearer wrong-secret"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_jobs(client, mock_redis):
    from app.db import get_session
    from app.main import app

    job = {
        "id": "jjjjjjjj-0000-0000-0000-000000000001",
        "status": "queued",
        "tier": "quick",
        "node_id": "aaaaaaaa-0000-0000-0000-000000000001",
        "queued_at": "2026-01-01T00:00:00+00:00",
    }
    mock_sess = _mock_execute(job)

    async def override():
        yield mock_sess

    app.dependency_overrides[get_session] = override
    async with client as c:
        resp = await c.get("/jobs", headers={"Authorization": "Bearer test-token"})
    assert resp.status_code == 200
    assert resp.json()[0]["id"] == "jjjjjjjj-0000-0000-0000-000000000001"


@pytest.mark.asyncio
async def test_get_job_found(client, mock_redis):
    from app.db import get_session
    from app.main import app

    job = {
        "id": "jjjjjjjj-0000-0000-0000-000000000001",
        "status": "completed",
        "tier": "quick",
        "node_id": "aaaaaaaa-0000-0000-0000-000000000001",
    }
    mock_sess = _mock_execute(job)

    async def override():
        yield mock_sess

    app.dependency_overrides[get_session] = override
    async with client as c:
        resp = await c.get(
            "/jobs/jjjjjjjj-0000-0000-0000-000000000001",
            headers={"Authorization": "Bearer test-token"},
        )
    assert resp.status_code == 200
    assert resp.json()["id"] == "jjjjjjjj-0000-0000-0000-000000000001"


@pytest.mark.asyncio
async def test_get_job_not_found(client, mock_redis):
    from app.db import get_session
    from app.main import app

    mock_sess = _mock_execute(None)

    async def override():
        yield mock_sess

    app.dependency_overrides[get_session] = override
    async with client as c:
        resp = await c.get(
            "/jobs/nonexistent",
            headers={"Authorization": "Bearer test-token"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cancel_job_success(client, mock_redis):
    from app.db import get_session
    from app.main import app

    mock_sess = _mock_execute({"id": "jjjjjjjj-0000-0000-0000-000000000001"})

    async def override():
        yield mock_sess

    app.dependency_overrides[get_session] = override
    async with client as c:
        resp = await c.delete(
            "/jobs/jjjjjjjj-0000-0000-0000-000000000001",
            headers={"Authorization": "Bearer test-token"},
        )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_cancel_job_not_found(client, mock_redis):
    from app.db import get_session
    from app.main import app

    mock_sess = _mock_execute(None)

    async def override():
        yield mock_sess

    app.dependency_overrides[get_session] = override
    async with client as c:
        resp = await c.delete(
            "/jobs/nonexistent",
            headers={"Authorization": "Bearer test-token"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_results_json(client, mock_redis):
    from app.db import get_session
    from app.main import app

    job = {"id": "jjjjjjjj-0000-0000-0000-000000000001", "status": "completed"}
    finding = {
        "id": "ffffffff-0000-0000-0000-000000000001",
        "job_id": "jjjjjjjj-0000-0000-0000-000000000001",
        "scanner": "nmap",
        "severity": "info",
        "category": "open_port",
        "title": "Open port 22",
        "description": "SSH port open",
        "evidence": {},
        "remediation": None,
    }
    total = {"n": 1}
    mock_sess = _mock_execute(job, finding, total)

    async def override():
        yield mock_sess

    app.dependency_overrides[get_session] = override
    async with client as c:
        resp = await c.get(
            "/jobs/jjjjjjjj-0000-0000-0000-000000000001/results",
            headers={"Authorization": "Bearer test-token"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["findings"][0]["title"] == "Open port 22"


@pytest.mark.asyncio
async def test_get_results_sarif(client, mock_redis):
    from app.db import get_session
    from app.main import app

    job = {"id": "jjjjjjjj-0000-0000-0000-000000000001", "status": "completed"}
    finding = {
        "id": "ffffffff-0000-0000-0000-000000000001",
        "job_id": "jjjjjjjj-0000-0000-0000-000000000001",
        "scanner": "nmap",
        "severity": "info",
        "category": "open_port",
        "title": "Open port 22",
        "description": "SSH port open",
        "evidence": {},
        "remediation": None,
    }
    mock_sess = _mock_execute(job, finding)  # 2 calls only — SARIF skips total count

    async def override():
        yield mock_sess

    app.dependency_overrides[get_session] = override
    async with client as c:
        resp = await c.get(
            "/jobs/jjjjjjjj-0000-0000-0000-000000000001/results?format=sarif",
            headers={"Authorization": "Bearer test-token"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == "2.1.0"
    assert len(data["runs"][0]["results"]) == 1


@pytest.mark.asyncio
async def test_submit_job_concurrent_limit(client, mock_redis):
    """429 when 2 jobs already running; Redis INCR must NOT be called."""
    from app.db import get_session
    from app.main import app

    target = _approved_target()
    quota_row = {"scanner_quota": _quota()}
    concurrent_row = {"n": 2}  # at the limit → 429 before Redis INCR
    mock_sess = _mock_execute(target, quota_row, concurrent_row)

    async def override():
        yield mock_sess

    app.dependency_overrides[get_session] = override
    mock_redis.get = AsyncMock(return_value=None)

    async with client as c:
        resp = await c.post(
            "/jobs",
            json={"target_id": "dddddddd-0000-0000-0000-000000000001", "tier": "quick"},
            headers={"Authorization": "Bearer test-token"},
        )
    assert resp.status_code == 429
    mock_redis.incr.assert_not_called()
