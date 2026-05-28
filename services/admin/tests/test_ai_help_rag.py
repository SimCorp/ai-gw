"""Tests for RAG-augmented /ai-help/chat/portal endpoint."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def portal_client():
    from app.main import app
    from app.routers.dev_auth import _get_current_developer

    async def fake_developer():
        return {"id": "dev-1", "email": "dev@example.com"}

    app.dependency_overrides[_get_current_developer] = fake_developer

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_high_similarity_returns_text_with_cited_sources(portal_client):
    chunks = [
        {
            "id": "abc-123",
            "title": "Using semantic cache",
            "content": "Set x-cache: bypass header to skip the cache for a request.",
            "source_url": "https://docs/cache",
            "score": 0.82,
        }
    ]
    rc_patch = patch("app.routers.ai_help.retrieve_champion_chunks", AsyncMock(return_value=chunks))
    llm_patch = patch(
        "app.routers.ai_help._call_llm",
        AsyncMock(return_value="Use x-cache: bypass."),
    )
    with rc_patch as rc, llm_patch as llm:
        resp = await portal_client.post(
            "/ai-help/chat/portal",
            json={"messages": [{"role": "user", "content": "how do I bypass the cache?"}]},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "text"
    assert data["content"] == "Use x-cache: bypass."
    assert data["reply"] == "Use x-cache: bypass."  # back-compat
    assert len(data["cited_sources"]) == 1
    cited = data["cited_sources"][0]
    assert cited["contribution_id"] == "abc-123"
    assert cited["title"] == "Using semantic cache"
    assert cited["source_url"] == "https://docs/cache"
    llm.assert_awaited_once()
    rc.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_chunks_returns_ask_cta_and_skips_llm(portal_client):
    with patch("app.routers.ai_help.retrieve_champion_chunks", AsyncMock(return_value=[])), \
         patch("app.routers.ai_help._call_llm", AsyncMock()) as llm:
        resp = await portal_client.post(
            "/ai-help/chat/portal",
            json={"messages": [{"role": "user", "content": "what is the meaning of life?"}]},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "ask_cta"
    assert "champion" in data["message"].lower()
    assert data["prefill"]["description"] == "what is the meaning of life?"
    assert data["prefill"]["title"] == "what is the meaning of life?"
    assert data["cited_sources"] == []
    llm.assert_not_awaited()


@pytest.mark.asyncio
async def test_all_below_threshold_returns_ask_cta(portal_client):
    """Chunks present but all below similarity threshold → fallback CTA."""
    chunks = [{"id": "x", "title": "Off-topic", "content": "Nope.", "score": 0.10}]
    with patch("app.routers.ai_help.retrieve_champion_chunks", AsyncMock(return_value=chunks)), \
         patch("app.routers.ai_help._call_llm", AsyncMock()) as llm:
        resp = await portal_client.post(
            "/ai-help/chat/portal",
            json={"messages": [{"role": "user", "content": "irrelevant question"}]},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "ask_cta"
    llm.assert_not_awaited()


@pytest.mark.asyncio
async def test_retrieve_called_with_champions_topic():
    """Confirm retrieve_champion_chunks queries librarian with topic=champions."""
    from app.llm import champion_rag

    captured = {}

    class FakeResp:
        status_code = 200

        def json(self):
            return {"results": [{"id": "1", "title": "T", "content": "C", "score": 0.9}]}

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            captured["url"] = url
            captured["params"] = params
            return FakeResp()

    with patch.object(champion_rag.httpx, "AsyncClient", FakeClient):
        results = await champion_rag.retrieve_champion_chunks("how to ship a feature", limit=5)

    assert captured["params"]["topic"] == "champions"
    assert captured["params"]["q"] == "how to ship a feature"
    assert captured["params"]["limit"] == 5
    assert captured["url"].endswith("/search")
    assert len(results) == 1
