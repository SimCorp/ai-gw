"""Developer portal API tests — registration, login, session token, and profile endpoints.

The developer auth API at /dev-auth/* is token-based (not cookie-based).
Register and login return {"token": ..., ...} in JSON.
Subsequent authenticated requests use Authorization: Bearer <token>.

These tests replace the old test_portal.py which hit removed Jinja2 endpoints.
"""

import uuid

import httpx
import pytest

from conftest import ADMIN_URL


# ── Helpers ───────────────────────────────────────────────────────────────────


def _random_email() -> str:
    return f"test-{uuid.uuid4().hex[:10]}@simcorp-test.invalid"


async def _register(client: httpx.AsyncClient, email: str, password: str,
                    display_name: str = "Test User") -> httpx.Response:
    return await client.post(
        "/dev-auth/register",
        json={"email": email, "display_name": display_name, "password": password},
    )


async def _login(client: httpx.AsyncClient, email: str, password: str) -> httpx.Response:
    return await client.post(
        "/dev-auth/login",
        json={"email": email, "password": password},
    )


# ── Register ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_new_email_returns_201(portal_client):
    """POST /dev-auth/register with new email must return 201."""
    resp = await _register(portal_client, _random_email(), "SecurePass123!")
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_register_returns_token(portal_client):
    """POST /dev-auth/register must return a token in the response body."""
    resp = await _register(portal_client, _random_email(), "SecurePass123!")
    assert resp.status_code == 201
    data = resp.json()
    assert "token" in data, "Register response must contain 'token'"
    assert isinstance(data["token"], str) and len(data["token"]) > 10


@pytest.mark.asyncio
async def test_register_response_shape(portal_client):
    """POST /dev-auth/register must return developer_id, email, display_name."""
    email = _random_email()
    resp = await _register(portal_client, email, "SecurePass123!", "Jane Doe")
    assert resp.status_code == 201
    data = resp.json()
    for field in ("token", "developer_id", "email", "display_name"):
        assert field in data, f"Register response missing field '{field}'"
    assert data["email"] == email.lower()
    assert data["display_name"] == "Jane Doe"


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409(portal_client):
    """POST /dev-auth/register with an already-registered email must return 409."""
    email = _random_email()
    first = await _register(portal_client, email, "SecurePass123!")
    assert first.status_code == 201

    second = await _register(portal_client, email, "AnotherPass456!")
    assert second.status_code == 409, (
        f"Expected 409 for duplicate email, got {second.status_code}: {second.text}"
    )


@pytest.mark.asyncio
async def test_register_short_password_returns_422(portal_client):
    """POST /dev-auth/register with password shorter than 8 characters must return 422."""
    resp = await _register(portal_client, _random_email(), "short")
    assert resp.status_code == 422, (
        f"Expected 422 for short password, got {resp.status_code}: {resp.text}"
    )


@pytest.mark.asyncio
async def test_register_invalid_email_returns_422(portal_client):
    """POST /dev-auth/register with invalid email (no @) must return 422."""
    resp = await portal_client.post(
        "/dev-auth/register",
        json={"email": "notanemail", "display_name": "Test", "password": "SecurePass123!"},
    )
    assert resp.status_code == 422, (
        f"Expected 422 for invalid email, got {resp.status_code}: {resp.text}"
    )


# ── Login ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_correct_credentials_returns_200(portal_client):
    """POST /dev-auth/login with correct credentials must return 200."""
    email = _random_email()
    await _register(portal_client, email, "SecurePass123!")
    resp = await _login(portal_client, email, "SecurePass123!")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_login_returns_token(portal_client):
    """POST /dev-auth/login must return a token in the response body."""
    email = _random_email()
    await _register(portal_client, email, "SecurePass123!")
    resp = await _login(portal_client, email, "SecurePass123!")
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data, "Login response must contain 'token'"
    assert isinstance(data["token"], str) and len(data["token"]) > 10


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(portal_client):
    """POST /dev-auth/login with wrong password must return 401."""
    email = _random_email()
    await _register(portal_client, email, "CorrectPass123!")
    resp = await _login(portal_client, email, "WrongPass456!")
    assert resp.status_code == 401, f"Expected 401 for wrong password, got {resp.status_code}"


@pytest.mark.asyncio
async def test_login_unknown_email_returns_401(portal_client):
    """POST /dev-auth/login with unknown email must return 401."""
    resp = await _login(portal_client, _random_email(), "AnyPass123!")
    assert resp.status_code == 401, f"Expected 401 for unknown email, got {resp.status_code}"


# ── /me endpoint ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_me_with_valid_token_returns_200():
    """GET /dev-auth/me with a valid token must return 200 and the developer object."""
    email = _random_email()
    async with httpx.AsyncClient(base_url=ADMIN_URL, timeout=30.0) as client:
        reg_resp = await _register(client, email, "SecurePass123!", "Me Tester")
        assert reg_resp.status_code == 201
        token = reg_resp.json()["token"]

        me_resp = await client.get(
            "/dev-auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert me_resp.status_code == 200, f"Expected 200, got {me_resp.status_code}: {me_resp.text}"
    data = me_resp.json()
    assert data["email"] == email.lower()


@pytest.mark.asyncio
async def test_me_without_token_returns_401(portal_client):
    """GET /dev-auth/me without Authorization header must return 401."""
    resp = await portal_client.get("/dev-auth/me")
    assert resp.status_code == 401, f"Expected 401 without token, got {resp.status_code}"


@pytest.mark.asyncio
async def test_me_with_invalid_token_returns_401(portal_client):
    """GET /dev-auth/me with a bogus token must return 401."""
    resp = await portal_client.get(
        "/dev-auth/me",
        headers={"Authorization": "Bearer totally-invalid-token"},
    )
    assert resp.status_code == 401, f"Expected 401 for invalid token, got {resp.status_code}"


@pytest.mark.asyncio
async def test_me_returns_correct_user_fields():
    """GET /dev-auth/me must include developer_id, email, display_name."""
    email = _random_email()
    async with httpx.AsyncClient(base_url=ADMIN_URL, timeout=30.0) as client:
        reg_resp = await _register(client, email, "SecurePass123!", "Field Checker")
        assert reg_resp.status_code == 201
        token = reg_resp.json()["token"]

        me_resp = await client.get(
            "/dev-auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert me_resp.status_code == 200
    data = me_resp.json()
    for field in ("developer_id", "email", "display_name"):
        assert field in data, f"/dev-auth/me response missing field '{field}'"


# ── Logout ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_logout_returns_200():
    """POST /dev-auth/logout with valid token must return 200."""
    email = _random_email()
    async with httpx.AsyncClient(base_url=ADMIN_URL, timeout=30.0) as client:
        reg_resp = await _register(client, email, "SecurePass123!")
        assert reg_resp.status_code == 201
        token = reg_resp.json()["token"]

        logout_resp = await client.post(
            "/dev-auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert logout_resp.status_code == 200, (
        f"Expected 200 for logout, got {logout_resp.status_code}: {logout_resp.text}"
    )


@pytest.mark.asyncio
async def test_me_after_logout_returns_401():
    """After logout, GET /dev-auth/me must return 401."""
    email = _random_email()
    async with httpx.AsyncClient(base_url=ADMIN_URL, timeout=30.0) as client:
        reg_resp = await _register(client, email, "SecurePass123!")
        assert reg_resp.status_code == 201
        token = reg_resp.json()["token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        # Verify token works
        me_before = await client.get("/dev-auth/me", headers=auth_headers)
        assert me_before.status_code == 200

        # Logout
        await client.post("/dev-auth/logout", headers=auth_headers)

        # Token should now be invalid
        me_after = await client.get("/dev-auth/me", headers=auth_headers)
    assert me_after.status_code == 401, (
        f"Expected 401 after logout, got {me_after.status_code}"
    )


# ── Login token reuse ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_token_allows_me_access():
    """Token obtained via login (not register) must grant /me access."""
    email = _random_email()
    async with httpx.AsyncClient(base_url=ADMIN_URL, timeout=30.0) as client:
        # Register first
        await _register(client, email, "LoginTokenTest!")
        # Then login (separate token)
        login_resp = await _login(client, email, "LoginTokenTest!")
        assert login_resp.status_code == 200
        login_token = login_resp.json()["token"]

        me_resp = await client.get(
            "/dev-auth/me",
            headers={"Authorization": f"Bearer {login_token}"},
        )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == email.lower()


# ── Select team ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_select_team_returns_200(admin_client, root_node_id):
    """POST /dev-auth/select-team?team_id=... requires team membership.

    Setup rewritten for the org-node refactor: the "team" is created via
    POST /nodes (type='team') under the root, and membership via
    POST /nodes/{id}/members with the developer's UUID. The select-team
    assertions are unchanged — they exercise the lead-owned dev-auth backend.
    """
    uid = uuid.uuid4().hex[:8]
    team_resp = await admin_client.post(
        "/nodes",
        json={"name": f"portal-test-{uid}", "type": "team", "parent_id": root_node_id},
    )
    assert team_resp.status_code == 201
    team_id = team_resp.json()["id"]

    try:
        email = _random_email()
        async with httpx.AsyncClient(base_url=ADMIN_URL, timeout=30.0) as client:
            reg_resp = await _register(client, email, "SecurePass123!")
            assert reg_resp.status_code == 201
            reg_data = reg_resp.json()
            token = reg_data["token"]
            developer_id = reg_data["developer_id"]

            # Add developer as a node member (user_id is CAST to uuid server-side)
            member_resp = await admin_client.post(
                f"/nodes/{team_id}/members",
                json={"user_id": developer_id},
            )
            assert member_resp.status_code == 201, f"Failed to add member: {member_resp.text}"

            sel_resp = await client.post(
                f"/dev-auth/select-team?team_id={team_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert sel_resp.status_code == 200, (
            f"Expected 200 for select-team, got {sel_resp.status_code}: {sel_resp.text}"
        )
        data = sel_resp.json()
        assert data["team_id"] == team_id
    finally:
        await admin_client.delete(f"/nodes/{team_id}")


@pytest.mark.asyncio
async def test_select_team_nonexistent_returns_404():
    """POST /dev-auth/select-team?team_id=<nonexistent> must return 404."""
    email = _random_email()
    async with httpx.AsyncClient(base_url=ADMIN_URL, timeout=30.0) as client:
        reg_resp = await _register(client, email, "SecurePass123!")
        assert reg_resp.status_code == 201
        token = reg_resp.json()["token"]

        sel_resp = await client.post(
            f"/dev-auth/select-team?team_id={uuid.uuid4()}",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert sel_resp.status_code == 404, (
        f"Expected 404 for nonexistent team, got {sel_resp.status_code}"
    )
