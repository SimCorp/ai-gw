from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_list_directory_returns_active_champions(client, mock_session):
    rows = [
        {
            "developer_id": "00000000-0000-0000-0000-000000000001",
            "bio": "rag",
            "focus_areas": ["rag"],
            "office_hours_text": None,
            "active": True,
            "nominated_at": None,
        }
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
    with (
        patch(
            "app.routers.champions.classify_content", new=AsyncMock(return_value=fake_metadata)
        ) as cc,
        patch(
            "app.routers.champions.ingest_to_librarian", new=AsyncMock(return_value="lib-item-1")
        ) as ing,
        patch("app.routers.champions.grant_points", new=AsyncMock()) as gp,
    ):
        resp = await client.post(
            "/champions/content",
            json={
                "type": "article",
                "text": "Once upon a time...",
                "champion_id": "00000000-0000-0000-0000-000000000001",
            },
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

    fake_metadata = {
        "title": "x",
        "summary": "y",
        "focus_areas": [],
        "tags": [],
        "difficulty": "unknown",
    }
    with (
        patch("app.routers.champions.classify_content", new=AsyncMock(return_value=fake_metadata)),
        patch("app.routers.champions.ingest_to_librarian", new=AsyncMock(return_value=None)),
        patch(
            "app.routers.champions.grant_points", new=AsyncMock(side_effect=RuntimeError("boom"))
        ),
    ):
        resp = await client.post(
            "/champions/content",
            json={
                "type": "article",
                "text": "hello",
                "champion_id": "00000000-0000-0000-0000-000000000001",
            },
        )
    assert resp.status_code == 201  # league failure swallowed


@pytest.mark.asyncio
async def test_feed_returns_recent_contributions(client, mock_session):
    rows = [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "champion_id": "00000000-0000-0000-0000-000000000001",
            "type": "article",
            "submitted_at": None,
            "auto_metadata": {"title": "x", "summary": "y", "focus_areas": [], "tags": []},
            "upvotes": 0,
            "views": 0,
        }
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


# ---------------------------------------------------------------------------
# Wave 3: bookings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_booking_inserts_row(client, mock_session):
    insert_result = MagicMock()
    insert_result.scalar_one.return_value = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    mock_session.execute.return_value = insert_result

    resp = await client.post(
        "/champions/00000000-0000-0000-0000-000000000001/book",
        json={
            "requested_by": "00000000-0000-0000-0000-000000000055",
            "slot_text": "Tue 14:00",
            "topic": "RAG",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["booking_id"] == "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    sql = str(mock_session.execute.await_args.args[0])
    assert "INSERT INTO champion_bookings" in sql
    assert "'requested'" in sql


@pytest.mark.asyncio
async def test_list_bookings_returns_rows(client, mock_session):
    rows = [
        {
            "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "champion_id": "00000000-0000-0000-0000-000000000001",
            "requested_by": "00000000-0000-0000-0000-000000000055",
            "slot_text": "Tue 14:00",
            "topic": "RAG",
            "team_id": None,
            "status": "requested",
            "created_at": None,
        }
    ]
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    mock_session.execute.return_value = result

    resp = await client.get("/champions/00000000-0000-0000-0000-000000000001/bookings")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["status"] == "requested"


@pytest.mark.asyncio
async def test_confirm_booking_success(client, mock_session):
    result = MagicMock()
    result.rowcount = 1
    mock_session.execute.return_value = result

    resp = await client.post(
        "/champions/bookings/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb/confirm",
        json={"champion_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert resp.status_code == 200
    sql = str(mock_session.execute.await_args.args[0])
    assert "status = 'confirmed'" in sql
    assert "status = 'requested'" in sql


@pytest.mark.asyncio
async def test_confirm_booking_conflict_when_not_requested(client, mock_session):
    result = MagicMock()
    result.rowcount = 0
    mock_session.execute.return_value = result

    resp = await client.post(
        "/champions/bookings/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb/confirm",
        json={"champion_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_done_booking_grants_points(client, mock_session):
    result = MagicMock()
    result.rowcount = 1
    mock_session.execute.return_value = result

    with patch("app.routers.champions.grant_points", new=AsyncMock()) as gp:
        resp = await client.post(
            "/champions/bookings/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb/done",
            json={"champion_id": "00000000-0000-0000-0000-000000000001"},
        )
    assert resp.status_code == 200
    gp.assert_awaited_once()
    kw = gp.await_args.kwargs
    assert kw["delta"] == 150
    assert kw["reason"] == "champion_office_hours"
    assert kw["engineer_id"] == "00000000-0000-0000-0000-000000000001"


@pytest.mark.asyncio
async def test_done_booking_conflict_when_not_confirmed(client, mock_session):
    result = MagicMock()
    result.rowcount = 0
    mock_session.execute.return_value = result

    with patch("app.routers.champions.grant_points", new=AsyncMock()) as gp:
        resp = await client.post(
            "/champions/bookings/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb/done",
            json={"champion_id": "00000000-0000-0000-0000-000000000001"},
        )
    assert resp.status_code == 409
    gp.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_booking_sets_cancelled(client, mock_session):
    result = MagicMock()
    result.rowcount = 1
    mock_session.execute.return_value = result

    resp = await client.post(
        "/champions/bookings/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb/cancel",
        json={"actor_id": "00000000-0000-0000-0000-000000000055"},
    )
    assert resp.status_code == 200
    sql = str(mock_session.execute.await_args.args[0])
    assert "status = 'cancelled'" in sql


@pytest.mark.asyncio
async def test_cancel_booking_conflict_when_terminal(client, mock_session):
    result = MagicMock()
    result.rowcount = 0
    mock_session.execute.return_value = result

    resp = await client.post(
        "/champions/bookings/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb/cancel",
        json={"actor_id": "00000000-0000-0000-0000-000000000055"},
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Wave 3: smart routing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_ask_picks_top_3_by_score(client, mock_session):
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    ask_lookup = MagicMock()
    ask_lookup.mappings.return_value.one_or_none.return_value = {
        "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "tags": ["rag", "agentic"],
    }

    # 5 champions: vary focus overlap and recency
    champ_rows = [
        # high overlap + very recent (top)
        {
            "developer_id": "11111111-1111-1111-1111-111111111111",
            "focus_areas": ["rag", "agentic"],
            "last_submitted_at": now - timedelta(days=1),
        },
        # high overlap, old contribution
        {
            "developer_id": "22222222-2222-2222-2222-222222222222",
            "focus_areas": ["rag", "agentic"],
            "last_submitted_at": now - timedelta(days=90),
        },
        # partial overlap, recent
        {
            "developer_id": "33333333-3333-3333-3333-333333333333",
            "focus_areas": ["rag", "ml", "infra"],
            "last_submitted_at": now - timedelta(days=2),
        },
        # no overlap, recent
        {
            "developer_id": "44444444-4444-4444-4444-444444444444",
            "focus_areas": ["frontend"],
            "last_submitted_at": now - timedelta(days=1),
        },
        # no overlap, no activity
        {
            "developer_id": "55555555-5555-5555-5555-555555555555",
            "focus_areas": ["devops"],
            "last_submitted_at": None,
        },
    ]
    champ_result = MagicMock()
    champ_result.mappings.return_value.all.return_value = champ_rows
    update_result = MagicMock()
    mock_session.execute.side_effect = [ask_lookup, champ_result, update_result]

    resp = await client.post(
        "/champions/asks/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/route",
        json={},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["suggestions"]) == 3
    ids = [s["developer_id"] for s in body["suggestions"]]
    # champ 1 (full overlap + recent) must be first
    assert ids[0] == "11111111-1111-1111-1111-111111111111"
    # champ 4 (no overlap) and champ 5 (no overlap, no activity) ranked lowest
    assert "44444444-4444-4444-4444-444444444444" not in ids
    assert "55555555-5555-5555-5555-555555555555" not in ids
    # scores monotonically non-increasing
    scores = [s["score"] for s in body["suggestions"]]
    assert scores == sorted(scores, reverse=True)
    # third execute call is the UPDATE champion_asks ... routed_to
    update_sql = str(mock_session.execute.await_args_list[2].args[0])
    assert "UPDATE champion_asks" in update_sql
    assert "routed_to" in update_sql


@pytest.mark.asyncio
async def test_route_ask_404_when_missing(client, mock_session):
    lookup = MagicMock()
    lookup.mappings.return_value.one_or_none.return_value = None
    mock_session.execute.return_value = lookup

    resp = await client.post(
        "/champions/asks/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/route",
        json={},
    )
    assert resp.status_code == 404
