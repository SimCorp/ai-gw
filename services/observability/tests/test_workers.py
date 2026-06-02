import asyncio

from app.bus import InMemoryBus
from app.models import GatewayEvent


async def test_event_reaches_handler():
    bus = InMemoryBus()
    received: list[GatewayEvent] = []

    async def handler(event: GatewayEvent) -> None:
        received.append(event)

    bus.subscribe(handler)
    await bus.start()

    event = GatewayEvent(
        team_id="team-1", model="claude-3-5-sonnet", tokens_input=100, tokens_output=50
    )
    await bus.publish(event)
    await asyncio.sleep(0.05)  # let the dispatch loop run

    await bus.stop()
    assert len(received) == 1
    assert received[0].team_id == "team-1"


async def test_worker_failure_does_not_crash_bus():
    bus = InMemoryBus()

    async def failing_handler(event: GatewayEvent) -> None:
        raise RuntimeError("worker exploded")

    async def good_handler(event: GatewayEvent) -> None:
        pass

    bus.subscribe(failing_handler)
    bus.subscribe(good_handler)
    await bus.start()

    await bus.publish(GatewayEvent(team_id="team-2"))
    await asyncio.sleep(0.05)
    await bus.stop()
    # no exception raised — test passes if we get here
