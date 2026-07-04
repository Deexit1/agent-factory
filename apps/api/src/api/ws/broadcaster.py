import asyncio
from collections import defaultdict

# In-process pub/sub for ticket_events. Fine for a single API replica; once the API
# scales horizontally this needs to move to Redis pub/sub per docs/06-tech-stack.md.


class TicketEventBroadcaster:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, object]]]] = defaultdict(set)
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self, ticket_id: str) -> asyncio.Queue[dict[str, object]]:
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
        self._subscribers[ticket_id].add(queue)
        return queue

    def unsubscribe(self, ticket_id: str, queue: asyncio.Queue[dict[str, object]]) -> None:
        self._subscribers[ticket_id].discard(queue)

    def publish(self, ticket_id: str, payload: dict[str, object]) -> None:
        """Thread-safe: callable from the sync worker thread FastAPI runs routes in."""
        if self._loop is None:
            return
        for queue in self._subscribers.get(ticket_id, ()):
            self._loop.call_soon_threadsafe(queue.put_nowait, payload)


broadcaster = TicketEventBroadcaster()
