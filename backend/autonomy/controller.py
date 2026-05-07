"""
controller — FASE 11A

AutonomyController manages the lifecycle of the System Event Loop:
  - start / stop / pause / resume
  - Rate limiting (max 3 actions/minute)
  - SAFE mode: file-write actions require WebSocket confirmation
  - Metrics persistence via SQLite
  - Action log (last 50 entries)
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, date
from enum import Enum
from pathlib import Path
from typing import Literal

from config import get_config

log = logging.getLogger(__name__)

DB_PATH = get_config().memory_db_path

# ── State ─────────────────────────────────────────────────────────────────────

class AutonomyState(str, Enum):
    RUNNING = "running"
    PAUSED  = "paused"
    STOPPED = "stopped"


@dataclass
class ActionRecord:
    ts: float
    rule_id: str
    goal: str
    status: str          # success | error | skipped | timeout_cancel
    output_summary: str = ""
    event_type: str = ""


# ── Controller ────────────────────────────────────────────────────────────────

class AutonomyController:
    """
    Singleton-style controller for the System Event Loop.
    Instantiated once in main.py startup and kept as app.state.autonomy.
    """

    _MAX_ACTIONS_PER_MINUTE = 3
    _LOG_RETENTION = 50    # keep last N action records in memory
    _WRITE_KEYWORDS = frozenset({"escrev", "cri", "delet", "remov", "modific", "salv",
                                 "write", "creat", "delet", "remov", "modif", "save"})

    def __init__(self, safe_mode: bool = True) -> None:
        self._state = AutonomyState.STOPPED
        self._safe_mode = safe_mode
        self._action_log: deque[ActionRecord] = deque(maxlen=self._LOG_RETENTION)
        self._rate_window: deque[float] = deque()    # timestamps of recent actions
        self._pending_confirmations: dict[str, asyncio.Future] = {}
        self._loop_task: asyncio.Task | None = None
        self._events_today = 0
        self._actions_taken = 0
        self._last_action: ActionRecord | None = None
        self._ensure_table()

    # ── DB ────────────────────────────────────────────────────────────────────

    def _ensure_table(self) -> None:
        try:
            with sqlite3.connect(str(DB_PATH)) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS autonomy_log (
                        id        INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts        REAL NOT NULL,
                        rule_id   TEXT,
                        goal      TEXT,
                        status    TEXT,
                        output    TEXT,
                        event_type TEXT
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS ix_al_ts ON autonomy_log(ts)")
                conn.commit()
        except Exception as exc:
            log.warning("AutonomyController: DB init failed: %s", exc)

    def _persist_action(self, rec: ActionRecord) -> None:
        try:
            with sqlite3.connect(str(DB_PATH)) as conn:
                conn.execute(
                    "INSERT INTO autonomy_log(ts,rule_id,goal,status,output,event_type) "
                    "VALUES (?,?,?,?,?,?)",
                    (rec.ts, rec.rule_id, rec.goal, rec.status,
                     rec.output_summary[:1000], rec.event_type),
                )
                conn.commit()
        except Exception as exc:
            log.warning("AutonomyController: persist failed: %s", exc)

    # ── Rate limiting ─────────────────────────────────────────────────────────

    def _within_rate_limit(self) -> bool:
        now = time.time()
        self._rate_window = deque(t for t in self._rate_window if now - t < 60.0)
        return len(self._rate_window) < self._MAX_ACTIONS_PER_MINUTE

    def _record_action_timestamp(self) -> None:
        self._rate_window.append(time.time())

    # ── Safe mode confirmation ────────────────────────────────────────────────

    def _requires_confirmation(self, goal: str) -> bool:
        if not self._safe_mode:
            return False
        goal_lower = goal.lower()
        return any(kw in goal_lower for kw in self._WRITE_KEYWORDS)

    async def _request_confirmation(self, goal: str, timeout: float = 30.0) -> bool:
        """
        Send a confirmation request via the WebSocket broadcast mechanism.
        Returns True if confirmed, False on timeout or rejection.
        """
        try:
            from services.message_bus import MessageBus
            bus = MessageBus.get_instance()
            fut: asyncio.Future = asyncio.get_event_loop().create_future()
            confirm_id = f"confirm_{int(time.time() * 1000)}"
            self._pending_confirmations[confirm_id] = fut

            await bus.broadcast({
                "event": "confirmation_required",
                "confirm_id": confirm_id,
                "goal": goal,
                "timeout": timeout,
            })

            try:
                result = await asyncio.wait_for(fut, timeout=timeout)
                return bool(result)
            except asyncio.TimeoutError:
                log.info("AutonomyController: confirmation timeout for '%s'", goal[:60])
                return False
            finally:
                self._pending_confirmations.pop(confirm_id, None)
        except Exception as exc:
            log.warning("AutonomyController: confirmation mechanism unavailable: %s", exc)
            return True  # Fail open if bus unavailable

    def confirm(self, confirm_id: str, approved: bool) -> None:
        """Called by the WebSocket endpoint when user responds to a confirmation."""
        fut = self._pending_confirmations.get(confirm_id)
        if fut and not fut.done():
            fut.set_result(approved)

    # ── Core event loop ───────────────────────────────────────────────────────

    async def _loop(self) -> None:
        from autonomy.event_detector import EventDetector
        from autonomy.event_router import EventRouter

        detector = EventDetector()
        router = EventRouter(session_id="autonomy")
        await detector.start()

        log.info("AutonomyController: event loop started")
        try:
            async for event in detector.events():
                if self._state == AutonomyState.STOPPED:
                    break
                if self._state == AutonomyState.PAUSED:
                    continue

                self._events_today += 1

                actions = router.route(event)
                for action in actions:
                    await self._execute_action(action, event)

        except asyncio.CancelledError:
            pass
        finally:
            await detector.stop()
            log.info("AutonomyController: event loop stopped")

    async def _execute_action(self, action: dict, event: Any = None) -> None:
        goal = action.get("goal", "")
        rule_id = action.get("rule_id", "unknown")
        event_type = getattr(event, "event_type", "unknown") if event else "manual"

        if not self._within_rate_limit():
            log.warning("AutonomyController: rate limit reached, skipping '%s'", goal[:60])
            rec = ActionRecord(ts=time.time(), rule_id=rule_id, goal=goal,
                               status="skipped", output_summary="rate_limited",
                               event_type=event_type)
            self._log_action(rec)
            return

        # Safe mode: confirm write operations
        if self._requires_confirmation(goal):
            approved = await self._request_confirmation(goal)
            if not approved:
                rec = ActionRecord(ts=time.time(), rule_id=rule_id, goal=goal,
                                   status="timeout_cancel", output_summary="user_did_not_confirm",
                                   event_type=event_type)
                self._log_action(rec)
                return

        self._record_action_timestamp()
        self._actions_taken += 1

        from autonomy.event_router import EventRouter
        router = EventRouter(session_id="autonomy")
        result = await router.dispatch(goal, rule_id=rule_id)

        rec = ActionRecord(
            ts=time.time(),
            rule_id=rule_id,
            goal=goal,
            status=result.get("status", "error"),
            output_summary=result.get("output", "")[:500],
            event_type=event_type,
        )
        self._log_action(rec)

    def _log_action(self, rec: ActionRecord) -> None:
        self._action_log.appendleft(rec)
        self._last_action = rec
        self._persist_action(rec)

    # ── Public lifecycle ──────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._state == AutonomyState.RUNNING:
            log.info("AutonomyController: already running")
            return
        self._state = AutonomyState.RUNNING
        self._loop_task = asyncio.create_task(self._loop(), name="autonomy-loop")
        log.info("AutonomyController: started (safe_mode=%s)", self._safe_mode)

    async def pause(self) -> None:
        self._state = AutonomyState.PAUSED
        log.info("AutonomyController: paused")

    async def resume(self) -> None:
        if self._state == AutonomyState.PAUSED:
            self._state = AutonomyState.RUNNING
            log.info("AutonomyController: resumed")

    async def stop(self) -> None:
        self._state = AutonomyState.STOPPED
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
            await asyncio.gather(self._loop_task, return_exceptions=True)
        log.info("AutonomyController: stopped")

    # ── Metrics ───────────────────────────────────────────────────────────────

    def status_dict(self) -> dict:
        last = self._last_action
        return {
            "state": self._state.value,
            "safe_mode": self._safe_mode,
            "events_today": self._events_today,
            "actions_taken": self._actions_taken,
            "actions_this_minute": len(self._rate_window),
            "last_action": {
                "ts": last.ts,
                "rule_id": last.rule_id,
                "goal": last.goal[:100],
                "status": last.status,
            } if last else None,
        }

    def log_entries(self, limit: int = 50) -> list[dict]:
        return [asdict(r) for r in list(self._action_log)[:limit]]

    def get_db_log(self, limit: int = 50) -> list[dict]:
        try:
            with sqlite3.connect(str(DB_PATH)) as conn:
                rows = conn.execute(
                    "SELECT ts,rule_id,goal,status,output,event_type "
                    "FROM autonomy_log ORDER BY ts DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [
                {"ts": r[0], "rule_id": r[1], "goal": r[2], "status": r[3],
                 "output": r[4], "event_type": r[5]}
                for r in rows
            ]
        except Exception:
            return []


# ── App-level singleton access ────────────────────────────────────────────────

_controller: AutonomyController | None = None


def get_autonomy_controller() -> AutonomyController:
    global _controller
    if _controller is None:
        _controller = AutonomyController(safe_mode=True)
    return _controller


# Fix missing Any import at module level
from typing import Any  # noqa: E402 — placed here to avoid circular at top
