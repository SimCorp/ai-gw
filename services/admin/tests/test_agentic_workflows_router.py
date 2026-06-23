"""Tests for the agentic-workflows status router."""

import pytest
from app.config import settings


@pytest.mark.asyncio
async def test_runs_unconfigured_returns_empty(client, monkeypatch):
    """With no GitHub token, the endpoint degrades gracefully (no error)."""
    monkeypatch.setattr(settings, "github_token", "")

    resp = await client.get("/agentic-workflows/runs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is False
    assert body["runs"] == []
    assert body["summary"]["total"] == 0


@pytest.mark.asyncio
async def test_runs_filters_to_agentic_workflows_and_summarizes(client, monkeypatch):
    """Only simcorp-* workflow runs are returned; summary counts conclusions."""
    monkeypatch.setattr(settings, "github_token", "ghp_test")

    payload = {
        "workflow_runs": [
            {
                "id": 1,
                "name": "AI Code Review",
                "display_title": "Fix cache bug",
                "status": "completed",
                "conclusion": "success",
                "event": "pull_request",
                "head_branch": "feat/x",
                "run_number": 12,
                "created_at": "2026-06-23T08:00:00Z",
                "updated_at": "2026-06-23T08:05:00Z",
                "html_url": "https://github.com/SimCorp/ai-gw/actions/runs/1",
                "path": ".github/workflows/simcorp-pr-review.lock.yml",
            },
            {
                "id": 2,
                "name": "Security Scan",
                "display_title": "Scan",
                "status": "completed",
                "conclusion": "failure",
                "event": "pull_request",
                "head_branch": "feat/y",
                "run_number": 3,
                "created_at": "2026-06-23T07:00:00Z",
                "updated_at": "2026-06-23T07:02:00Z",
                "html_url": "https://github.com/SimCorp/ai-gw/actions/runs/2",
                "path": ".github/workflows/simcorp-security-scan.lock.yml",
            },
            {
                # Non-agentic workflow — must be filtered out.
                "id": 3,
                "name": "CI",
                "status": "completed",
                "conclusion": "success",
                "path": ".github/workflows/ci.yml",
            },
        ]
    }

    class _FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            return _FakeResp()

    monkeypatch.setattr(
        "app.routers.agentic_workflows.httpx.AsyncClient", lambda *a, **k: _FakeClient()
    )

    resp = await client.get("/agentic-workflows/runs?limit=10")
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is True
    # ci.yml filtered out; only the two simcorp-* runs remain.
    assert [r["id"] for r in body["runs"]] == [1, 2]
    assert body["runs"][0]["title"] == "Fix cache bug"
    assert body["summary"] == {"total": 2, "success": 1, "failure": 1, "other": 0}
