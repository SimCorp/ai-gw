"""Developer portal tests — registration, login, session cookie, key management.

The portal uses HTML form submissions and session cookies.  httpx is used
without follow_redirects so we can assert on each redirect step explicitly.

Signup auto-creates a team and developer row in Postgres.  The tests use
unique random emails to avoid uniqueness conflicts with prior runs.  We do
not clean up developer or team rows created through the portal (no admin API
for developer deletion), so the test DB accumulates rows over time.  In a
real environment you would purge the developers table as part of CI teardown.
"""

import uuid

import httpx
import pytest

from conftest import ADMIN_URL


# ── Helpers ──────────────────────────────────────────────────────────────────


def _random_email() -> str:
    return f"test-{uuid.uuid4().hex[:10]}@simcorp-test.invalid"


async def _signup(client: httpx.AsyncClient, email: str, password: str, name: str = "Test User") -> httpx.Response:
    return await client.post(
        "/portal/signup",
        data={
            "email": email,
            "display_name": name,
            "password": password,
            "password2": password,
        },
    )


async def _login(client: httpx.AsyncClient, email: str, password: str) -> httpx.Response:
    return await client.post(
        "/portal/login",
        data={"email": email, "password": password},
    )


# ── Signup ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_signup_redirects_to_login(portal_client):
    """Successful signup must redirect to /portal/login with a success message."""
    email = _random_email()
    resp = await _signup(portal_client, email, "SecurePass123!")
    # Expect a 303 redirect to the login page
    assert resp.status_code == 303, (
        f"Expected 303 redirect after signup, got {resp.status_code}"
    )
    location = resp.headers.get("location", "")
    assert "/portal/login" in location, (
        f"Expected redirect to /portal/login, got {location!r}"
    )


@pytest.mark.asyncio
async def test_signup_duplicate_email_shows_error(portal_client):
    """Signing up with an already-registered email must return an error page (not 303)."""
    email = _random_email()
    # First signup succeeds
    first = await _signup(portal_client, email, "SecurePass123!")
    assert first.status_code == 303

    # Second signup with the same email must not redirect; must show an error
    second = await _signup(portal_client, email, "AnotherPass456!")
    # The server re-renders the signup page (200) with an error message
    assert second.status_code == 200, (
        f"Expected 200 with error for duplicate email, got {second.status_code}"
    )
    assert b"already exists" in second.content.lower() or b"error" in second.content.lower(), (
        "Duplicate signup should contain an error message"
    )


@pytest.mark.asyncio
async def test_signup_password_mismatch_shows_error(portal_client):
    """Mismatched passwords must re-render the signup form with an error."""
    resp = await portal_client.post(
        "/portal/signup",
        data={
            "email": _random_email(),
            "display_name": "Test",
            "password": "SecurePass123!",
            "password2": "DifferentPass456!",
        },
    )
    assert resp.status_code == 200
    assert b"do not match" in resp.content.lower() or b"error" in resp.content.lower()


@pytest.mark.asyncio
async def test_signup_short_password_shows_error(portal_client):
    """A password shorter than 8 characters must re-render with an error."""
    resp = await portal_client.post(
        "/portal/signup",
        data={
            "email": _random_email(),
            "display_name": "Test",
            "password": "short",
            "password2": "short",
        },
    )
    assert resp.status_code == 200
    assert b"8 character" in resp.content.lower() or b"error" in resp.content.lower()


# ── Login ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_valid_credentials_sets_cookie_and_redirects(portal_client):
    """Valid login must redirect to /portal/dashboard and set portal_session cookie."""
    email = _random_email()
    await _signup(portal_client, email, "SecurePass123!")

    resp = await _login(portal_client, email, "SecurePass123!")
    assert resp.status_code == 303, (
        f"Expected 303 redirect after login, got {resp.status_code}"
    )
    location = resp.headers.get("location", "")
    assert "/portal/dashboard" in location, (
        f"Expected redirect to /portal/dashboard, got {location!r}"
    )
    assert "portal_session" in resp.cookies, (
        "Login must set 'portal_session' cookie"
    )


@pytest.mark.asyncio
async def test_login_wrong_password_returns_error(portal_client):
    """Wrong password must re-render the login page with a 401 status and error."""
    email = _random_email()
    await _signup(portal_client, email, "CorrectPass123!")

    resp = await _login(portal_client, email, "WrongPass456!")
    assert resp.status_code == 401, (
        f"Expected 401 for wrong password, got {resp.status_code}"
    )
    assert b"invalid" in resp.content.lower() or b"error" in resp.content.lower()


@pytest.mark.asyncio
async def test_login_unknown_email_returns_error(portal_client):
    """Login attempt with a non-existent email must return 401."""
    resp = await _login(portal_client, _random_email(), "AnyPass123!")
    assert resp.status_code == 401


# ── Authenticated dashboard ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_authenticated_dashboard_returns_200():
    """After login the dashboard must return 200 (cookie persisted in client)."""
    email = _random_email()
    # Use a single client instance so cookies persist across requests
    async with httpx.AsyncClient(
        base_url=ADMIN_URL, follow_redirects=False, timeout=30.0
    ) as client:
        # Register
        await _signup(client, email, "SecurePass123!")
        # Login — sets cookie in the client jar
        login_resp = await _login(client, email, "SecurePass123!")
        assert login_resp.status_code == 303
        # Dashboard — cookie should be sent automatically
        dash_resp = await client.get("/portal/dashboard")
    assert dash_resp.status_code == 200, (
        f"Authenticated dashboard should return 200, got {dash_resp.status_code}"
    )


@pytest.mark.asyncio
async def test_unauthenticated_dashboard_redirects_to_login(portal_client):
    """GET /portal/dashboard without a session cookie must redirect to /portal/login."""
    resp = await portal_client.get("/portal/dashboard")
    assert resp.status_code == 303, (
        f"Expected 303 redirect to login for unauthenticated request, got {resp.status_code}"
    )
    location = resp.headers.get("location", "")
    assert "/portal/login" in location, (
        f"Expected redirect to /portal/login, got {location!r}"
    )


# ── API key creation via portal ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_portal_create_key_redirects_with_new_key():
    """Creating a key via the portal must redirect to /portal/keys?new_key=sk-...."""
    email = _random_email()
    async with httpx.AsyncClient(
        base_url=ADMIN_URL, follow_redirects=False, timeout=30.0
    ) as client:
        # Register + login
        await _signup(client, email, "SecurePass123!")
        login_resp = await _login(client, email, "SecurePass123!")
        assert login_resp.status_code == 303

        # Create key
        resp = await client.post("/portal/keys", data={"name": "My Integration Key"})

    assert resp.status_code == 303, (
        f"Expected 303 redirect after key creation, got {resp.status_code}"
    )
    location = resp.headers.get("location", "")
    assert "new_key=" in location, (
        f"Redirect location must contain 'new_key=' query param, got {location!r}"
    )
    # Extract the key value from the Location header
    new_key = location.split("new_key=")[-1].split("&")[0]
    assert new_key.startswith("sk-"), (
        f"Portal-created key must start with 'sk-', got {new_key[:15]!r}"
    )


@pytest.mark.asyncio
async def test_portal_keys_page_requires_auth(portal_client):
    """GET /portal/keys without a session must redirect to login."""
    resp = await portal_client.get("/portal/keys")
    assert resp.status_code == 303
    location = resp.headers.get("location", "")
    assert "/portal/login" in location


@pytest.mark.asyncio
async def test_portal_key_creation_requires_auth(portal_client):
    """POST /portal/keys without a session must redirect to login."""
    resp = await portal_client.post("/portal/keys", data={"name": "Sneaky Key"})
    assert resp.status_code == 303
    location = resp.headers.get("location", "")
    assert "/portal/login" in location
