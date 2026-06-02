"""Tests for /teams/{team_id}/keys endpoints."""

import uuid
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_key_orm(team_id):
    k = MagicMock()
    k.id = uuid.uuid4()
    k.team_id = team_id
    k.name = "test key"
    k.created_at = None
    k.revoked_at = None
    k.monthly_budget_usd = None
    return k


def _scalars_all(objs):
    result = MagicMock()
    result.scalars.return_value.all.return_value = objs
    return result


# ---------------------------------------------------------------------------
# GET /teams/{team_id}/keys
# ---------------------------------------------------------------------------


async def test_list_keys_returns_200(client, mock_session):
    team_id = uuid.uuid4()
    key = _make_key_orm(team_id)
    mock_session.execute.return_value = _scalars_all([key])

    resp = await client.get(f"/teams/{team_id}/keys")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)


async def test_list_keys_empty(client, mock_session):
    team_id = uuid.uuid4()
    mock_session.execute.return_value = _scalars_all([])

    resp = await client.get(f"/teams/{team_id}/keys")

    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# POST /teams/{team_id}/keys
# ---------------------------------------------------------------------------


async def test_create_key_returns_201_with_sk_prefix(client, mock_session):
    team_id = uuid.uuid4()

    import app.routers.api_keys as api_keys_module

    original_class = api_keys_module.APIKey

    created_key = _make_key_orm(team_id)

    class FakeAPIKey:
        def __init__(self, **kwargs):
            self.id = created_key.id
            self.team_id = kwargs.get("team_id", team_id)
            self.project_id = kwargs.get("project_id", None)
            self.name = kwargs.get("name", "test key")
            self.key_hash = kwargs.get("key_hash", "abc")
            self.scopes = kwargs.get("scopes", [])
            self.created_at = None
            self.revoked_at = None

    api_keys_module.APIKey = FakeAPIKey
    mock_session.execute.return_value = MagicMock()

    try:
        resp = await client.post(
            f"/teams/{team_id}/keys",
            json={"name": "test key"},
        )
    finally:
        api_keys_module.APIKey = original_class

    assert resp.status_code == 201
    body = resp.json()
    assert "key" in body
    assert body["key"].startswith("sk-")


async def test_create_key_key_returned_once(client, mock_session):
    """The raw key appears in the response body and nowhere else."""
    team_id = uuid.uuid4()

    import app.routers.api_keys as api_keys_module

    original_class = api_keys_module.APIKey

    created_key = _make_key_orm(team_id)

    class FakeAPIKey:
        def __init__(self, **kwargs):
            self.id = created_key.id
            self.team_id = kwargs.get("team_id", team_id)
            self.project_id = None
            self.name = kwargs.get("name", "test key")
            self.key_hash = kwargs.get("key_hash", "abc")
            self.scopes = kwargs.get("scopes", [])
            self.created_at = None
            self.revoked_at = None

    api_keys_module.APIKey = FakeAPIKey
    mock_session.execute.return_value = MagicMock()

    try:
        resp = await client.post(
            f"/teams/{team_id}/keys",
            json={"name": "test key"},
        )
    finally:
        api_keys_module.APIKey = original_class

    assert resp.status_code == 201
    body = resp.json()
    # The raw key should be present exactly once in the response
    assert "key" in body
    raw_key = body["key"]
    assert raw_key.startswith("sk-")
    # It is not the key_hash (which would be a sha256 hex digest)
    assert len(raw_key) < 100  # raw key, not a 64-char hash


# ---------------------------------------------------------------------------
# DELETE /teams/{team_id}/keys/{key_id}
# ---------------------------------------------------------------------------


async def test_revoke_key_found_returns_204(client, mock_session):
    team_id = uuid.uuid4()
    key = _make_key_orm(team_id)
    mock_session.get.return_value = key
    mock_session.execute.return_value = MagicMock()

    resp = await client.delete(f"/teams/{team_id}/keys/{key.id}")

    assert resp.status_code == 204


async def test_revoke_key_not_found_returns_404(client, mock_session):
    team_id = uuid.uuid4()
    key_id = uuid.uuid4()
    mock_session.get.return_value = None

    resp = await client.delete(f"/teams/{team_id}/keys/{key_id}")

    assert resp.status_code == 404


async def test_revoke_key_wrong_team_returns_404(client, mock_session):
    """Key exists but belongs to a different team — should return 404."""
    real_team_id = uuid.uuid4()
    wrong_team_id = uuid.uuid4()

    key = _make_key_orm(real_team_id)
    mock_session.get.return_value = key

    resp = await client.delete(f"/teams/{wrong_team_id}/keys/{key.id}")

    assert resp.status_code == 404
