"""Integration tests for team member management endpoints.

Tests cover:
  - Listing members (empty initially)
  - Adding members with valid roles
  - Invalid role rejection
  - Role update
  - Member removal
  - 404 on non-existent member operations
"""

import uuid

import pytest


# ── List ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_members_returns_empty_list_initially(admin_client, test_team):
    """GET /teams/{id}/members must return 200 with an empty list for a new team."""
    resp = await admin_client.get(f"/teams/{test_team}/members")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    # Fresh test team should have no members
    assert resp.json() == []


# ── Add member ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_member_with_role_member_returns_201(admin_client, test_team):
    """POST /teams/{id}/members with role=member must return 201."""
    user_id = f"user-{uuid.uuid4().hex[:8]}"
    resp = await admin_client.post(
        f"/teams/{test_team}/members",
        json={"user_id": user_id, "role": "member"},
    )
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["user_id"] == user_id
    assert data["role"] == "member"

    # Cleanup
    await admin_client.delete(f"/teams/{test_team}/members/{user_id}")


@pytest.mark.asyncio
async def test_add_member_with_role_admin_returns_201(admin_client, test_team):
    """POST /teams/{id}/members with role=admin must return 201."""
    user_id = f"admin-{uuid.uuid4().hex[:8]}"
    resp = await admin_client.post(
        f"/teams/{test_team}/members",
        json={"user_id": user_id, "role": "admin"},
    )
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["role"] == "admin"

    # Cleanup
    await admin_client.delete(f"/teams/{test_team}/members/{user_id}")


@pytest.mark.asyncio
async def test_add_member_with_invalid_role_returns_422(admin_client, test_team):
    """POST /teams/{id}/members with an invalid role must return 422."""
    resp = await admin_client.post(
        f"/teams/{test_team}/members",
        json={"user_id": f"user-{uuid.uuid4().hex[:8]}", "role": "superuser"},
    )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_added_member_appears_in_list(admin_client, test_team):
    """After adding a member, GET /teams/{id}/members must include them."""
    user_id = f"user-{uuid.uuid4().hex[:8]}"
    add_resp = await admin_client.post(
        f"/teams/{test_team}/members",
        json={"user_id": user_id, "role": "member"},
    )
    assert add_resp.status_code == 201

    try:
        list_resp = await admin_client.get(f"/teams/{test_team}/members")
        assert list_resp.status_code == 200
        user_ids = [m["user_id"] for m in list_resp.json()]
        assert user_id in user_ids, f"Added member {user_id!r} not found in list"
    finally:
        await admin_client.delete(f"/teams/{test_team}/members/{user_id}")


# ── Update role ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_member_role_returns_200(admin_client, test_team):
    """PUT /teams/{id}/members/{user_id} must return 200 with updated role."""
    user_id = f"user-{uuid.uuid4().hex[:8]}"
    add_resp = await admin_client.post(
        f"/teams/{test_team}/members",
        json={"user_id": user_id, "role": "member"},
    )
    assert add_resp.status_code == 201

    try:
        update_resp = await admin_client.put(
            f"/teams/{test_team}/members/{user_id}",
            json={"user_id": user_id, "role": "admin"},
        )
        assert update_resp.status_code == 200, f"Expected 200, got {update_resp.status_code}: {update_resp.text}"
        assert update_resp.json()["role"] == "admin"
    finally:
        await admin_client.delete(f"/teams/{test_team}/members/{user_id}")


@pytest.mark.asyncio
async def test_update_nonexistent_member_returns_404(admin_client, test_team):
    """PUT /teams/{id}/members/{non-existent} must return 404."""
    resp = await admin_client.put(
        f"/teams/{test_team}/members/nonexistent-user-{uuid.uuid4().hex[:8]}",
        json={"user_id": "nonexistent", "role": "member"},
    )
    assert resp.status_code == 404


# ── Remove member ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_remove_member_returns_204(admin_client, test_team):
    """DELETE /teams/{id}/members/{user_id} must return 204."""
    user_id = f"user-{uuid.uuid4().hex[:8]}"
    add_resp = await admin_client.post(
        f"/teams/{test_team}/members",
        json={"user_id": user_id, "role": "member"},
    )
    assert add_resp.status_code == 201

    delete_resp = await admin_client.delete(f"/teams/{test_team}/members/{user_id}")
    assert delete_resp.status_code == 204


@pytest.mark.asyncio
async def test_remove_member_twice_returns_404(admin_client, test_team):
    """Removing a member twice — the second DELETE must return 404."""
    user_id = f"user-{uuid.uuid4().hex[:8]}"
    add_resp = await admin_client.post(
        f"/teams/{test_team}/members",
        json={"user_id": user_id, "role": "member"},
    )
    assert add_resp.status_code == 201

    first = await admin_client.delete(f"/teams/{test_team}/members/{user_id}")
    assert first.status_code == 204

    second = await admin_client.delete(f"/teams/{test_team}/members/{user_id}")
    assert second.status_code == 404


@pytest.mark.asyncio
async def test_removed_member_not_in_list(admin_client, test_team):
    """After removal, member must not appear in GET /teams/{id}/members."""
    user_id = f"user-{uuid.uuid4().hex[:8]}"
    await admin_client.post(
        f"/teams/{test_team}/members",
        json={"user_id": user_id, "role": "member"},
    )
    await admin_client.delete(f"/teams/{test_team}/members/{user_id}")

    list_resp = await admin_client.get(f"/teams/{test_team}/members")
    assert list_resp.status_code == 200
    user_ids = [m["user_id"] for m in list_resp.json()]
    assert user_id not in user_ids, f"Removed member {user_id!r} still appears in list"
