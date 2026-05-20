"""
Activity Tracker — records user commands and patterns.
Data is used ONLY for suggestion generation, NOT for execution decisions.
"""
from __future__ import annotations

import asyncio
import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from backend.core.logger import log_autonomy

# Persisted to disk so patterns survive restarts
_STORAGE = Path(__file__).parent.parent / "reports" / "activity_log.jsonl"


class ActivityTracker:
    """
    In-memory activity log with optional disk persistence.
    Thread-safe via asyncio.Lock.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._file_lock = asyncio.Lock()  # Bug #6: dedicated lock for file I/O
        self._entries: list[dict[str, Any]] = []
        self._action_counter: Counter[str] = Counter()
        self._hour_counter: Counter[int] = Counter()  # hour of day
        self._load()

    def _load(self) -> None:
        """Load existing activity log from disk."""
        try:
            if _STORAGE.exists():
                with _STORAGE.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if line:
                            entry = json.loads(line)
                            self._entries.append(entry)
                            self._action_counter[entry.get("action", "")] += 1
                            hour = int(entry.get("hour", 0))
                            self._hour_counter[hour] += 1
        except Exception:
            pass  # non-critical

    async def record(self, user_input: str, action: str, session_id: str) -> None:
        """Record a new activity event."""
        hour = int(time.localtime().tm_hour)
        entry: dict[str, Any] = {
            "ts": time.time(),
            "hour": hour,
            "action": action,
            "input_preview": user_input[:80],
            "session_id": session_id,
        }

        async with self._lock:
            self._entries.append(entry)
            self._action_counter[action] += 1
            self._hour_counter[hour] += 1
            # Keep last 10_000 entries in memory
            if len(self._entries) > 10_000:
                self._entries = self._entries[-10_000:]

        # Persist asynchronously
        asyncio.ensure_future(self._persist(entry))
        log_autonomy("activity_recorded", action=action, session_id=session_id)

    async def _persist(self, entry: dict[str, Any]) -> None:
        # Bug #6 fix: use the class-level _file_lock, not a new Lock() per call
        try:
            _STORAGE.parent.mkdir(parents=True, exist_ok=True)
            async with self._file_lock:
                with _STORAGE.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry) + "\n")
        except Exception:
            pass

    def most_common_actions(self, top_n: int = 5) -> list[tuple[str, int]]:
        return self._action_counter.most_common(top_n)

    def busiest_hours(self, top_n: int = 3) -> list[tuple[int, int]]:
        return self._hour_counter.most_common(top_n)

    def current_hour_count(self) -> int:
        return self._hour_counter[int(time.localtime().tm_hour)]
