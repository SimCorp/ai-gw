import asyncio
from abc import ABC, abstractmethod
from typing import Callable, Awaitable

from app.models import GatewayEvent


Handler = Callable[[GatewayEvent], Awaitable[None]]


class EventBus(ABC):
    @abstractmethod
    async def publish(self, event: GatewayEvent) -> None: ...

    @abstractmethod
    def subscribe(self, handler: Handler) -> None: ...

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


class InMemoryBus(EventBus):
    def __init__(self) -> None:
        self._queue: asyncio.Queue[GatewayEvent] = asyncio.Queue()
        self._handlers: list[Handler] = []
        self._task: asyncio.Task | None = None

    def subscribe(self, handler: Handler) -> None:
        self._handlers.append(handler)

    async def publish(self, event: GatewayEvent) -> None:
        await self._queue.put(event)

    async def start(self) -> None:
        self._task = asyncio.create_task(self._dispatch())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def _dispatch(self) -> None:
        while True:
            event = await self._queue.get()
            for handler in self._handlers:
                try:
                    await handler(event)
                except Exception:
                    pass  # worker failure must not crash the bus
            self._queue.task_done()


class ServiceBusBus(EventBus):
    """Azure Service Bus implementation. Requires azure-servicebus installed."""

    def __init__(self, connection_string: str, topic: str) -> None:
        self._conn = connection_string
        self._topic = topic
        self._handlers: list[Handler] = []

    def subscribe(self, handler: Handler) -> None:
        self._handlers.append(handler)

    async def publish(self, event: GatewayEvent) -> None:
        from azure.servicebus.aio import ServiceBusClient
        from azure.servicebus import ServiceBusMessage

        async with ServiceBusClient.from_connection_string(self._conn) as client:
            async with client.get_topic_sender(self._topic) as sender:
                await sender.send_messages(ServiceBusMessage(event.model_dump_json()))

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


def make_bus(settings) -> EventBus:
    if settings.bus_provider == "servicebus" and settings.azure_service_bus_connection_string:
        return ServiceBusBus(
            settings.azure_service_bus_connection_string,
            settings.azure_service_bus_topic,
        )
    return InMemoryBus()
