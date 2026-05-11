"""Tests for /teams and /teams/{id}/projects endpoints."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_team_row(team_id=None):
    """Return a dict that matches what _team_row_to_dict expects."""
    row = MagicMock()
    _id = team_id or uuid.uuid4()
    row.__getitem__ = lambda self, k: {
        "id": _id,
        "name": "Test Team",
        "slug": "test-team",
        "created_at": None,
        "monthly_budget_usd": None,
        "budget_alert_pct": 0.8,
        "budget_action": "alert",
        "area_id": None,
        "area_name": None,
        "area_slug": None,
        "area_color": None,
    }[k]
    return row


def _make_team_orm(team_id=None):
    """Return a mock that behaves like a Team ORM instance."""
    t = MagicMock()
    t.id = team_id or uuid.uuid4()
    t.name = "Test Team"
    t.slug = "test-team"
    t.created_at = None
    t.monthly_budget_usd = None
    t.budget_alert_pct = 0.8
    t.budget_action = "alert"
    t.area_id = None
    return t


def _make_project_orm(team_id):
    p = MagicMock()
    p.id = uuid.uuid4()
    p.team_id = team_id
    p.name = "My Project"
    p.slug = "my-project"
    p.created_at = None
    return p


def _mappings_all(rows):
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    return result


def _mappings_one_or_none(row):
    result = MagicMock()
    result.mappings.return_value.one_or_none.return_value = row
    return result


def _scalars_all(objs):
    result = MagicMock()
    result.scalars.return_value.all.return_value = objs
    return result


# ---------------------------------------------------------------------------
# GET /teams
# ---------------------------------------------------------------------------

async def test_list_teams_returns_200(client, mock_session):
    team_id = uuid.uuid4()
    row = _make_team_row(team_id)
    mock_session.execute.return_value = _mappings_all([row])

    resp = await client.get("/teams")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["slug"] == "test-team"


async def test_list_teams_empty(client, mock_session):
    mock_session.execute.return_value = _mappings_all([])

    resp = await client.get("/teams")

    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# POST /teams
# ---------------------------------------------------------------------------

async def test_create_team_returns_201(client, mock_session):
    team = _make_team_orm()
    mock_session.refresh = AsyncMock(return_value=None)

    # flush/commit/refresh are all AsyncMocks on mock_session already;
    # we just need execute to handle the audit insert
    mock_session.execute.return_value = MagicMock()

    # After refresh, the team object attributes should be correct.
    # refresh is a no-op mock, so attrs are already set via _make_team_orm.
    # We intercept session.add to capture the added Team.
    added = {}

    def capture_add(obj):
        added["obj"] = obj

    mock_session.add.side_effect = capture_add

    # Patch the Team constructor so we control the returned instance.
    import app.routers.teams as teams_module
    original_team_class = teams_module.Team

    class FakeTeam:
        def __init__(self, **kwargs):
            self.id = team.id
            self.name = kwargs.get("name", "Test Team")
            self.slug = kwargs.get("slug", "test-team")
            self.area_id = kwargs.get("area_id", None)
            self.created_at = None
            self.monthly_budget_usd = None
            self.budget_alert_pct = 0.8
            self.budget_action = "alert"

    teams_module.Team = FakeTeam
    try:
        resp = await client.post("/teams", json={"name": "Test Team", "slug": "test-team"})
    finally:
        teams_module.Team = original_team_class

    assert resp.status_code == 201
    body = resp.json()
    assert body["slug"] == "test-team"
    assert body["name"] == "Test Team"


# ---------------------------------------------------------------------------
# GET /teams/{id}
# ---------------------------------------------------------------------------

async def test_get_team_found(client, mock_session):
    team_id = uuid.uuid4()
    row = _make_team_row(team_id)
    mock_session.execute.return_value = _mappings_one_or_none(row)

    resp = await client.get(f"/teams/{team_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(team_id)


async def test_get_team_not_found(client, mock_session):
    team_id = uuid.uuid4()
    mock_session.execute.return_value = _mappings_one_or_none(None)

    resp = await client.get(f"/teams/{team_id}")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /teams/{id}
# ---------------------------------------------------------------------------

async def test_update_team_found(client, mock_session):
    team_id = uuid.uuid4()
    team = _make_team_orm(team_id)
    mock_session.get.return_value = team
    mock_session.execute.return_value = MagicMock()

    resp = await client.put(
        f"/teams/{team_id}",
        json={"name": "Updated", "slug": "updated"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(team_id)


async def test_update_team_not_found(client, mock_session):
    team_id = uuid.uuid4()
    mock_session.get.return_value = None

    resp = await client.put(
        f"/teams/{team_id}",
        json={"name": "Updated", "slug": "updated"},
    )

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /teams/{id}
# ---------------------------------------------------------------------------

async def test_delete_team_found(client, mock_session):
    team_id = uuid.uuid4()
    team = _make_team_orm(team_id)
    mock_session.get.return_value = team
    mock_session.execute.return_value = MagicMock()

    resp = await client.delete(f"/teams/{team_id}")

    assert resp.status_code == 204
    mock_session.delete.assert_called_once_with(team)


async def test_delete_team_not_found(client, mock_session):
    team_id = uuid.uuid4()
    mock_session.get.return_value = None

    resp = await client.delete(f"/teams/{team_id}")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /teams/{id}/projects
# ---------------------------------------------------------------------------

async def test_list_projects_returns_200(client, mock_session):
    team_id = uuid.uuid4()
    project = _make_project_orm(team_id)
    mock_session.execute.return_value = _scalars_all([project])

    resp = await client.get(f"/teams/{team_id}/projects")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)


# ---------------------------------------------------------------------------
# POST /teams/{id}/projects
# ---------------------------------------------------------------------------

async def test_create_project_returns_201(client, mock_session):
    team_id = uuid.uuid4()

    import app.routers.teams as teams_module
    original_project_class = teams_module.Project

    class FakeProject:
        def __init__(self, **kwargs):
            self.id = uuid.uuid4()
            self.team_id = kwargs.get("team_id", team_id)
            self.name = kwargs.get("name", "My Project")
            self.slug = kwargs.get("slug", "my-project")
            self.created_at = None

    teams_module.Project = FakeProject
    mock_session.execute.return_value = MagicMock()

    try:
        resp = await client.post(
            f"/teams/{team_id}/projects",
            json={"name": "My Project", "slug": "my-project"},
        )
    finally:
        teams_module.Project = original_project_class

    assert resp.status_code == 201
