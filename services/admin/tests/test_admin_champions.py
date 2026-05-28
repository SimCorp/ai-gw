import pytest
from unittest.mock import MagicMock


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
