import secrets

from fastapi import APIRouter, Header, HTTPException, Request

from app.models import GatewayEvent

router = APIRouter()


@router.post("/events", status_code=202)
async def ingest_event(
    event: GatewayEvent,
    request: Request,
    x_internal_key: str | None = Header(default=None),
) -> dict:
    expected = request.app.state.settings.internal_api_key
    if not expected or not secrets.compare_digest(x_internal_key or "", expected):
        raise HTTPException(status_code=401, detail="Invalid internal API key")
    await request.app.state.bus.publish(event)
    return {"accepted": True}
