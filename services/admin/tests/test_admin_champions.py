from unittest.mock import MagicMock

import pytest


@pytest.mark.asyncio
async def test_nominate_inserts_champion(client, mock_session):
    resp = await client.post(
        "/admin/champions",
        json={
            "developer_id": "00000000-0000-0000-0000-000000000001",
            "bio": "RAG specialist",
            "focus_areas": ["rag", "agentic"],
        },
    )
    assert resp.status_code == 201
    assert mock_session.execute.await_count >= 1
    assert mock_session.commit.await_count >= 1


@pytest.mark.asyncio
async def test_retire_sets_active_false(client, mock_session):
    result = MagicMock()
    result.rowcount = 1
    mock_session.execute.return_value = result

    resp = await client.delete("/admin/champions/00000000-0000-0000-0000-000000000001")
    assert resp.status_code == 204
    args, _ = mock_session.execute.await_args
    assert "UPDATE champions" in str(args[0])
    assert "active" in str(args[0])


@pytest.mark.asyncio
async def test_retire_returns_404_when_missing(client, mock_session):
    result = MagicMock()
    result.rowcount = 0
    mock_session.execute.return_value = result

    resp = await client.delete("/admin/champions/00000000-0000-0000-0000-000000000999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Wave 2: flag moderation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_flags_returns_joined_rows(client, mock_session):
    rows = [
        {
            "id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
            "contribution_id": "11111111-1111-1111-1111-111111111111",
            "contribution_title": "Spammy post",
            "flagged_by": "00000000-0000-0000-0000-000000000055",
            "reason": "spam",
            "created_at": None,
        }
    ]
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    mock_session.execute.return_value = result

    resp = await client.get("/admin/champions/flags")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["contribution_title"] == "Spammy post"
    args, _ = mock_session.execute.await_args
    sql = str(args[0])
    assert "champion_flags" in sql
    assert "JOIN champion_contributions" in sql
    assert "status = 'open'" in sql


@pytest.mark.asyncio
async def test_resolve_flag_dismiss_updates_status(client, mock_session):
    lookup = MagicMock()
    lookup.mappings.return_value.one_or_none.return_value = {
        "contribution_id": "11111111-1111-1111-1111-111111111111",
    }
    update = MagicMock()
    audit_insert = MagicMock()
    mock_session.execute.side_effect = [lookup, update, audit_insert]

    resp = await client.post(
        "/admin/champions/flags/ffffffff-ffff-ffff-ffff-ffffffffffff/resolve",
        json={"action": "dismiss"},
    )
    assert resp.status_code == 200
    # second execute call should be the dismiss UPDATE
    second_sql = str(mock_session.execute.await_args_list[1].args[0])
    assert "champion_flags" in second_sql
    assert "'dismissed'" in second_sql


@pytest.mark.asyncio
async def test_resolve_flag_remove_marks_contribution(client, mock_session):
    lookup = MagicMock()
    lookup.mappings.return_value.one_or_none.return_value = {
        "contribution_id": "11111111-1111-1111-1111-111111111111",
    }
    mock_session.execute.side_effect = [lookup, MagicMock(), MagicMock(), MagicMock()]

    resp = await client.post(
        "/admin/champions/flags/ffffffff-ffff-ffff-ffff-ffffffffffff/resolve",
        json={"action": "remove"},
    )
    assert resp.status_code == 200
    calls = mock_session.execute.await_args_list
    # second call: tombstone the contribution
    assert "flag_count = 999" in str(calls[1].args[0])
    # third call: cascade flag rows to 'removed'
    assert "'removed'" in str(calls[2].args[0])


@pytest.mark.asyncio
async def test_resolve_flag_returns_404_when_missing(client, mock_session):
    lookup = MagicMock()
    lookup.mappings.return_value.one_or_none.return_value = None
    mock_session.execute.return_value = lookup

    resp = await client.post(
        "/admin/champions/flags/ffffffff-ffff-ffff-ffff-ffffffffffff/resolve",
        json={"action": "dismiss"},
    )
    assert resp.status_code == 404
