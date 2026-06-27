"""Public tier-status endpoint — unauthenticated, no error detail leaked."""

import asyncio
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter

router = APIRouter(tags=["status"])

# Full probe URLs per service. Tier 0 drives overall health.
_TIER_DEFS = [
    {
        "tier": "0",
        "name": "critical",
        "description": "Inference path — AI calls require all to be healthy",
        "services": [
            ("auth", "http://auth:8001/health"),
            ("cache", "http://cache:8002/health"),
            ("litellm", "http://litellm:8003/health/liveliness"),
        ],
    },
    {
        "tier": "1",
        "name": "important",
        "description": "User-facing — AI calls still work when degraded",
        "services": [
            ("admin", "http://admin:8005/health"),
            ("observability", "http://observability:8004/health"),
            ("portal", "http://portal:3002/"),
            ("admin-portal", "http://admin-portal:3001/admin/login"),
        ],
    },
    {
        "tier": "2",
        "name": "background",
        "description": "Optional — handle 503 gracefully",
        "services": [
            ("identity", "http://identity:8006/health"),
            ("agent-relay", "http://agent-relay:8007/health"),
            ("librarian", "http://librarian:8008/health"),
            ("memory", "http://memory:8009/health"),
            ("league", "http://league:8010/health"),
            ("graphify", "http://graphify:8012/health"),
            ("scanner", "http://scanner:8011/health"),
        ],
    },
]


async def _probe(name: str, url: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await asyncio.wait_for(client.get(url), timeout=3.0)
        status = "ok" if resp.is_success else "degraded"
    except Exception:
        status = "unreachable"
    return {"name": name, "status": status}


@router.get("/status")
async def public_status() -> dict:
    """Tier-classified service status — unauthenticated, no error detail."""
    flat = [
        (name, url, tier_def["tier"])
        for tier_def in _TIER_DEFS
        for name, url in tier_def["services"]
    ]
    results = await asyncio.gather(*[_probe(name, url) for name, url, _ in flat])

    overall = "ok"
    tiers_out: dict = {}
    idx = 0
    for tier_def in _TIER_DEFS:
        n = len(tier_def["services"])
        tier_services = list(results[idx : idx + n])
        idx += n
        tier_status = "ok" if all(s["status"] == "ok" for s in tier_services) else "degraded"
        if tier_def["tier"] == "0" and tier_status != "ok":
            overall = "degraded"
        tiers_out[tier_def["tier"]] = {
            "name": tier_def["name"],
            "description": tier_def["description"],
            "status": tier_status,
            "services": tier_services,
        }

    return {
        "overall": overall,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tiers": tiers_out,
    }
