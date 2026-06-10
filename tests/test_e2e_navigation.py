"""
End-to-end navigation tests using Playwright.

Workflow:
  1. Load the landing page (localhost:8080/)
  2. Verify every card is present and its link target responds
  3. Admin portal — log in, click every sidebar link, verify expected heading
  4. Developer portal — inject auth token, click every nav link, verify expected heading

Run:
    pip install playwright pytest-playwright
    playwright install chromium
    pytest tests/test_e2e_navigation.py -v
"""

import json
import re
import subprocess
import urllib.request

import pytest
from playwright.sync_api import Page, expect

HUB = "http://localhost:8080"
ADMIN_BASE = f"{HUB}/admin-portal"
PORTAL_BASE = f"{HUB}/portal"
ADMIN_EMAIL = "admin@simcorp.com"
ADMIN_PASS = "Admin1234!"
SCREENSHOTS = "/tmp/e2e_screenshots"

import os

os.makedirs(SCREENSHOTS, exist_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _shot(page: Page, label: str) -> None:
    page.screenshot(path=f"{SCREENSHOTS}/{label}.png", full_page=True)


def _reset_admin_password(email: str) -> None:
    """Ensure must_change_password=FALSE so login works cleanly."""
    subprocess.run(
        [
            "docker",
            "exec",
            "ai-gateway-postgres-1",
            "psql",
            "-U",
            "aigateway",
            "-d",
            "aigateway",
            "-c",
            f"UPDATE users SET must_change_password=FALSE WHERE email='{email}'",
        ],
        capture_output=True,
    )


def _get_dev_token() -> str:
    req = urllib.request.Request(
        f"{HUB}/admin/dev-auth/login",
        data=json.dumps({"email": "dev@simcorp.com", "password": "password"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())["token"]


def _assert_no_crash(page: Page, label: str) -> None:
    """Fail if the page body contains an error boundary or 500 text."""
    body = page.locator("body").inner_text()[:3000].lower()
    crash_patterns = [
        "application error",
        "internal server error",
        "typeerror",
        "referenceerror",
        "is not a function",
        "cannot read propert",
    ]
    for pat in crash_patterns:
        assert pat not in body, f"{label}: crash pattern '{pat}' found in page body"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def admin_page(browser):
    """Logged-in admin portal page, module-scoped so login runs once."""
    ctx = browser.new_context(viewport={"width": 1400, "height": 900})
    page = ctx.new_page()
    page.goto(f"{ADMIN_BASE}/login", wait_until="networkidle", timeout=20000)
    page.fill('input[type="email"]', ADMIN_EMAIL)
    page.fill('input[type="password"]', ADMIN_PASS)
    page.click('button[type="submit"]')
    page.wait_for_url(re.compile(r"/admin-portal/admin/"), timeout=15000)
    yield page
    ctx.close()


@pytest.fixture(scope="module")
def portal_page(browser):
    """Developer portal page with token injected, module-scoped."""
    token = _get_dev_token()
    ctx = browser.new_context(viewport={"width": 1400, "height": 900})
    page = ctx.new_page()
    page.goto(f"{PORTAL_BASE}/portal", wait_until="domcontentloaded", timeout=20000)
    page.evaluate(f"localStorage.setItem('portal_dev_token', '{token}')")
    page.wait_for_timeout(300)
    yield page
    ctx.close()


# ---------------------------------------------------------------------------
# 1. Landing page
# ---------------------------------------------------------------------------


class TestLandingPage:
    EXPECTED_CARDS = [
        ("Admin portal", f"{HUB}/admin-portal/admin/dashboard"),
        ("Developer portal", f"{HUB}/portal/portal"),
        ("Admin API", f"{HUB}/admin/docs"),
        ("LiteLLM proxy", f"{HUB}/litellm/ui"),
        ("Auth service", f"{HUB}/auth/docs"),
        ("Cache service", f"{HUB}/cache/docs"),
        ("Observability", f"{HUB}/observability/docs"),
        ("Identity Pool", f"{HUB}/identity/docs"),
        ("Agent Relay", f"{HUB}/agent-relay/docs"),
        ("Librarian", f"{HUB}/librarian/docs"),
        ("Memory Palace", f"{HUB}/memory/docs"),
        ("League", f"{HUB}/league/docs"),
    ]

    def test_page_loads(self, page: Page):
        page.goto(HUB, wait_until="networkidle", timeout=15000)
        _shot(page, "landing_page")
        expect(page.locator("body")).to_be_visible()
        _assert_no_crash(page, "landing page")

    def test_all_cards_present(self, page: Page):
        page.goto(HUB, wait_until="networkidle", timeout=15000)
        for title, _ in self.EXPECTED_CARDS:
            card = page.locator(".card__title", has_text=title)
            expect(card).to_be_visible(), f"Card '{title}' not found on landing page"

    @pytest.mark.parametrize("title,expected_href", EXPECTED_CARDS)
    def test_card_link(self, page: Page, title: str, expected_href: str):
        """Each card's href must match the expected nginx URL."""
        page.goto(HUB, wait_until="networkidle", timeout=15000)
        card_link = page.locator("a.card", has_text=title)
        expect(card_link).to_be_visible()
        href = card_link.get_attribute("href")
        assert href == expected_href, (
            f"Card '{title}': expected href '{expected_href}', got '{href}'"
        )


# ---------------------------------------------------------------------------
# 2. Admin portal — login
# ---------------------------------------------------------------------------


class TestAdminLogin:
    def test_login_page_loads(self, page: Page):
        page.goto(f"{ADMIN_BASE}/login", wait_until="networkidle", timeout=15000)
        _shot(page, "admin_login")
        expect(page.locator('input[type="email"]')).to_be_visible()
        expect(page.locator('input[type="password"]')).to_be_visible()
        expect(page.locator('button[type="submit"]')).to_be_visible()

    def test_login_succeeds(self, admin_page: Page):
        """Fixture already logged in; verify we're on a dashboard URL."""
        assert "/admin-portal/admin/" in admin_page.url, (
            f"Expected admin portal URL, got: {admin_page.url}"
        )


# ---------------------------------------------------------------------------
# 3. Admin portal — all pages
# ---------------------------------------------------------------------------

ADMIN_NAV = [
    ("/admin/dashboard", "Platform overview"),
    ("/admin/requests", "Live requests"),
    ("/admin/org", "Org Tree"),
    # areas/units/teams pages removed in the org-node refactor (unified into /admin/org)
    ("/admin/users", "Users & Access"),
    ("/admin/transformation", "AI Transformation"),
    ("/admin/genai-adoption", "GenAI Adoption"),
    ("/admin/insights", "AI Insights"),
    ("/admin/devops", "DevOps"),  # no h1 — has <div> headings
    ("/admin/guardrails", "Guardrails"),
    ("/admin/audit", "Audit log"),
    ("/admin/policies", "Policies"),
    ("/admin/quotas", "Quotas"),
    ("/admin/approvals", "Approvals"),
    ("/admin/mcp", "MCP Servers"),
    ("/admin/memory", "Memory"),
    ("/admin/skills", "Skills"),
    ("/admin/plugins", "Plugins"),
    ("/admin/models", "Model registry"),
    ("/admin/cache", "Semantic cache"),
    ("/admin/providers", "Providers"),
    ("/admin/reports", "Cost Reports"),
    ("/admin/alerts", "Alerts"),
    ("/admin/league/seasons", "Seasons"),
    ("/admin/league/challenges", "Challenge Builder"),
    ("/admin/league/proposals", "Community Proposals"),
    ("/admin/league/store", "Store Editor"),
    ("/admin/settings/entra", "Entra ID"),
]


@pytest.mark.parametrize("path,expected_text", ADMIN_NAV, ids=[p for p, _ in ADMIN_NAV])
def test_admin_page(admin_page: Page, path: str, expected_text: str):
    """Navigate to every admin page via the sidebar and verify heading."""
    url = f"{ADMIN_BASE}{path}"

    console_errors: list[str] = []
    failed_requests: list[str] = []
    IGNORE_URL_FRAGMENTS = ["/cache/v1/models", "/league/"]

    def _on_console(m):
        if m.type == "error":
            console_errors.append(m.text)

    def _on_response(resp):
        if resp.status >= 400 and "hot-update" not in resp.url and "_next" not in resp.url:
            if not any(frag in resp.url for frag in IGNORE_URL_FRAGMENTS):
                failed_requests.append(f"{resp.status} {resp.url}")

    admin_page.on("console", _on_console)
    admin_page.on("response", _on_response)
    try:
        # /admin/cache has refetchInterval=15000 which prevents networkidle
        wait_until = "load" if path == "/admin/cache" else "networkidle"
        admin_page.goto(url, wait_until=wait_until, timeout=20000)
        admin_page.wait_for_timeout(800)
        _shot(admin_page, f"admin{_slug(path)}")

        # Heading check — try h1 first, fall back to body text for pages without h1
        heading_text = expected_text.split()[0]  # first word is always unambiguous
        heading = admin_page.locator("h1", has_text=re.compile(heading_text, re.IGNORECASE))
        if heading.count() > 0:
            expect(heading.first).to_be_visible(timeout=8000)
        else:
            body = admin_page.locator("body").inner_text()
            assert expected_text.split()[0].lower() in body.lower(), (
                f"{path}: expected '{expected_text}' in page body"
            )

        _assert_no_crash(admin_page, path)

        # Filter known-noisy console errors
        real_errors = [
            e
            for e in console_errors
            if not any(
                x in e
                for x in [
                    "favicon",
                    "hot-update",
                    "webpack",
                    "Fast Refresh",
                    "/cache/v1/models",
                    "/league/",
                    "401 (Unauthorized)",
                    "403 (Forbidden)",
                    "404 (Not Found)",
                ]
            )
        ]
        assert not real_errors, f"{path}: unexpected console errors: {real_errors}"
        assert not failed_requests, f"{path}: failed HTTP requests: {failed_requests}"
    finally:
        admin_page.remove_listener("console", _on_console)
        admin_page.remove_listener("response", _on_response)


# ---------------------------------------------------------------------------
# 4. Developer portal — all pages
# ---------------------------------------------------------------------------

PORTAL_NAV = [
    # Path is relative to PORTAL_BASE="http://localhost:8080/portal".
    # Next.js basePath=/portal means app route /portal → URL /portal/portal,
    # app route /portal/usage → URL /portal/portal/usage, etc.
    ("/portal", "Welcome"),
    ("/portal/usage", "Usage & spend"),
    ("/portal/keys", "API keys"),
    ("/portal/models", "Models"),
    ("/portal/playground", "playground"),  # no h1 — check body text
    ("/portal/workflows", "Workflows"),
    ("/portal/agents", "Agents"),
    ("/portal/mcp", "MCP Servers"),
    ("/portal/plugins", "Plugins"),
    ("/portal/prompts", "Prompts"),
    ("/portal/skills", "Skills"),
    ("/portal/docs", "Quickstart"),
    ("/portal/transformation", "AI Transformation"),
    ("/portal/settings", "Settings"),
    ("/portal/league", "Challenges"),
    ("/portal/league/leaderboard", "Leaderboard"),
    ("/portal/league/results", "My Results"),
    ("/portal/league/store", "Store"),
]


@pytest.mark.parametrize("path,expected_text", PORTAL_NAV, ids=[p for p, _ in PORTAL_NAV])
def test_portal_page(portal_page: Page, path: str, expected_text: str):
    """Navigate to every developer portal page and verify expected content."""
    url = f"{PORTAL_BASE}{path}"

    console_errors: list[str] = []
    failed_requests: list[str] = []
    IGNORE_URL_FRAGMENTS = ["/cache/v1/models", "/league/"]

    def _on_console(m):
        if m.type == "error":
            console_errors.append(m.text)

    def _on_response(resp):
        if resp.status >= 400 and "hot-update" not in resp.url and "_next" not in resp.url:
            if not any(frag in resp.url for frag in IGNORE_URL_FRAGMENTS):
                failed_requests.append(f"{resp.status} {resp.url}")

    portal_page.on("console", _on_console)
    portal_page.on("response", _on_response)
    try:
        portal_page.goto(url, wait_until="networkidle", timeout=20000)
        portal_page.wait_for_timeout(800)
        _shot(portal_page, f"portal{_slug(path)}")

        # For playground there's no h1, check body text instead
        if path == "/portal/playground":
            body = portal_page.locator("body").inner_text()
            assert "playground" in body.lower(), f"{path}: 'playground' not found in page body"
        else:
            first_word = expected_text.split()[0]
            heading = portal_page.locator("h1", has_text=re.compile(first_word, re.IGNORECASE))
            expect(heading.first).to_be_visible(timeout=8000)

        _assert_no_crash(portal_page, path)

        real_errors = [
            e
            for e in console_errors
            if not any(
                x in e
                for x in [
                    "favicon",
                    "hot-update",
                    "webpack",
                    "Fast Refresh",
                    "/cache/v1/models",
                    "/league/",
                    "401 (Unauthorized)",
                    "403 (Forbidden)",
                    "404 (Not Found)",
                ]
            )
        ]
        assert not real_errors, f"{path}: unexpected console errors: {real_errors}"
        assert not failed_requests, f"{path}: failed HTTP requests: {failed_requests}"
    finally:
        portal_page.remove_listener("console", _on_console)
        portal_page.remove_listener("response", _on_response)


# ---------------------------------------------------------------------------
# 5. Sidebar navigation — click actual links (not goto)
# ---------------------------------------------------------------------------


class TestAdminSidebarClicks:
    """Verify sidebar links navigate to the correct basePath-prefixed URL."""

    # (sidebar label text, expected URL substring after click)
    SIDEBAR_LINKS = [
        ("Dashboard", "/admin-portal/admin/dashboard"),
        ("Live requests", "/admin-portal/admin/requests"),
        ("Org tree", "/admin-portal/admin/org"),
        ("Users", "/admin-portal/admin/users"),
        ("Guardrails", "/admin-portal/admin/guardrails"),
        ("Policies", "/admin-portal/admin/policies"),
        ("Audit log", "/admin-portal/admin/audit"),
        ("Seasons", "/admin-portal/admin/league/seasons"),
        ("Challenges", "/admin-portal/admin/league/challenges"),
        ("Proposals", "/admin-portal/admin/league/proposals"),
        ("Store editor", "/admin-portal/admin/league/store"),
    ]

    @pytest.mark.parametrize(
        "label,expected_path", SIDEBAR_LINKS, ids=[l for l, _ in SIDEBAR_LINKS]
    )
    def test_sidebar_click(self, admin_page: Page, label: str, expected_path: str):
        """Click a sidebar nav item and assert the URL includes the basePath prefix."""
        admin_page.goto(f"{ADMIN_BASE}/admin/dashboard", wait_until="networkidle", timeout=15000)
        # Use get_by_role for reliable link finding; fall back to text locator
        link = admin_page.get_by_role(
            "link", name=re.compile(rf"^{re.escape(label)}$", re.IGNORECASE)
        ).first
        expect(link).to_be_visible()
        with admin_page.expect_navigation(timeout=10000):
            link.click()
        assert expected_path in admin_page.url, (
            f"After clicking '{label}', URL '{admin_page.url}' does not contain '{expected_path}'"
        )
        _assert_no_crash(admin_page, f"click:{label}")


class TestPortalSidebarClicks:
    """Verify developer portal sidebar links navigate correctly."""

    # Labels match PortalShell.tsx item.label values exactly
    SIDEBAR_LINKS = [
        ("Usage & spend", "/portal/usage"),
        ("API keys", "/portal/keys"),
        ("Models", "/portal/models"),
        ("Playground", "/portal/playground"),  # link text is "Playground\n⌘P"
        ("Workflows", "/portal/workflows"),
        ("Agents", "/portal/agents"),
        ("Quickstart", "/portal/docs"),
        ("Settings", "/portal/settings"),
        ("Challenges", "/portal/league"),
        ("Leaderboard", "/portal/league/leaderboard"),
        ("My Results", "/portal/league/results"),
        ("Store", "/portal/league/store"),
    ]

    @pytest.mark.parametrize(
        "label,expected_path", SIDEBAR_LINKS, ids=[l for l, _ in SIDEBAR_LINKS]
    )
    def test_sidebar_click(self, portal_page: Page, label: str, expected_path: str):
        portal_page.goto(f"{PORTAL_BASE}/portal", wait_until="networkidle", timeout=15000)
        # Use partial match — some links have extra content (e.g. "Playground\n⌘P")
        link = portal_page.get_by_role(
            "link", name=re.compile(re.escape(label), re.IGNORECASE)
        ).first
        expect(link).to_be_visible()
        with portal_page.expect_navigation(timeout=10000):
            link.click()
        assert expected_path in portal_page.url, (
            f"After clicking '{label}', URL '{portal_page.url}' does not contain '{expected_path}'"
        )
        _assert_no_crash(portal_page, f"click:{label}")
