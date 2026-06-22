"""Caller authentication for the graphify query + management surface.

Graphs of private repos are sensitive, so unlike librarian *every* content and
listing endpoint requires a valid `sk-*` Bearer that validates against the auth
service. This is access gating only — no per-caller row scoping. Mirrors
librarian's resolve_caller() → auth /validate pattern.
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings

_log = logging.getLogger(__name__)


class AuthError(Exception):
    """A caller token could not be validated. `status_code` is the HTTP status
    the REST surface should return; the JSON-RPC surface maps it to -32000."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


async def _validate(token: str) -> int:
    """POST the token to the auth service; return its HTTP status code.

    Network failure → 503 (surfaced as service_unavailable).
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{settings.auth_url}/validate",
                json={"token": token, "model": ""},
            )
        return resp.status_code
    except httpx.RequestError as exc:
        _log.warning("auth /validate unreachable: %s", exc)
        return 503


async def resolve_caller(request) -> None:
    """Validate the Bearer sk-* token on a request.

    Raises AuthError(401) when missing/invalid, AuthError(429) when rate-limited,
    AuthError(503) when the auth service is unreachable. Returns None on success.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise AuthError(401, "unauthorized")
    token = auth_header[len("Bearer ") :]

    status = await _validate(token)
    if status == 200:
        return None
    if status == 429:
        raise AuthError(429, "rate_limit_exceeded")
    if status == 503:
        raise AuthError(503, "service_unavailable")
    raise AuthError(401, "unauthorized")
