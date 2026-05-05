import asyncio
from abc import ABC, abstractmethod
from typing import Awaitable, Callable

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

    _SUBSCRIPTION = "gateway-workers"

    def __init__(self, connection_string: str, topic: str) -> None:
        self._conn = connection_string
        self._topic = topic
        self._handlers: list[Handler] = []
        self._sender = None
        self._client = None
        self._consumer_task: asyncio.Task | None = None

    def subscribe(self, handler: Handler) -> None:
        self._handlers.append(handler)

    async def publish(self, event: GatewayEvent) -> None:
        from azure.servicebus import ServiceBusMessage

        await self._sender.send_messages(ServiceBusMessage(event.model_dump_json()))

    async def start(self) -> None:
        from azure.servicebus.aio import ServiceBusClient

        self._client = ServiceBusClient.from_connection_string(self._conn)
        self._sender = self._client.get_topic_sender(self._topic)
        await self._sender.__aenter__()
        self._consumer_task = asyncio.create_task(self._consume())

    async def stop(self) -> None:
        if self._consumer_task:
            self._consumer_task.cancel()
        if self._sender:
            await self._sender.__aexit__(None, None, None)
        if self._client:
            await self._client.__aexit__(None, None, None)

    async def _consume(self) -> None:
        from azure.servicebus.aio import ServiceBusClient

        async with ServiceBusClient.from_connection_string(self._conn) as client:
            async with client.get_subscription_receiver(
                self._topic, self._SUBSCRIPTION
            ) as receiver:
                async for msg in receiver:
                    try:
                        event = GatewayEvent.model_validate_json(str(msg))
                        for handler in self._handlers:
                            try:
                                await handler(event)
                            except Exception:
                                pass
                        await receiver.complete_message(msg)
                    except Exception:
                        await receiver.abandon_message(msg)


def make_bus(settings) -> EventBus:
    if settings.bus_provider == "servicebus" and settings.azure_service_bus_connection_string:
        return ServiceBusBus(
            settings.azure_service_bus_connection_string,
            settings.azure_service_bus_topic,
        )
    return InMemoryBus()
