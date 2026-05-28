import pytest
import httpx
from unittest.mock import AsyncMock, patch

from app.league_client import grant_points


@pytest.mark.asyncio
async def test_grant_points_posts_to_league():
    with patch("app.league_client.httpx.AsyncClient") as mock_client_cls:
        instance = AsyncMock()
        instance.__aenter__.return_value = instance
        instance.post.return_value = httpx.Response(201, json={"ok": True})
        mock_client_cls.return_value = instance

        await grant_points(
            engineer_id="00000000-0000-0000-0000-000000000001",
            delta=50,
            reason="champion_content",
            ref_id=None,
        )
        instance.post.assert_awaited_once()
        kwargs = instance.post.await_args.kwargs
        assert "X-Admin-Token" in kwargs["headers"]
        body = kwargs["json"]
        assert body["reason"] == "champion_content"
        assert body["delta"] == 50
        assert "ref_id" not in body  # omitted when None


@pytest.mark.asyncio
async def test_grant_points_includes_ref_id_when_provided():
    with patch("app.league_client.httpx.AsyncClient") as mock_client_cls:
        instance = AsyncMock()
        instance.__aenter__.return_value = instance
        instance.post.return_value = httpx.Response(201, json={"ok": True})
        mock_client_cls.return_value = instance

        await grant_points(
            engineer_id="00000000-0000-0000-0000-000000000001",
            delta=50,
            reason="champion_content",
            ref_id="11111111-1111-1111-1111-111111111111",
        )
        body = instance.post.await_args.kwargs["json"]
        assert body["ref_id"] == "11111111-1111-1111-1111-111111111111"


@pytest.mark.asyncio
async def test_grant_points_raises_on_non_201():
    with patch("app.league_client.httpx.AsyncClient") as mock_client_cls:
        instance = AsyncMock()
        instance.__aenter__.return_value = instance
        instance.post.return_value = httpx.Response(500, json={"detail": "boom"})
        mock_client_cls.return_value = instance

        with pytest.raises(RuntimeError):
            await grant_points(
                engineer_id="00000000-0000-0000-0000-000000000001",
                delta=50,
                reason="champion_content",
            )
