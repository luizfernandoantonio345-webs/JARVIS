"""
session_checkpoint — FASE 11 Session State Persistence

Saves session state periodically (every 5 minutes) and on graceful shutdown.

What is checkpointed
--------------------
  - Active job_id + status (from AutoDev loop registry)
  - Last 5 executed shell/agent actions (from autonomous loop state)
  - Autonomous loop state snapshot
  - Timestamp

Storage: SQLite table ``session_checkpoints`` in the same memory.db
Retention: rows older than 7 days are pruned on each save.

Usage (in main.py)
------------------
>>> from backend.core.session_checkpoint import SessionCheckpoint, start_checkpoint_scheduler
>>>
>>> @app.on_event("startup")
>>> async def startup():
...     start_checkpoint_scheduler()           # background 5-min saves
>>>
>>> @app.on_event("shutdown")
>>> async def shutdown():
...     await SessionCheckpoint().save()       # final save
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_CHECKPOINT_INTERVAL_S = 300  # 5 minutes
_RETENTION_DAYS        = 7

_scheduler_task: asyncio.Task | None = None


# ── DB setup ───────────────────────────────────────────────────────────────────

def _get_db_conn() -> sqlite3.Connection:
    """Return a connection to memory.db with the checkpoints table bootstrapped."""
    from services.memory_service import DB_PATH

    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS session_checkpoints (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            saved_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            active_job   TEXT,
            last_actions TEXT,
            loop_state   TEXT,
            extra        TEXT
        )
    """)
    conn.commit()
    return conn


# ── SessionCheckpoint ─────────────────────────────────────────────────────────

class SessionCheckpoint:
    """Captures and persists the current session state."""

    async def save(self) -> None:
        """Capture current state and write to session_checkpoints table."""
        try:
            snapshot = self._capture()
            self._write(snapshot)
            self._prune_old()
            log.info(
                "session_checkpoint: saved — job=%s actions=%d",
                snapshot.get("active_job"),
                len(snapshot.get("last_actions", [])),
            )
        except Exception as exc:
            log.warning("session_checkpoint: save failed: %s", exc)

    # ── Snapshot builder ───────────────────────────────────────────────────────

    def _capture(self) -> dict[str, Any]:
        return {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "active_job": self._get_active_job(),
            "last_actions": self._get_last_actions(limit=5),
            "loop_state": self._get_loop_state(),
        }

    def _get_active_job(self) -> str | None:
        """Return job_id of the most recently updated non-terminal AutoDev job."""
        try:
            from autodev.loop import _active_jobs, JobStatus
            for job_id, job in _active_jobs.items():
                state = job.get_status()
                status = state.get("status", "")
                if not JobStatus.is_terminal(status):
                    return job_id
        except Exception as exc:
            log.debug("[core.session_checkpoint] suppressed exception", exc_info=exc)
            pass
        return None

    def _get_last_actions(self, limit: int = 5) -> list[dict]:
        """Return the last `limit` episodic memory entries as action records."""
        try:
            import sqlite3 as _sqlite
            from services.memory_service import DB_PATH

            conn = _sqlite.connect(str(DB_PATH), check_same_thread=False)
            cursor = conn.execute(
                "SELECT action, message, created_at FROM memory "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            rows = cursor.fetchall()
            conn.close()
            return [
                {"action": r[0], "message": r[1][:200], "created_at": r[2]}
                for r in rows
            ]
        except Exception:
            return []

    def _get_loop_state(self) -> dict | None:
        """Snapshot the autonomous loop state from session store."""
        try:
            from services.session_store import get_history
            history = get_history("autonomous_loop")
            if history:
                last = history[-1]
                return {"last_message": last.get("content", "")[:500]}
        except Exception as exc:
            log.debug("[core.session_checkpoint] suppressed exception", exc_info=exc)
            pass
        return None

    # ── DB I/O ─────────────────────────────────────────────────────────────────

    def _write(self, snapshot: dict) -> None:
        conn = _get_db_conn()
        try:
            conn.execute(
                "INSERT INTO session_checkpoints "
                "(saved_at, active_job, last_actions, loop_state, extra) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    snapshot["saved_at"],
                    snapshot.get("active_job") or "",
                    json.dumps(snapshot.get("last_actions", [])),
                    json.dumps(snapshot.get("loop_state") or {}),
                    "{}",
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _prune_old(self) -> None:
        """Delete checkpoints older than _RETENTION_DAYS days."""
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=_RETENTION_DAYS)
        ).isoformat()
        conn = _get_db_conn()
        try:
            conn.execute(
                "DELETE FROM session_checkpoints WHERE saved_at < ?",
                (cutoff,),
            )
            conn.commit()
        finally:
            conn.close()


# ── Background scheduler ───────────────────────────────────────────────────────

async def _checkpoint_loop() -> None:
    """Coroutine that saves a checkpoint every _CHECKPOINT_INTERVAL_S seconds."""
    cp = SessionCheckpoint()
    while True:
        await asyncio.sleep(_CHECKPOINT_INTERVAL_S)
        await cp.save()


def start_checkpoint_scheduler() -> None:
    """
    Start the background checkpoint task (call once from FastAPI startup).

    Safe to call multiple times — only one task is created.
    """
    global _scheduler_task
    if _scheduler_task is not None and not _scheduler_task.done():
        return
    _scheduler_task = asyncio.create_task(_checkpoint_loop())
    log.info("session_checkpoint: scheduler started (interval=%ds)", _CHECKPOINT_INTERVAL_S)


# ── Reader helper ──────────────────────────────────────────────────────────────

def get_last_checkpoint() -> dict | None:
    """Return the most recent checkpoint, or None."""
    try:
        conn = _get_db_conn()
        cursor = conn.execute(
            "SELECT saved_at, active_job, last_actions, loop_state "
            "FROM session_checkpoints ORDER BY id DESC LIMIT 1"
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "saved_at": row[0],
            "active_job": row[1],
            "last_actions": json.loads(row[2] or "[]"),
            "loop_state": json.loads(row[3] or "{}"),
        }
    except Exception as exc:
        log.warning("session_checkpoint: read failed: %s", exc)
        return None
