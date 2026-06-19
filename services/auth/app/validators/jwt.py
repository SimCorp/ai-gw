import asyncio
import ipaddress
import json
import logging
import socket
import time
from urllib.parse import urlparse

import httpx
import jwt
from fastapi import HTTPException

from app.config import Settings

_log = logging.getLogger(__name__)

_jwks_cache: dict = {}
_jwks_cache_expires: float = 0.0
_JWKS_TTL = 3600  # 1 hour in-process cache TTL
_JWKS_REDIS_TTL = 90000  # 25 hours Redis fallback TTL (survives overnight outages)
_JWKS_REDIS_KEY = "jwks:cache"
_jwks_lock = asyncio.Lock()

# Separate cache for admin-issued identity JWTs
_identity_jwks_cache: dict = {}
_identity_jwks_expires: float = 0.0
_IDENTITY_JWKS_REDIS_KEY = "jwks:identity:cache"
_identity_jwks_lock = asyncio.Lock()

_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]

_METADATA_HOSTNAMES = {
    "169.254.169.254",
    "metadata.google.internal",
    "metadata.azure.com",
}


def _oidc_identity(payload: dict) -> str | None:
    """Per-user identity for an Entra OIDC token used as the team/cache key.

    Must be PER-USER, never the tenant-wide ``tid`` claim — ``tid`` is identical
    for every user in the tenant, so using it collapses all SSO callers into one
    cache / rate-limit namespace and leaks cached responses across teams. Prefer
    the immutable per-user object id (``oid``), fall back to the subject
    (``sub``); ``tid`` is intentionally never used.
    """
    return payload.get("oid") or payload.get("sub")


def _validate_jwks_uri(uri: str) -> None:
    parsed = urlparse(uri)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"JWKS URI must use http or https, got {parsed.scheme!r}")
    host = parsed.hostname or ""
    if host.lower() in _METADATA_HOSTNAMES:
        raise ValueError(f"JWKS URI targets a metadata endpoint: {host}")
    try:
        addr = ipaddress.ip_address(host)
        if any(addr in net for net in _PRIVATE_NETS):
            raise ValueError(f"JWKS URI targets a private/loopback address: {host}")
    except ValueError as exc:
        if "JWKS URI" in str(exc):
            raise
        # Not an IP literal — resolve hostname
        try:
            resolved = socket.gethostbyname(host)
            addr = ipaddress.ip_address(resolved)
            if any(addr in net for net in _PRIVATE_NETS):
                raise ValueError(f"JWKS URI resolves to private address {resolved}")
        except socket.gaierror:
            pass


async def _fetch_jwks(settings: Settings) -> dict:
    async with httpx.AsyncClient(follow_redirects=False, timeout=5) as client:
        resp = await client.get(settings.jwks_uri)
        resp.raise_for_status()
        return resp.json()


async def _get_jwks(settings: Settings, redis=None) -> dict:
    """Return JWKS data, with three-tier fallback:
    1. In-process cache (1h TTL) — fastest
    2. Live fetch from IdP  — authoritative
    3. Redis stale copy (25h TTL) — survives IdP restarts and auth-service restarts
    """
    global _jwks_cache, _jwks_cache_expires
    now = time.monotonic()
    if _jwks_cache and now < _jwks_cache_expires:
        return _jwks_cache

    async with _jwks_lock:
        if _jwks_cache and time.monotonic() < _jwks_cache_expires:
            return _jwks_cache

        try:
            data = await _fetch_jwks(settings)
            _jwks_cache = data
            _jwks_cache_expires = time.monotonic() + _JWKS_TTL

            # Persist to Redis so future restarts (and this service's restarts) can survive
            # a brief IdP outage without dropping JWT auth.
            if redis is not None:
                try:
                    await redis.set(_JWKS_REDIS_KEY, json.dumps(data), ex=_JWKS_REDIS_TTL)
                except Exception as e:
                    _log.warning("Failed to persist JWKS to Redis: %s", e)

            return _jwks_cache

        except httpx.HTTPError as exc:
            # IdP unreachable — try Redis fallback before failing
            _log.warning("JWKS fetch failed (%s), trying Redis fallback", exc)
            if redis is not None:
                try:
                    cached = await redis.get(_JWKS_REDIS_KEY)
                    if cached:
                        data = json.loads(cached)
                        # Refresh in-process cache with stale data so we don't hit Redis every request
                        _jwks_cache = data
                        _jwks_cache_expires = time.monotonic() + 300  # short TTL; retry live soon
                        _log.warning("Serving JWKS from Redis stale cache — IdP may be down")
                        return data
                except Exception as e:
                    _log.error("Redis JWKS fallback also failed: %s", e)

            raise HTTPException(status_code=503, detail="JWKS fetch failed")


async def _get_identity_jwks(settings: Settings, redis=None) -> dict:
    """Fetch JWKS from the admin service identity endpoint."""
    global _identity_jwks_cache, _identity_jwks_expires
    now = time.monotonic()
    if _identity_jwks_cache and now < _identity_jwks_expires:
        return _identity_jwks_cache

    async with _identity_jwks_lock:
        if _identity_jwks_cache and time.monotonic() < _identity_jwks_expires:
            return _identity_jwks_cache

        identity_jwks_uri = f"{settings.admin_url}/identity/jwks"
        try:
            async with httpx.AsyncClient(follow_redirects=False, timeout=5) as client:
                resp = await client.get(identity_jwks_uri)
                resp.raise_for_status()
                data = resp.json()
            _identity_jwks_cache = data
            _identity_jwks_expires = time.monotonic() + _JWKS_TTL
            if redis is not None:
                try:
                    await redis.set(_IDENTITY_JWKS_REDIS_KEY, json.dumps(data), ex=_JWKS_REDIS_TTL)
                except Exception:
                    pass
            return _identity_jwks_cache
        except httpx.HTTPError as exc:
            _log.warning("Identity JWKS fetch failed (%s), trying Redis fallback", exc)
            if redis is not None:
                try:
                    cached = await redis.get(_IDENTITY_JWKS_REDIS_KEY)
                    if cached:
                        data = json.loads(cached)
                        _identity_jwks_cache = data
                        _identity_jwks_expires = time.monotonic() + 300
                        return data
                except Exception:
                    pass
            raise HTTPException(status_code=503, detail="Identity JWKS fetch failed")


async def _validate_identity_jwt(token: str, settings: Settings, redis=None) -> dict:
    """Verify an admin-issued identity JWT and extract team_id + capabilities as scopes."""
    import base64 as _b64

    try:
        parts = token.split(".")
        if len(parts) < 2:
            raise HTTPException(status_code=401, detail="Malformed token")
        padding = 4 - len(parts[1]) % 4
        # Decode to validate the token is well-formed; verification happens below.
        json.loads(_b64.urlsafe_b64decode(parts[1] + "=" * padding))
    except Exception:
        raise HTTPException(status_code=401, detail="Malformed token")

    jwks_data = await _get_identity_jwks(settings, redis=redis)
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    key = next((k for k in jwks_data.get("keys", []) if k.get("kid") == kid), None)
    if key is None:
        raise HTTPException(status_code=401, detail="Unknown signing key")

    from jwt import algorithms as jwt_alg

    rsa_key = jwt_alg.RSAAlgorithm.from_jwk(key)
    try:
        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    team_id = payload.get("team_id") or payload.get("tid") or payload.get("sub")
    scopes = payload.get("capabilities") or payload.get("scopes") or ["ai-gw:inference:*"]
    return {
        "team_id": str(team_id) if team_id else None,
        "project_id": payload.get("project_id"),
        "scopes": scopes,
    }


async def validate_jwt(token: str, settings: Settings, redis=None) -> dict:
    """Verify a JWT and return identity dict.

    Routes to identity JWT path when the token carries a 'capabilities' claim
    (admin-issued agent tokens). Falls back to OIDC path for Dex/Entra tokens.
    """
    import base64 as _b64

    try:
        parts = token.split(".")
        if len(parts) >= 2:
            padding = 4 - len(parts[1]) % 4
            unverified = json.loads(_b64.urlsafe_b64decode(parts[1] + "=" * padding))
            if "capabilities" in unverified or "scopes" in unverified:
                return await _validate_identity_jwt(token, settings, redis=redis)
    except Exception:
        pass  # fall through to OIDC path

    global _jwks_cache, _jwks_cache_expires
    try:
        jwks_data = await _get_jwks(settings, redis=redis)

        # Find the matching key by kid
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        key = next((k for k in jwks_data.get("keys", []) if k.get("kid") == kid), None)

        # Unknown kid — keys may have rotated; refresh once and retry.
        if key is None:
            async with _jwks_lock:
                data = await _fetch_jwks(settings)
                _jwks_cache = data
                _jwks_cache_expires = time.monotonic() + _JWKS_TTL
                if redis is not None:
                    try:
                        await redis.set(_JWKS_REDIS_KEY, json.dumps(data), ex=_JWKS_REDIS_TTL)
                    except Exception:
                        pass
            key = next((k for k in _jwks_cache.get("keys", []) if k.get("kid") == kid), None)
        if key is None:
            raise HTTPException(status_code=401, detail="Unknown signing key")

        # Build a PyJWT signing key from the JWK
        from jwt import algorithms as jwt_alg

        rsa_key = jwt_alg.RSAAlgorithm.from_jwk(key)

        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=["RS256"],
            audience=settings.entra_client_id,
            options={"verify_at_hash": False},
        )
        return {
            "team_id": _oidc_identity(payload),
            "project_id": payload.get("project_id"),
        }
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="JWKS fetch failed")
