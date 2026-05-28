import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_list_directory_returns_active_champions(client, mock_session):
    rows = [
        {"developer_id": "00000000-0000-0000-0000-000000000001", "bio": "rag", "focus_areas": ["rag"],
         "office_hours_text": None, "active": True, "nominated_at": None}
    ]
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    mock_session.execute.return_value = result

    resp = await client.get("/champions")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["focus_areas"] == ["rag"]


@pytest.mark.asyncio
async def test_profile_returns_404_when_missing(client, mock_session):
    result = MagicMock()
    result.mappings.return_value.one_or_none.return_value = None
    mock_session.execute.return_value = result

    resp = await client.get("/champions/00000000-0000-0000-0000-000000000999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_submit_content_runs_full_pipeline(client, mock_session):
    insert_result = MagicMock()
    insert_result.scalar_one.return_value = "22222222-2222-2222-2222-222222222222"
    mock_session.execute.return_value = insert_result

    fake_metadata = {
        "title": "Agentic basics",
        "summary": "intro",
        "focus_areas": ["agentic"],
        "tags": ["intro"],
        "difficulty": "beginner",
    }
    with patch("app.routers.champions.classify_content", new=AsyncMock(return_value=fake_metadata)) as cc, \
         patch("app.routers.champions.ingest_to_librarian", new=AsyncMock(return_value="lib-item-1")) as ing, \
         patch("app.routers.champions.grant_points", new=AsyncMock()) as gp:
        resp = await client.post(
            "/champions/content",
            json={"type": "article", "text": "Once upon a time...", "champion_id": "00000000-0000-0000-0000-000000000001"},
        )

    assert resp.status_code == 201, resp.text
    cc.assert_awaited_once()
    ing.assert_awaited_once()
    gp.assert_awaited_once()
    gp_kwargs = gp.await_args.kwargs
    assert gp_kwargs["delta"] == 50
    assert gp_kwargs["reason"] == "champion_content"
    body = resp.json()
    assert body["title"] == "Agentic basics"


@pytest.mark.asyncio
async def test_submit_content_requires_url_or_text(client):
    resp = await client.post(
        "/champions/content",
        json={"type": "link", "champion_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert resp.status_code in (400, 422)


@pytest.mark.asyncio
async def test_submit_content_continues_on_league_failure(client, mock_session):
    insert_result = MagicMock()
    insert_result.scalar_one.return_value = "22222222-2222-2222-2222-222222222222"
    mock_session.execute.return_value = insert_result

    fake_metadata = {"title": "x", "summary": "y", "focus_areas": [], "tags": [], "difficulty": "unknown"}
    with patch("app.routers.champions.classify_content", new=AsyncMock(return_value=fake_metadata)), \
         patch("app.routers.champions.ingest_to_librarian", new=AsyncMock(return_value=None)), \
         patch("app.routers.champions.grant_points", new=AsyncMock(side_effect=RuntimeError("boom"))):
        resp = await client.post(
            "/champions/content",
            json={"type": "article", "text": "hello", "champion_id": "00000000-0000-0000-0000-000000000001"},
        )
    assert resp.status_code == 201  # league failure swallowed


@pytest.mark.asyncio
async def test_feed_returns_recent_contributions(client, mock_session):
    rows = [
        {"id": "11111111-1111-1111-1111-111111111111", "champion_id": "00000000-0000-0000-0000-000000000001",
         "type": "article", "submitted_at": None,
         "auto_metadata": {"title": "x", "summary": "y", "focus_areas": [], "tags": []},
         "upvotes": 0, "views": 0}
    ]
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    mock_session.execute.return_value = result

    resp = await client.get("/champions/content")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
