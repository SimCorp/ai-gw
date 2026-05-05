import asyncio

import httpx
from fastapi import APIRouter

from app.config import settings

router = APIRouter(prefix="/system", tags=["system"])

_SERVICES = {
    "auth": settings.auth_url,
    "cache": settings.cache_url,
    "litellm": settings.litellm_url,
    "observability": settings.observability_url,
}


@router.get("/health")
async def system_health():
    async def check(name: str, url: str) -> dict:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                resp = await client.get(f"{url}/health")
                return {"service": name, "status": "ok" if resp.is_success else "degraded", "code": resp.status_code}
        except Exception as exc:
            return {"service": name, "status": "unreachable", "error": str(exc)}

    results = await asyncio.gather(*[check(n, u) for n, u in _SERVICES.items()])
    overall = "ok" if all(r["status"] == "ok" for r in results) else "degraded"
    return {"overall": overall, "services": results}
