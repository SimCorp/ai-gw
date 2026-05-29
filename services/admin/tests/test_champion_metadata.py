import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from app.llm.champion_metadata import classify_content


@pytest.mark.asyncio
async def test_classify_returns_structured_dict():
    fake_llm_response = {
        "choices": [{"message": {"content": json.dumps({
            "title": "Building an agentic RAG",
            "summary": "Walkthrough of agentic RAG with tool-use",
            "focus_areas": ["agentic", "rag"],
            "tags": ["python", "anthropic"],
            "difficulty": "intermediate",
        })}}]
    }
    with patch("app.llm.champion_metadata.httpx.AsyncClient") as mock_client_cls:
        instance = AsyncMock()
        instance.__aenter__.return_value = instance
        instance.post.return_value = httpx.Response(200, json=fake_llm_response)
        mock_client_cls.return_value = instance

        result = await classify_content(text="how I built a rag agent...")

    assert result["title"] == "Building an agentic RAG"
    assert "agentic" in result["focus_areas"]
    assert result["difficulty"] == "intermediate"
    assert len(result["summary"]) <= 200


@pytest.mark.asyncio
async def test_classify_handles_malformed_json():
    fake_llm_response = {"choices": [{"message": {"content": "not json"}}]}
    with patch("app.llm.champion_metadata.httpx.AsyncClient") as mock_client_cls:
        instance = AsyncMock()
        instance.__aenter__.return_value = instance
        instance.post.return_value = httpx.Response(200, json=fake_llm_response)
        mock_client_cls.return_value = instance

        result = await classify_content(text="hello")

    assert result == {
        "title": "(untitled)",
        "summary": "",
        "focus_areas": [],
        "tags": [],
        "difficulty": "unknown",
    }


@pytest.mark.asyncio
async def test_classify_truncates_summary_over_200_chars():
    long_summary = "x" * 500
    fake_llm_response = {
        "choices": [{"message": {"content": json.dumps({
            "title": "T",
            "summary": long_summary,
            "focus_areas": [],
            "tags": [],
            "difficulty": "beginner",
        })}}]
    }
    with patch("app.llm.champion_metadata.httpx.AsyncClient") as mock_client_cls:
        instance = AsyncMock()
        instance.__aenter__.return_value = instance
        instance.post.return_value = httpx.Response(200, json=fake_llm_response)
        mock_client_cls.return_value = instance

        result = await classify_content(text="anything")

    assert len(result["summary"]) == 200


@pytest.mark.asyncio
async def test_classify_raises_on_litellm_5xx():
    with patch("app.llm.champion_metadata.httpx.AsyncClient") as mock_client_cls:
        instance = AsyncMock()
        instance.__aenter__.return_value = instance
        instance.post.return_value = httpx.Response(502, json={})
        mock_client_cls.return_value = instance

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await classify_content(text="anything")
        assert exc.value.status_code == 502
