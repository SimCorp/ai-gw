"""Tests for /teams/{id}/members endpoints."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_member_orm(team_id, user_id="user-123", role="member"):
    m = MagicMock()
    m.id = uuid.uuid4()
    m.team_id = team_id
    m.user_id = user_id
    m.role = role
    m.developer_id = None
    m.created_at = None
    return m


def _scalars_all(objs):
    result = MagicMock()
    result.scalars.return_value.all.return_value = objs
    return result


def _scalar_one_or_none(obj):
    result = MagicMock()
    result.scalar_one_or_none.return_value = obj
    return result


def _one_or_none(obj):
    """For direct .one_or_none() on result (developer lookup in add_member)."""
    result = MagicMock()
    result.one_or_none.return_value = obj
    return result


# ---------------------------------------------------------------------------
# GET /teams/{id}/members
# ---------------------------------------------------------------------------

async def test_list_members_returns_200(client, mock_session):
    team_id = uuid.uuid4()
    member = _make_member_orm(team_id)
    mock_session.execute.return_value = _scalars_all([member])

    resp = await client.get(f"/teams/{team_id}/members")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)


async def test_list_members_empty(client, mock_session):
    team_id = uuid.uuid4()
    mock_session.execute.return_value = _scalars_all([])

    resp = await client.get(f"/teams/{team_id}/members")

    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# POST /teams/{id}/members
# ---------------------------------------------------------------------------

async def test_add_member_valid_role_returns_201(client, mock_session):
    team_id = uuid.uuid4()
    member = _make_member_orm(team_id)

    import app.routers.members as members_module
    original_class = members_module.TeamMember

    class FakeMember:
        def __init__(self, **kwargs):
            self.id = member.id
            self.team_id = kwargs.get("team_id", team_id)
            self.user_id = kwargs.get("user_id", "user-123")
            self.role = kwargs.get("role", "member")
            self.developer_id = kwargs.get("developer_id", None)
            self.created_at = None

    members_module.TeamMember = FakeMember
    # No developer lookup (no "@" in user_id), so single execute for audit
    mock_session.execute.return_value = MagicMock()

    try:
        resp = await client.post(
            f"/teams/{team_id}/members",
            json={"user_id": "user-123", "role": "member"},
        )
    finally:
        members_module.TeamMember = original_class

    assert resp.status_code == 201


async def test_add_member_invalid_role_returns_422(client, mock_session):
    team_id = uuid.uuid4()

    resp = await client.post(
        f"/teams/{team_id}/members",
        json={"user_id": "user-123", "role": "superuser"},
    )

    assert resp.status_code == 422


async def test_add_member_email_triggers_developer_lookup(client, mock_session):
    """When user_id contains '@', the router does a developer lookup."""
    team_id = uuid.uuid4()
    member = _make_member_orm(team_id, user_id="dev@example.com")

    import app.routers.members as members_module
    original_class = members_module.TeamMember

    class FakeMember:
        def __init__(self, **kwargs):
            self.id = member.id
            self.team_id = kwargs.get("team_id", team_id)
            self.user_id = kwargs.get("user_id", "dev@example.com")
            self.role = kwargs.get("role", "member")
            self.developer_id = kwargs.get("developer_id", None)
            self.created_at = None

    members_module.TeamMember = FakeMember

    # First execute: developer lookup; second: audit insert
    dev_lookup_result = MagicMock()
    dev_lookup_result.one_or_none.return_value = None  # developer not found → None
    audit_result = MagicMock()
    mock_session.execute.side_effect = [dev_lookup_result, audit_result]

    try:
        resp = await client.post(
            f"/teams/{team_id}/members",
            json={"user_id": "dev@example.com", "role": "admin"},
        )
    finally:
        members_module.TeamMember = original_class

    assert resp.status_code == 201
    # developer lookup was attempted
    assert mock_session.execute.call_count >= 1


# ---------------------------------------------------------------------------
# PUT /teams/{id}/members/{user_id}
# ---------------------------------------------------------------------------

async def test_update_member_role_found(client, mock_session):
    team_id = uuid.uuid4()
    user_id = "user-123"
    member = _make_member_orm(team_id, user_id=user_id)
    mock_session.execute.side_effect = [
        _scalar_one_or_none(member),  # select member
        MagicMock(),                   # audit insert
    ]

    resp = await client.put(
        f"/teams/{team_id}/members/{user_id}",
        json={"user_id": user_id, "role": "admin"},
    )

    assert resp.status_code == 200


async def test_update_member_role_not_found(client, mock_session):
    team_id = uuid.uuid4()
    user_id = "ghost-user"
    mock_session.execute.return_value = _scalar_one_or_none(None)

    resp = await client.put(
        f"/teams/{team_id}/members/{user_id}",
        json={"user_id": user_id, "role": "member"},
    )

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /teams/{id}/members/{user_id}
# ---------------------------------------------------------------------------

async def test_remove_member_found_returns_204(client, mock_session):
    team_id = uuid.uuid4()
    user_id = "user-123"
    member = _make_member_orm(team_id, user_id=user_id)
    mock_session.execute.side_effect = [
        _scalar_one_or_none(member),  # select member
        MagicMock(),                   # audit insert
    ]

    resp = await client.delete(f"/teams/{team_id}/members/{user_id}")

    assert resp.status_code == 204
    mock_session.delete.assert_called_once_with(member)


async def test_remove_member_not_found_returns_404(client, mock_session):
    team_id = uuid.uuid4()
    user_id = "ghost-user"
    mock_session.execute.return_value = _scalar_one_or_none(None)

    resp = await client.delete(f"/teams/{team_id}/members/{user_id}")

    assert resp.status_code == 404
