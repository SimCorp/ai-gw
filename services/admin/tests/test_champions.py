from unittest.mock import AsyncMock, MagicMock, patch

import pytest


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


# ---------------------------------------------------------------------------
# Wave 2: asks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_ask_inserts_row(client, mock_session):
    insert_result = MagicMock()
    insert_result.scalar_one.return_value = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    mock_session.execute.return_value = insert_result

    resp = await client.post(
        "/champions/asks",
        json={
            "title": "Need RAG help",
            "description": "Looking for guidance",
            "created_by": "00000000-0000-0000-0000-000000000001",
            "tags": ["rag"],
        },
    )
    assert resp.status_code == 201
    assert resp.json()["id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    args, _ = mock_session.execute.await_args
    assert "INSERT INTO champion_asks" in str(args[0])
    assert "'open'" in str(args[0])


@pytest.mark.asyncio
async def test_claim_ask_success(client, mock_session):
    result = MagicMock()
    result.rowcount = 1
    mock_session.execute.return_value = result

    resp = await client.post(
        "/champions/asks/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/claim",
        json={"champion_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert resp.status_code == 200
    args, _ = mock_session.execute.await_args
    sql = str(args[0])
    assert "UPDATE champion_asks" in sql
    assert "status = 'claimed'" in sql
    assert "status = 'open'" in sql


@pytest.mark.asyncio
async def test_claim_ask_conflict_when_already_claimed(client, mock_session):
    result = MagicMock()
    result.rowcount = 0
    mock_session.execute.return_value = result

    resp = await client.post(
        "/champions/asks/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/claim",
        json={"champion_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_resolve_ask_sets_pending_with_7_day_deadline(client, mock_session):
    result = MagicMock()
    result.rowcount = 1
    mock_session.execute.return_value = result

    resp = await client.post(
        "/champions/asks/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/resolve",
        json={"champion_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert resp.status_code == 200
    args, _ = mock_session.execute.await_args
    sql = str(args[0])
    assert "resolved_pending" in sql
    assert "INTERVAL '7 days'" in sql
    assert "claimed_by" in sql


@pytest.mark.asyncio
async def test_confirm_ask_by_asker_grants_points(client, mock_session):
    select_result = MagicMock()
    select_result.mappings.return_value.one_or_none.return_value = {
        "status": "resolved_pending",
        "created_by": "00000000-0000-0000-0000-000000000099",
        "claimed_by": "00000000-0000-0000-0000-000000000001",
    }
    update_result = MagicMock()
    mock_session.execute.side_effect = [select_result, update_result]

    with patch("app.routers.champions.grant_points", new=AsyncMock()) as gp:
        resp = await client.post(
            "/champions/asks/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/confirm",
            json={"asker_id": "00000000-0000-0000-0000-000000000099"},
        )
    assert resp.status_code == 200
    gp.assert_awaited_once()
    kw = gp.await_args.kwargs
    assert kw["delta"] == 200
    assert kw["reason"] == "champion_ask_resolved"
    assert kw["engineer_id"] == "00000000-0000-0000-0000-000000000001"


@pytest.mark.asyncio
async def test_confirm_ask_not_by_asker_returns_403(client, mock_session):
    select_result = MagicMock()
    select_result.mappings.return_value.one_or_none.return_value = {
        "status": "resolved_pending",
        "created_by": "00000000-0000-0000-0000-000000000099",
        "claimed_by": "00000000-0000-0000-0000-000000000001",
    }
    mock_session.execute.return_value = select_result

    resp = await client.post(
        "/champions/asks/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/confirm",
        json={"asker_id": "00000000-0000-0000-0000-000000000077"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_confirm_ask_wrong_status_returns_409(client, mock_session):
    select_result = MagicMock()
    select_result.mappings.return_value.one_or_none.return_value = {
        "status": "open",
        "created_by": "00000000-0000-0000-0000-000000000099",
        "claimed_by": None,
    }
    mock_session.execute.return_value = select_result

    resp = await client.post(
        "/champions/asks/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/confirm",
        json={"asker_id": "00000000-0000-0000-0000-000000000099"},
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Wave 2: upvotes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upvote_insert_grants_and_increments(client, mock_session):
    select_existing = MagicMock()
    select_existing.scalar_one_or_none.return_value = None  # no existing upvote
    insert_result = MagicMock()
    update_result = MagicMock()
    update_result.mappings.return_value.one.return_value = {
        "upvotes": 7,
        "champion_id": "00000000-0000-0000-0000-000000000001",
    }
    mock_session.execute.side_effect = [select_existing, insert_result, update_result]

    with patch("app.routers.champions.grant_points", new=AsyncMock()) as gp:
        resp = await client.post(
            "/champions/content/11111111-1111-1111-1111-111111111111/upvote",
            json={"developer_id": "00000000-0000-0000-0000-000000000055"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"upvoted": True, "upvotes": 7}
    gp.assert_awaited_once()
    kw = gp.await_args.kwargs
    assert kw["delta"] == 5
    assert kw["reason"] == "champion_upvote"
    assert kw["engineer_id"] == "00000000-0000-0000-0000-000000000001"


@pytest.mark.asyncio
async def test_upvote_toggle_off_no_grant(client, mock_session):
    select_existing = MagicMock()
    select_existing.scalar_one_or_none.return_value = 1  # row exists
    delete_result = MagicMock()
    update_result = MagicMock()
    update_result.scalar_one.return_value = 3
    mock_session.execute.side_effect = [select_existing, delete_result, update_result]

    with patch("app.routers.champions.grant_points", new=AsyncMock()) as gp:
        resp = await client.post(
            "/champions/content/11111111-1111-1111-1111-111111111111/upvote",
            json={"developer_id": "00000000-0000-0000-0000-000000000055"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"upvoted": False, "upvotes": 3}
    gp.assert_not_awaited()


# ---------------------------------------------------------------------------
# Wave 2: flags
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_flag_inserts_and_increments(client, mock_session):
    insert_result = MagicMock()
    insert_result.scalar_one.return_value = "ffffffff-ffff-ffff-ffff-ffffffffffff"
    update_result = MagicMock()
    mock_session.execute.side_effect = [insert_result, update_result]

    resp = await client.post(
        "/champions/content/11111111-1111-1111-1111-111111111111/flag",
        json={"developer_id": "00000000-0000-0000-0000-000000000055", "reason": "spam"},
    )
    assert resp.status_code == 201
    assert resp.json()["id"] == "ffffffff-ffff-ffff-ffff-ffffffffffff"
    # second call increments flag_count
    second_sql = str(mock_session.execute.await_args_list[1].args[0])
    assert "flag_count = flag_count + 1" in second_sql
