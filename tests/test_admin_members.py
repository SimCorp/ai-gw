"""Integration tests for org-node member management endpoints.

The org-node refactor replaced /teams/{id}/members with /nodes/{id}/members
(services/admin/app/routers/nodes.py). These tests were rewritten accordingly.

The new contract differs from the old team-members API:
  - POST /nodes/{id}/members takes {user_id} only (no role) and returns
    {"ok": True} with 201 — not the created member object. Membership is
    therefore verified via GET, not the POST response body.
  - user_id is CAST to uuid server-side, so it must be a valid UUID string.
  - There is no role concept on the API and no PUT (update-role) endpoint.
  - DELETE /nodes/{id}/members/{user_id} is idempotent and always returns 204.

Tests dropped vs the old suite (genuinely-removed functionality):
  - test_add_member_with_role_admin / test_add_member_with_invalid_role_returns_422:
    roles are no longer part of the member API (AddMemberRequest has only
    user_id), so role-specific behaviour and 422-on-bad-role no longer exist.
  - test_update_member_role_returns_200 / test_update_nonexistent_member_returns_404:
    there is no PUT /nodes/{id}/members/{user_id} endpoint at all.
  - test_remove_member_twice_returns_404: removal is now idempotent (204), so
    the double-remove case is folded into test_remove_member_is_idempotent.
"""

import uuid

import pytest


def _new_user_id() -> str:
    """A valid UUID string — the members endpoint CASTs user_id to uuid."""
    return str(uuid.uuid4())


# ── List ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_members_returns_empty_list_initially(admin_client, test_team):
    """GET /nodes/{id}/members must return 200 with an empty list for a new node."""
    resp = await admin_client.get(f"/nodes/{test_team}/members")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    # Fresh test node should have no members
    assert resp.json() == []


# ── Add member ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_member_returns_201(admin_client, test_team):
    """POST /nodes/{id}/members must return 201."""
    user_id = _new_user_id()
    resp = await admin_client.post(
        f"/nodes/{test_team}/members",
        json={"user_id": user_id},
    )
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    # The POST response is {"ok": True}; membership is verified via GET.
    assert resp.json().get("ok") is True

    # Cleanup
    await admin_client.delete(f"/nodes/{test_team}/members/{user_id}")


@pytest.mark.asyncio
async def test_added_member_appears_in_list(admin_client, test_team):
    """After adding a member, GET /nodes/{id}/members must include them."""
    user_id = _new_user_id()
    add_resp = await admin_client.post(
        f"/nodes/{test_team}/members",
        json={"user_id": user_id},
    )
    assert add_resp.status_code == 201

    try:
        list_resp = await admin_client.get(f"/nodes/{test_team}/members")
        assert list_resp.status_code == 200
        user_ids = [m["user_id"] for m in list_resp.json()]
        assert user_id in user_ids, f"Added member {user_id!r} not found in list"
    finally:
        await admin_client.delete(f"/nodes/{test_team}/members/{user_id}")


# ── Remove member ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_remove_member_returns_204(admin_client, test_team):
    """DELETE /nodes/{id}/members/{user_id} must return 204."""
    user_id = _new_user_id()
    add_resp = await admin_client.post(
        f"/nodes/{test_team}/members",
        json={"user_id": user_id},
    )
    assert add_resp.status_code == 201

    delete_resp = await admin_client.delete(f"/nodes/{test_team}/members/{user_id}")
    assert delete_resp.status_code == 204


@pytest.mark.asyncio
async def test_remove_member_is_idempotent(admin_client, test_team):
    """Removing a member twice — both DELETEs return 204 (idempotent)."""
    user_id = _new_user_id()
    add_resp = await admin_client.post(
        f"/nodes/{test_team}/members",
        json={"user_id": user_id},
    )
    assert add_resp.status_code == 201

    first = await admin_client.delete(f"/nodes/{test_team}/members/{user_id}")
    assert first.status_code == 204

    second = await admin_client.delete(f"/nodes/{test_team}/members/{user_id}")
    assert second.status_code == 204


@pytest.mark.asyncio
async def test_removed_member_not_in_list(admin_client, test_team):
    """After removal, member must not appear in GET /nodes/{id}/members."""
    user_id = _new_user_id()
    await admin_client.post(
        f"/nodes/{test_team}/members",
        json={"user_id": user_id},
    )
    await admin_client.delete(f"/nodes/{test_team}/members/{user_id}")

    list_resp = await admin_client.get(f"/nodes/{test_team}/members")
    assert list_resp.status_code == 200
    user_ids = [m["user_id"] for m in list_resp.json()]
    assert user_id not in user_ids, f"Removed member {user_id!r} still appears in list"
