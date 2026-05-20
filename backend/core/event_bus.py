import asyncio, logging, time
from typing import Callable, Any
log = logging.getLogger("jarvis.eventbus")

class EventBus:
    def __init__(self):
        self._handlers: dict[str, list[Callable]] = {}
        self._history: list[dict] = []
        self._max_history = 1000

    def on(self, event: str, handler: Callable):
        self._handlers.setdefault(event, []).append(handler)
        return self

    async def emit(self, event: str, data: Any = None):
        entry = {"event": event, "data": data, "ts": time.time()}
        self._history.append(entry)
        if len(self._history) > self._max_history:
            self._history.pop(0)
        for h in self._handlers.get(event, []) + self._handlers.get("*", []):
            try:
                if asyncio.iscoroutinefunction(h):
                    asyncio.create_task(h(data))
                else:
                    h(data)
            except Exception as e:
                log.error("[EVENT_BUS] Erro em %s: %s", event, e)

    def get_history(self, event: str = None, limit: int = 50) -> list:
        h = [e for e in self._history if not event or e["event"] == event]
        return h[-limit:]

    def get_stats(self) -> dict:
        from collections import Counter
        counts = Counter(e["event"] for e in self._history)
        return {"total_events": len(self._history), "by_type": dict(counts)}

_bus = None
def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
