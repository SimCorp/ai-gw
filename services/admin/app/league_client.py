import httpx

from app.config import settings


async def grant_points(
    *, engineer_id: str, delta: int, reason: str, ref_id: str | None = None
) -> None:
    """Award (or deduct) points via the league internal grant API.

    Raises RuntimeError on non-201 responses so callers can surface a 502
    or silently swallow with try/except depending on whether the grant is
    best-effort or required.
    """
    payload: dict = {"engineer_id": str(engineer_id), "delta": delta, "reason": reason}
    if ref_id is not None:
        payload["ref_id"] = str(ref_id)

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{settings.league_url}/league/internal/points/grant",
            json=payload,
            headers={"X-Admin-Token": settings.admin_token},
        )
    if resp.status_code != 201:
        raise RuntimeError(f"league grant failed: {resp.status_code} {resp.text}")
