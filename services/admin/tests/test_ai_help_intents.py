"""Tests for Wave 3 AiHelp intent classification and structured card responses."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Pure classifier unit tests
# ---------------------------------------------------------------------------

def test_classify_show_champions_simple():
    from app.llm.champion_intents import classify

    res = classify("show me champions")
    assert res["intent"] == "show_champions"


def test_classify_show_champions_with_topic():
    from app.llm.champion_intents import classify

    res = classify("champions for rag")
    assert res["intent"] == "show_champions"
    assert res["query"] == "rag"


def test_classify_find_content():
    from app.llm.champion_intents import classify

    res = classify("find content on caching")
    assert res["intent"] == "find_content"
    assert res["query"] == "caching"


def test_classify_book_champion():
    from app.llm.champion_intents import classify

    res = classify("book alice")
    assert res["intent"] == "book_champion"
    assert res["query"] == "alice"


def test_classify_book_with_session_phrase():
    from app.llm.champion_intents import classify

    res = classify("book a session with bob")
    assert res["intent"] == "book_champion"
    assert res["query"] == "bob"


def test_classify_none():
    from app.llm.champion_intents import classify

    res = classify("how do I bypass the cache?")
    assert res["intent"] == "none"


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------

@pytest.fixture
async def portal_client_with_session():
    from app.db import get_session
    from app.main import app
    from app.routers.dev_auth import _get_current_developer

    fake_session = AsyncMock()
    fake_session.execute = AsyncMock()

    async def fake_developer():
        return {"id": "dev-1", "email": "dev@example.com"}

    async def override_session():
        yield fake_session

    app.dependency_overrides[_get_current_developer] = fake_developer
    app.dependency_overrides[get_session] = override_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, fake_session

    app.dependency_overrides.clear()


def _mappings_result(rows: list[dict]):
    """Build a fake SQLAlchemy result whose .mappings().all() returns rows."""
    result = MagicMock()
    mappings = MagicMock()
    mappings.all.return_value = rows
    mappings.first.return_value = rows[0] if rows else None
    result.mappings.return_value = mappings
    return result


@pytest.mark.asyncio
async def test_show_champions_returns_champions_payload(portal_client_with_session):
    client, fake_session = portal_client_with_session

    rows = [
        {
            "developer_id": "00000000-0000-0000-0000-000000000001",
            "bio": "Caching champion",
            "focus_areas": ["caching", "redis"],
        }
    ]
    fake_session.execute.return_value = _mappings_result(rows)

    with patch("app.routers.ai_help._call_llm", AsyncMock()) as llm:
        resp = await client.post(
            "/ai-help/chat/portal",
            json={"messages": [{"role": "user", "content": "show me champions"}]},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["type"] == "champions"
    assert "reply" in data
    assert len(data["champions"]) == 1
    assert data["champions"][0]["focus_areas"] == ["caching", "redis"]
    llm.assert_not_awaited()


@pytest.mark.asyncio
async def test_find_content_returns_content_cards(portal_client_with_session):
    client, _fake_session = portal_client_with_session

    chunks = [
        {
            "id": "c1",
            "title": "RAG patterns",
            "content": "Retrieval augmented generation overview..." * 5,
            "source_url": "https://docs/rag",
        }
    ]
    with patch(
        "app.routers.ai_help.retrieve_champion_chunks",
        AsyncMock(return_value=chunks),
    ) as rc, patch("app.routers.ai_help._call_llm", AsyncMock()) as llm:
        resp = await client.post(
            "/ai-help/chat/portal",
            json={"messages": [{"role": "user", "content": "find content on rag"}]},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["type"] == "content"
    assert "reply" in data
    assert len(data["items"]) == 1
    assert data["items"][0]["title"] == "RAG patterns"
    assert data["items"][0]["source_url"] == "https://docs/rag"
    rc.assert_awaited_once()
    llm.assert_not_awaited()


@pytest.mark.asyncio
async def test_book_unresolved_falls_through_to_rag(portal_client_with_session):
    """`book alice` with no matching champion → RAG path executes (text or ask_cta)."""
    client, fake_session = portal_client_with_session

    # SQL resolution returns no rows.
    fake_session.execute.return_value = _mappings_result([])

    # No chunks → RAG returns ask_cta (no LLM).
    with patch(
        "app.routers.ai_help.retrieve_champion_chunks",
        AsyncMock(return_value=[]),
    ), patch("app.routers.ai_help._call_llm", AsyncMock()) as llm:
        resp = await client.post(
            "/ai-help/chat/portal",
            json={"messages": [{"role": "user", "content": "book alice"}]},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["type"] in ("text", "ask_cta")
    assert "reply" in data
    llm.assert_not_awaited()
