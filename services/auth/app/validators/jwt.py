import httpx
from fastapi import HTTPException
from jose import JWTError, jwt

from app.config import Settings

_jwks_cache: dict = {}


async def _fetch_jwks(settings: Settings) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(settings.jwks_uri, timeout=5)
        resp.raise_for_status()
        return resp.json()


async def validate_jwt(token: str, settings: Settings) -> dict:
    """Fetch JWKS, verify token signature + claims, return {team_id, project_id}."""
    global _jwks_cache
    try:
        if not _jwks_cache:
            _jwks_cache = await _fetch_jwks(settings)

        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        key = next((k for k in _jwks_cache.get("keys", []) if k.get("kid") == kid), None)

        # Unknown kid — keys may have rotated; refresh once and retry.
        if key is None:
            _jwks_cache = await _fetch_jwks(settings)
            key = next((k for k in _jwks_cache.get("keys", []) if k.get("kid") == kid), None)
        if key is None:
            raise HTTPException(status_code=401, detail="Unknown signing key")

        payload = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.entra_client_id,
            options={"verify_at_hash": False},
        )
        return {
            "team_id": payload.get("tid") or payload.get("sub"),
            "project_id": payload.get("project_id"),
        }
    except JWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"JWKS fetch failed: {exc}") from exc
