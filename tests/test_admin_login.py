"""Integration tests for admin portal authentication endpoints."""

import pytest
import httpx
from conftest import ADMIN_URL


# ── Login ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_valid_credentials_returns_200():
    """POST /admin-auth/login with valid credentials must return 200 with token."""
    async with httpx.AsyncClient(base_url=ADMIN_URL, timeout=10.0) as client:
        resp = await client.post("/admin-auth/login", json={
            "email": "admin@simcorp.com",
            "password": "Admin1234!",
        })
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "token" in data
    assert "user" in data
    assert data["user"]["email"] == "admin@simcorp.com"
    assert data["user"]["role"] == "superadmin"
    assert len(data["token"]) > 20


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401():
    """POST /admin-auth/login with wrong password must return 401."""
    async with httpx.AsyncClient(base_url=ADMIN_URL, timeout=10.0) as client:
        resp = await client.post("/admin-auth/login", json={
            "email": "admin@simcorp.com",
            "password": "wrongpassword",
        })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_email_returns_401():
    """POST /admin-auth/login with unknown email must return 401."""
    async with httpx.AsyncClient(base_url=ADMIN_URL, timeout=10.0) as client:
        resp = await client.post("/admin-auth/login", json={
            "email": "nonexistent@simcorp.com",
            "password": "Admin1234!",
        })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_response_shape():
    """POST /admin-auth/login response must include token and user fields."""
    async with httpx.AsyncClient(base_url=ADMIN_URL, timeout=10.0) as client:
        resp = await client.post("/admin-auth/login", json={
            "email": "admin@simcorp.com",
            "password": "Admin1234!",
        })
    assert resp.status_code == 200
    data = resp.json()
    for field in ("token", "user"):
        assert field in data, f"Missing field '{field}'"
    for field in ("email", "role", "display_name"):
        assert field in data["user"], f"Missing user field '{field}'"


# ── /me ───────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_me_returns_200_with_valid_token():
    """GET /admin-auth/me with valid token must return 200 with user info."""
    async with httpx.AsyncClient(base_url=ADMIN_URL, timeout=10.0) as client:
        login = await client.post("/admin-auth/login", json={
            "email": "admin@simcorp.com",
            "password": "Admin1234!",
        })
        token = login.json()["token"]
        resp = await client.get("/admin-auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "admin@simcorp.com"


@pytest.mark.asyncio
async def test_me_returns_401_without_token():
    """GET /admin-auth/me without token must return 401."""
    async with httpx.AsyncClient(base_url=ADMIN_URL, timeout=10.0) as client:
        resp = await client.get("/admin-auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_401_with_invalid_token():
    """GET /admin-auth/me with a garbage token must return 401."""
    async with httpx.AsyncClient(base_url=ADMIN_URL, timeout=10.0) as client:
        resp = await client.get("/admin-auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


# ── Logout ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_logout_returns_200():
    """POST /admin-auth/logout must return 200."""
    async with httpx.AsyncClient(base_url=ADMIN_URL, timeout=10.0) as client:
        login = await client.post("/admin-auth/login", json={
            "email": "admin@simcorp.com",
            "password": "Admin1234!",
        })
        token = login.json()["token"]
        resp = await client.post("/admin-auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_me_after_logout_returns_401():
    """GET /admin-auth/me after logout must return 401 (session invalidated)."""
    async with httpx.AsyncClient(base_url=ADMIN_URL, timeout=10.0) as client:
        login = await client.post("/admin-auth/login", json={
            "email": "admin@simcorp.com",
            "password": "Admin1234!",
        })
        token = login.json()["token"]
        await client.post("/admin-auth/logout", headers={"Authorization": f"Bearer {token}"})
        resp = await client.get("/admin-auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


# ── Change password ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_change_password_wrong_current_returns_401():
    """POST /admin-auth/change-password with wrong current password must return 401."""
    async with httpx.AsyncClient(base_url=ADMIN_URL, timeout=10.0) as client:
        login = await client.post("/admin-auth/login", json={
            "email": "admin@simcorp.com",
            "password": "Admin1234!",
        })
        token = login.json()["token"]
        resp = await client.post(
            "/admin-auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"current_password": "wrongpassword", "new_password": "NewPassword123!"},
        )
    assert resp.status_code == 401
