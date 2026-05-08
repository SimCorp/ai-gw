from fastapi import APIRouter, Header, HTTPException, Request

from app.models import GatewayEvent

router = APIRouter()


@router.post("/events", status_code=202)
async def ingest_event(
    event: GatewayEvent,
    request: Request,
    x_internal_key: str | None = Header(default=None),
) -> dict:
    import os
    expected = request.app.state.settings.internal_api_key
    key_is_default = expected == "change-me-internal-key"
    is_dev = os.getenv("ENVIRONMENT", "development") in ("development", "test", "ci")
    # Skip auth only in dev when no explicit key is configured; always enforce in prod
    if not (is_dev and key_is_default):
        if x_internal_key != expected:
            raise HTTPException(status_code=401, detail="Invalid internal API key")
    await request.app.state.bus.publish(event)
    return {"accepted": True}
