"""Tests for DAG compile-time security validation added in create_workflow_version."""
import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("DEV_BYPASS_AUTH", "true")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://placeholder/placeholder")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test")
os.environ.setdefault("OIDC_ISSUER", "http://localhost:5556")
os.environ.setdefault("OIDC_CLIENT_ID", "test")
os.environ.setdefault("OIDC_CLIENT_SECRET", "test")

@pytest.fixture
async def client():
    from unittest.mock import AsyncMock, MagicMock

    from app.auth import require_admin_auth
    from app.db import get_session
    from app.main import app

    session = AsyncMock()
    # Simulate workflow exists (latest_version=1) and version insert succeeds
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: 1,
                                                        scalar_one=lambda: 1))
    session.commit = AsyncMock()

    async def _override_session():
        yield session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_admin_auth] = lambda: {"actor": "test", "role": "admin"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


_WF_ID = str(uuid.uuid4())
_CREATOR = str(uuid.uuid4())


def _version_body(dag: dict) -> dict:
    return {"dag": dag, "created_by": _CREATOR}


def _linear_dag(n: int = 2) -> dict:
    nodes = [{"id": f"n{i}", "agent_slug": "echo-agent"} for i in range(1, n+1)]
    edges = [{"from": f"n{i}", "to": f"n{i+1}"} for i in range(1, n)]
    return {"entry_node": "n1", "nodes": nodes, "edges": edges}


@pytest.mark.asyncio
async def test_valid_dag_accepted(client):
    r = await client.post(f"/workflows/{_WF_ID}/versions", json=_version_body(_linear_dag(2)))
    assert r.status_code in (200, 201), r.text


@pytest.mark.asyncio
async def test_too_many_nodes_rejected(client):
    dag = _linear_dag(51)
    r = await client.post(f"/workflows/{_WF_ID}/versions", json=_version_body(dag))
    assert r.status_code == 422
    assert "maximum node count" in r.text


@pytest.mark.asyncio
async def test_loop_max_iterations_exceeded(client):
    dag = {
        "entry_node": "n1",
        "nodes": [{"id": "n1", "agent_slug": "echo-agent",
                   "loop": {"enabled": True, "max_iterations": 100}}],
        "edges": []
    }
    r = await client.post(f"/workflows/{_WF_ID}/versions", json=_version_body(dag))
    assert r.status_code == 422
    assert "max_iterations" in r.text


@pytest.mark.asyncio
async def test_invalid_edge_condition_rejected(client):
    dag = {
        "entry_node": "n1",
        "nodes": [{"id": "n1", "agent_slug": "a"}, {"id": "n2", "agent_slug": "b"}],
        "edges": [{"from": "n1", "to": "n2", "condition": "'; DROP TABLE workflows; --"}]
    }
    r = await client.post(f"/workflows/{_WF_ID}/versions", json=_version_body(dag))
    assert r.status_code == 422
    assert "condition" in r.text


@pytest.mark.asyncio
async def test_valid_condition_accepted(client):
    dag = {
        "entry_node": "n1",
        "nodes": [{"id": "n1", "agent_slug": "a"}, {"id": "n2", "agent_slug": "b"}],
        "edges": [{"from": "n1", "to": "n2", "condition": "outputs.status == 'success'"}]
    }
    r = await client.post(f"/workflows/{_WF_ID}/versions", json=_version_body(dag))
    assert r.status_code in (200, 201), r.text


@pytest.mark.asyncio
async def test_orphan_node_rejected(client):
    dag = {
        "entry_node": "n1",
        "nodes": [{"id": "n1", "agent_slug": "a"}, {"id": "orphan", "agent_slug": "b"}],
        "edges": []  # orphan has no path from entry_node
    }
    r = await client.post(f"/workflows/{_WF_ID}/versions", json=_version_body(dag))
    assert r.status_code == 422
    assert "orphan" in r.text or "Unreachable" in r.text


@pytest.mark.asyncio
async def test_invalid_image_format_rejected(client):
    dag = {
        "entry_node": "n1",
        "nodes": [{"id": "n1", "image": "malicious:latest; rm -rf /", "agent_slug": "x"}],
        "edges": []
    }
    r = await client.post(f"/workflows/{_WF_ID}/versions", json=_version_body(dag))
    assert r.status_code == 422
    assert "invalid image format" in r.text
