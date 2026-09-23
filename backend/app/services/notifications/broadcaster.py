"""In-process pub/sub feeding the dashboard's Server-Sent Events stream."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class Broadcaster:
    def __init__(self, max_queue: int = 100) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._max_queue = max_queue

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def publish(self, event: dict[str, Any]) -> int:
        """Fan out to every live viewer; must be called on the event loop."""
        delivered = 0
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
                delivered += 1
            except asyncio.QueueFull:
                logger.warning("Dropping SSE event for a slow subscriber")
        return delivered


broadcaster = Broadcaster()
