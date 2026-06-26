"""Tests for the /ingest endpoint and content validation.

LIBRARIAN_SERVICE_TOKEN defaults to "" so _check_ingest_token fails-open;
no token header is needed in these tests.
"""

import uuid
from unittest.mock import AsyncMock, patch

import app.main as main
import pytest


@pytest.mark.asyncio
async def test_ingest_successful(client):
    """Valid payload: embedding created, row inserted, UUID returned."""
    fake_embed = [0.1] * 768

    with patch.object(main, "_embed", AsyncMock(return_value=fake_embed)):
        resp = await client.post(
            "/ingest",
            json={"title": "Test Doc", "content": "Some content about embeddings."},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    uuid.UUID(data["id"])  # Raises ValueError if not a valid UUID

    # Embedding was stored in Redis under exactly lib:embed:<doc_id>
    main._redis.set.assert_awaited_once()
    assert main._redis.set.call_args[0][0] == f"lib:embed:{data['id']}"

    # Row inserted via pool
    main._pool.acquire.assert_called()


@pytest.mark.asyncio
async def test_ingest_embedding_failure_is_graceful(client):
    """When the embedding model is unavailable, the document is still persisted."""
    with patch.object(main, "_embed", AsyncMock(side_effect=Exception("LLM down"))):
        resp = await client.post(
            "/ingest",
            json={"title": "Fallback Doc", "content": "Content that cannot be embedded."},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data

    # Redis.set was NOT called (no embedding to store)
    main._redis.set.assert_not_called()

    # The DB row was still inserted
    main._pool.acquire.assert_called()


@pytest.mark.asyncio
async def test_ingest_content_too_long_returns_422(client):
    """Content exceeding 50 000 chars is rejected before any DB call."""
    with patch.object(main, "_embed", AsyncMock()) as mock_embed:
        resp = await client.post(
            "/ingest",
            json={"title": "Big Doc", "content": "x" * 50_001},
        )

    assert resp.status_code == 422
    assert "50000" in resp.text or "maximum" in resp.text.lower()
    # No embedding attempted, no DB call
    mock_embed.assert_not_called()
    main._pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_ingest_invalid_source_url_returns_422(client):
    """source_url that doesn't start with http:// or https:// is rejected."""
    with patch.object(main, "_embed", AsyncMock()) as mock_embed:
        resp = await client.post(
            "/ingest",
            json={
                "title": "Doc",
                "content": "Some valid content.",
                "source_url": "ftp://example.com/file.txt",
            },
        )

    assert resp.status_code == 422
    mock_embed.assert_not_called()


@pytest.mark.asyncio
async def test_ingest_valid_source_url_accepted(client):
    """http:// and https:// URLs are accepted by validation."""
    fake_embed = [0.2] * 768

    with patch.object(main, "_embed", AsyncMock(return_value=fake_embed)):
        resp = await client.post(
            "/ingest",
            json={
                "title": "Web Doc",
                "content": "Content from a website.",
                "source_url": "https://docs.example.com/page",
            },
        )

    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_ingest_with_topic_and_tags(client):
    """Topic and tags are accepted and passed through."""
    fake_embed = [0.3] * 768

    with patch.object(main, "_embed", AsyncMock(return_value=fake_embed)):
        resp = await client.post(
            "/ingest",
            json={
                "title": "Tagged Doc",
                "content": "Content with metadata.",
                "topic": "finance",
                "tags": ["quarterly", "risk"],
            },
        )

    assert resp.status_code == 201
    assert "id" in resp.json()
