"""In-process fan-out of live delivery messages to WebSocket subscribers.

Sync request handlers run in worker threads, so `publish` hands each message to the event
loop with `call_soon_threadsafe`. This works for a single API process. Running several
instances needs a shared channel (PostgreSQL LISTEN/NOTIFY or Redis pub/sub) feeding the
same `publish`; see docs/architecture.md.
"""

import asyncio
import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)
QUEUE_SIZE = 32  # a slow client loses the oldest messages, never blocks the others


class TrackingHub:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: dict[uuid.UUID, set[asyncio.Queue]] = {}

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        """Called at startup with the server's event loop."""
        self._loop = loop

    def subscribe(self, delivery_id: uuid.UUID) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._subscribers.setdefault(delivery_id, set()).add(queue)
        return queue

    def unsubscribe(self, delivery_id: uuid.UUID, queue: asyncio.Queue) -> None:
        queues = self._subscribers.get(delivery_id)
        if queues is not None:
            queues.discard(queue)
            if not queues:
                del self._subscribers[delivery_id]

    def subscriber_count(self, delivery_id: uuid.UUID) -> int:
        return len(self._subscribers.get(delivery_id, ()))

    def publish(self, delivery_id: uuid.UUID, message: dict[str, Any]) -> None:
        """Thread-safe. Messages published before startup (or without listeners) are dropped."""
        if self._loop is None or self._loop.is_closed():
            return
        self._loop.call_soon_threadsafe(self._fan_out, delivery_id, message)

    def _fan_out(self, delivery_id: uuid.UUID, message: dict[str, Any]) -> None:
        for queue in list(self._subscribers.get(delivery_id, ())):
            if queue.full():
                queue.get_nowait()  # drop the oldest
            queue.put_nowait(message)
