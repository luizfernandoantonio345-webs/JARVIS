"""
autonomy/controller.py — Simple autonomy controller stub.
Provides get_autonomy_controller() used by routes/autonomy.py
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone


class _AutonomyController:
    """Minimal autonomy controller."""

    def __init__(self) -> None:
        self._state = "idle"
        self._started_at: str | None = None
        self._events_today = 0
        self._actions_taken = 0
        self._last_action: str | None = None

    async def start(self) -> None:
        self._state = "running"
        self._started_at = datetime.now(timezone.utc).isoformat()

    async def pause(self) -> None:
        self._state = "paused"

    async def resume(self) -> None:
        self._state = "running"

    async def stop(self) -> None:
        self._state = "idle"

    async def confirm(self, confirm_id: str) -> None:
        pass

    def status_dict(self) -> dict:
        return {
            "state": self._state,
            "started_at": self._started_at,
            "events_today": self._events_today,
            "actions_taken": self._actions_taken,
            "last_action": self._last_action,
        }

    def log_entries(self, limit: int = 50) -> list:
        return []


_instance: _AutonomyController | None = None


def get_autonomy_controller() -> _AutonomyController:
    global _instance
    if _instance is None:
        _instance = _AutonomyController()
    return _instance
