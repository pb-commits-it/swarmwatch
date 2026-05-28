"""In-process pub/sub hub for live SSE broadcast.

Each `/api/live` subscriber gets its own asyncio.Queue; `/v1/traces` ingests push
events through `publish()`. Slow subscribers don't block ingest — their queue
just drops the overflow.
"""

from __future__ import annotations

import asyncio


class LiveHub:
    def __init__(self) -> None:
        self._subs: set[asyncio.Queue[tuple[str, dict]]] = set()

    def subscribe(self, maxsize: int = 1024) -> asyncio.Queue[tuple[str, dict]]:
        q: asyncio.Queue[tuple[str, dict]] = asyncio.Queue(maxsize=maxsize)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def subscriber_count(self) -> int:
        return len(self._subs)

    async def publish(self, event: str, data: dict) -> None:
        for q in list(self._subs):
            try:
                q.put_nowait((event, data))
            except asyncio.QueueFull:
                # drop oldest, push newest
                try:
                    q.get_nowait()
                    q.put_nowait((event, data))
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass
