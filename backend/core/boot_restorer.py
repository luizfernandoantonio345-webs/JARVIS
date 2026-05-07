"""
boot_restorer — FASE 11 Boot Context Restoration

Executed once when FastAPI starts (via startup event).

Responsibilities
----------------
1. Scan jobs/ directory for any non-terminal job (status ≠ done/escalated/failed).
2. Load the last 10 episodic memory entries across all sessions.
3. Load preferences with confidence > 0.7.
4. Load all project context entries.
5. Assemble a BootContext and store it in the in-memory session store under
   the special key "boot_context".
6. Log a structured summary of what was restored.

Usage (in main.py startup event)
---------------------------------
>>> from backend.core.boot_restorer import BootRestorer
>>> await BootRestorer().restore()
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

JOBS_BASE_DIR = Path(os.getenv("JARVIS_JOBS_DIR",
                               str(Path(__file__).parent.parent.parent / "jobs")))

# Session-store key for boot context
BOOT_CONTEXT_KEY = "boot_context"


# ── Models ─────────────────────────────────────────────────────────────────────

@dataclass
class ActiveJobSummary:
    job_id: str
    goal: str
    status: str
    last_stage: str
    files_completed: int
    updated_at: str


@dataclass
class BootContext:
    restored_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    active_job: ActiveJobSummary | None = None
    recent_history: list[dict[str, str]] = field(default_factory=list)
    preferences: dict[str, str] = field(default_factory=dict)
    project: dict[str, str] = field(default_factory=dict)
    injected: bool = False          # set to True once injected into an LLM call


# ── BootRestorer ───────────────────────────────────────────────────────────────

class BootRestorer:
    """Loads and caches startup context from persistent storage."""

    async def restore(self) -> BootContext:
        """
        Main entry point — called once from FastAPI startup.

        Returns the assembled BootContext (also stored in session store).
        """
        log.info("boot_restorer: scanning for previous session context…")

        ctx = BootContext(
            active_job=self._find_active_job(),
            recent_history=self._load_recent_history(limit=10),
            preferences=self._load_high_confidence_prefs(min_confidence=0.7),
            project=self._load_project_context(),
        )

        # Persist to in-memory session store so any route can read it
        self._save_to_session_store(ctx)

        # ── Structured log of what was restored ───────────────────────────────
        log.info(
            "boot_restorer: context restored",
            extra={
                "active_job": ctx.active_job.job_id if ctx.active_job else None,
                "history_entries": len(ctx.recent_history),
                "preferences_count": len(ctx.preferences),
                "project_entries": len(ctx.project),
            },
        )

        if ctx.active_job:
            log.info(
                "boot_restorer: resumable job found — %s [%s] last stage: %s",
                ctx.active_job.job_id,
                ctx.active_job.status,
                ctx.active_job.last_stage,
            )
        if ctx.preferences:
            log.info(
                "boot_restorer: restored %d preference(s): %s",
                len(ctx.preferences),
                list(ctx.preferences.keys()),
            )
        if ctx.project:
            log.info(
                "boot_restorer: restored project context keys: %s",
                list(ctx.project.keys()),
            )

        return ctx

    # ── Private helpers ────────────────────────────────────────────────────────

    def _find_active_job(self) -> ActiveJobSummary | None:
        """Scan JOBS_BASE_DIR for the most recent non-terminal job."""
        if not JOBS_BASE_DIR.exists():
            return None

        terminal = {"done", "escalated", "failed"}
        candidates: list[tuple[str, dict]] = []

        for job_dir in sorted(JOBS_BASE_DIR.iterdir(), key=lambda d: d.stat().st_mtime, reverse=True):
            if not job_dir.is_dir():
                continue
            state_file = job_dir / "state.json"
            if not state_file.exists():
                continue
            try:
                state = json.loads(state_file.read_text(encoding="utf-8"))
                if state.get("status") not in terminal:
                    candidates.append((str(state.get("updated_at", "")), state))
            except Exception as exc:
                log.debug("[core.boot_restorer] suppressed exception", exc_info=exc)
                continue

        if not candidates:
            return None

        # Most recently updated non-terminal job
        candidates.sort(key=lambda x: x[0], reverse=True)
        best = candidates[0][1]
        files_completed = best.get("files_completed") or []
        return ActiveJobSummary(
            job_id=best.get("job_id", ""),
            goal=best.get("goal", "")[:200],
            status=best.get("status", ""),
            last_stage=best.get("status", ""),
            files_completed=len(files_completed) if isinstance(files_completed, list) else 0,
            updated_at=best.get("updated_at", ""),
        )

    def _load_recent_history(self, limit: int = 10) -> list[dict[str, str]]:
        """Load the last `limit` episodic memory entries across all sessions."""
        try:
            import sqlite3
            from services.memory_service import DB_PATH

            conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            cursor = conn.execute(
                "SELECT session_id, message, response, action, created_at "
                "FROM memory ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            rows = cursor.fetchall()
            conn.close()
            return [
                {
                    "session_id": r[0],
                    "message": r[1][:300],
                    "response": r[2][:300],
                    "action": r[3],
                    "created_at": r[4],
                }
                for r in rows
            ]
        except Exception as exc:
            log.warning("boot_restorer: could not load episodic history: %s", exc)
            return []

    def _load_high_confidence_prefs(self, min_confidence: float = 0.7) -> dict[str, str]:
        """Load preferences with confidence >= min_confidence from all sessions."""
        try:
            import sqlite3
            from services.memory_service import DB_PATH

            conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            cursor = conn.execute(
                "SELECT key, value FROM preferences WHERE confidence >= ? "
                "ORDER BY confidence DESC, updated_at DESC LIMIT 50",
                (min_confidence,),
            )
            rows = cursor.fetchall()
            conn.close()
            return dict(rows)
        except Exception as exc:
            log.warning("boot_restorer: could not load preferences: %s", exc)
            return {}

    def _load_project_context(self) -> dict[str, str]:
        """Load all project context entries (most recent session wins on conflict)."""
        try:
            import sqlite3
            from services.memory_service import DB_PATH

            conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            cursor = conn.execute(
                "SELECT name, content FROM project_context "
                "ORDER BY updated_at DESC LIMIT 20"
            )
            rows = cursor.fetchall()
            conn.close()
            # Keep first occurrence of each name (most recent)
            result: dict[str, str] = {}
            for name, content in rows:
                if name not in result:
                    result[name] = content
            return result
        except Exception as exc:
            log.warning("boot_restorer: could not load project context: %s", exc)
            return {}

    def _save_to_session_store(self, ctx: BootContext) -> None:
        """Store BootContext in the in-memory session store."""
        try:
            from services.session_store import append_message
            # We encode the boot context as a special system message
            # so it is accessible to any component that reads session history.
            ctx_json = json.dumps(asdict(ctx), default=str)
            append_message(BOOT_CONTEXT_KEY, "system", ctx_json)
        except Exception as exc:
            log.warning("boot_restorer: could not save to session store: %s", exc)


# ── Public accessor ────────────────────────────────────────────────────────────

def get_boot_context() -> BootContext | None:
    """
    Return the stored BootContext from session store, or None if not set.

    Usage
    -----
    >>> ctx = get_boot_context()
    >>> if ctx and ctx.active_job:
    ...     print("Resumable job:", ctx.active_job.job_id)
    """
    try:
        from services.session_store import get_history
        history = get_history(BOOT_CONTEXT_KEY)
        if not history:
            return None
        # The most recent system message is the boot context
        for msg in reversed(history):
            if msg.get("role") == "system":
                data = json.loads(msg["content"])
                active = data.get("active_job")
                return BootContext(
                    restored_at=data.get("restored_at", ""),
                    active_job=ActiveJobSummary(**active) if active else None,
                    recent_history=data.get("recent_history", []),
                    preferences=data.get("preferences", {}),
                    project=data.get("project", {}),
                    injected=data.get("injected", False),
                )
    except Exception as exc:
        log.debug("[core.boot_restorer] suppressed exception", exc_info=exc)
        pass
    return None


def mark_boot_context_injected() -> None:
    """Mark the boot context as injected so it is not repeated on future calls."""
    ctx = get_boot_context()
    if ctx:
        ctx.injected = True
        try:
            from services.session_store import append_message
            ctx_json = json.dumps(asdict(ctx), default=str)
            append_message(BOOT_CONTEXT_KEY, "system", ctx_json)
        except Exception as exc:
            log.debug("[core.boot_restorer] suppressed exception", exc_info=exc)
            pass
