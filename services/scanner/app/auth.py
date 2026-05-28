import time
from typing import Any
import httpx
from fastapi import Request, HTTPException
from app.config import settings

_auth_cache: dict[str, tuple[dict, float]] = {}
_CACHE_TTL = 45.0


async def validate_token(request: Request, token: str) -> dict[str, Any]:
    cached = _auth_cache.get(token)
    if cached and (time.monotonic() - cached[1]) < _CACHE_TTL:
        return cached[0]
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{settings.auth_url}/validate",
                headers={
                    "Authorization": f"Bearer {token}",
                    "x-internal-key": settings.internal_api_key,
                },
            )
        if resp.status_code in (401, 403):
            _auth_cache.pop(token, None)
            raise HTTPException(status_code=401, detail="Unauthorized")
        resp.raise_for_status()
        identity = resp.json()
        _auth_cache[token] = (identity, time.monotonic())
        return identity
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Auth service unavailable")


async def get_identity(request: Request) -> dict[str, Any]:
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return await validate_token(request, token)


def require_worker_auth(request: Request) -> None:
    auth_header = request.headers.get("Authorization", "")
    secret = auth_header.removeprefix("Bearer ").strip()
    if secret != settings.scanner_worker_secret:
        raise HTTPException(status_code=403, detail="Forbidden")
