from fastapi import APIRouter, Request

from app.models import GatewayEvent

router = APIRouter()


@router.post("/events", status_code=202)
async def ingest_event(event: GatewayEvent, request: Request):
    await request.app.state.bus.publish(event)
    return {"accepted": True}
