"""
LearningLoop — FASE 5: Self-Learning

Analyses per-agent failure rates from SelfImprover and generates
improved system-prompt hints via local LLM. Hints are stored in
SQLite and exposed to agents that request them.

Usage:
    from core.learning_loop import get_learning_loop
    loop = get_learning_loop()
    hints = await loop.analyze_async()   # non-blocking, returns list[Hint]
    hint  = loop.get_hints("dev")        # latest hints for the dev agent
"""
from __future__ import annotations

import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from config import get_config

log = logging.getLogger(__name__)

_DB_PATH = get_config().memory_db_path
FAILURE_THRESHOLD = 0.30
MIN_EVENTS = 5           # skip agents with fewer events than this
MAX_HINTS_PER_AGENT = 3  # only keep the latest N hints per agent


# ── Data types ─────────────────────────────────────────────────────────────────

@dataclass
class Hint:
    agent: str
    hint: str
    failure_rate: float
    created_at: float

    def to_dict(self) -> dict:
        return {
            "agent":        self.agent,
            "hint":         self.hint,
            "failure_rate": round(self.failure_rate, 3),
            "created_at":   self.created_at,
        }


# ── SQLite schema ──────────────────────────────────────────────────────────────

def _init_schema(db_path: Path) -> None:
    try:
        with sqlite3.connect(str(db_path), timeout=5) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS learning_hints (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent       TEXT    NOT NULL,
                    hint        TEXT    NOT NULL,
                    failure_rate REAL   NOT NULL DEFAULT 0,
                    created_at  REAL    NOT NULL,
                    applied     INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_lh_agent ON learning_hints(agent)")
    except Exception as exc:
        log.warning("learning_hints schema init failed: %s", exc)


# ── LearningLoop ───────────────────────────────────────────────────────────────

class LearningLoop:
    def __init__(self) -> None:
        _init_schema(_DB_PATH)
        self._lock = threading.Lock()
        self._last_run: float = 0.0
        self._cooldown_s: float = 300.0  # run at most once every 5 minutes

    # ── Public API ─────────────────────────────────────────────────────────────

    def analyze(self) -> list[Hint]:
        """
        Synchronously analyse performance stats and generate hints for
        underperforming agents.  Rate-limited by _cooldown_s.
        """
        now = time.time()
        if now - self._last_run < self._cooldown_s:
            return []

        try:
            from services.self_improver import get_improver
            stats = get_improver().agent_stats()
        except Exception as exc:
            log.warning("LearningLoop: could not get stats: %s", exc)
            return []

        hints: list[Hint] = []
        for stat in stats:
            if stat.total < MIN_EVENTS:
                continue
            if stat.failure_rate <= FAILURE_THRESHOLD:
                continue

            hint_text = self._generate_hint(stat.agent, stat.failure_rate, stat.top_errors)
            if not hint_text:
                continue

            hint = Hint(
                agent=stat.agent,
                hint=hint_text,
                failure_rate=stat.failure_rate,
                created_at=now,
            )
            self._persist_hint(hint)
            hints.append(hint)

        if hints:
            self._last_run = now

        return hints

    def analyze_in_background(self) -> None:
        """Fire-and-forget background analysis (safe to call from hot path)."""
        threading.Thread(target=self.analyze, daemon=True).start()

    def get_hints(self, agent: str, limit: int = MAX_HINTS_PER_AGENT) -> list[str]:
        """Return the latest *limit* hints for *agent*."""
        try:
            with sqlite3.connect(str(_DB_PATH), timeout=5) as conn:
                rows = conn.execute(
                    "SELECT hint FROM learning_hints WHERE agent = ? ORDER BY created_at DESC LIMIT ?",
                    (agent, limit),
                ).fetchall()
            return [row[0] for row in rows]
        except Exception as exc:
            log.warning("LearningLoop.get_hints failed: %s", exc)
            return []

    def apply_hint(self, agent: str) -> Optional[str]:
        """Return the latest unapplied hint for *agent* and mark it applied."""
        try:
            with sqlite3.connect(str(_DB_PATH), timeout=5) as conn:
                row = conn.execute(
                    "SELECT id, hint FROM learning_hints WHERE agent = ? AND applied = 0 ORDER BY created_at DESC LIMIT 1",
                    (agent,),
                ).fetchone()
                if not row:
                    return None
                conn.execute("UPDATE learning_hints SET applied = 1 WHERE id = ?", (row[0],))
            return row[1]
        except Exception as exc:
            log.warning("LearningLoop.apply_hint failed: %s", exc)
            return None

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _generate_hint(self, agent: str, failure_rate: float, top_errors: list[str]) -> str | None:
        """Ask local LLM for a concise improvement hint (2-3 sentences max)."""
        try:
            from services.llm_service import call_llm
            prompt = (
                f"Agent '{agent}' has a {failure_rate:.0%} failure rate. "
                f"Top errors: {top_errors}. "
                "Write a concise 2-sentence improvement hint for this agent's system prompt. "
                "Focus on avoiding the top errors. Return ONLY the hint text."
            )
            hint = call_llm(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=120,
                force_local=True,
            )
            hint = (hint or "").strip()
            return hint if len(hint) > 20 else None
        except Exception as exc:
            log.warning("LearningLoop._generate_hint failed: %s", exc)
            return None

    def _persist_hint(self, hint: Hint) -> None:
        """Write hint to SQLite, trimming old hints for the agent."""
        try:
            with sqlite3.connect(str(_DB_PATH), timeout=5) as conn:
                conn.execute(
                    "INSERT INTO learning_hints (agent, hint, failure_rate, created_at, applied) VALUES (?,?,?,?,0)",
                    (hint.agent, hint.hint, hint.failure_rate, hint.created_at),
                )
                # Keep only the latest MAX_HINTS_PER_AGENT per agent
                conn.execute(
                    """
                    DELETE FROM learning_hints
                    WHERE agent = ?
                    AND id NOT IN (
                        SELECT id FROM learning_hints
                        WHERE agent = ?
                        ORDER BY created_at DESC
                        LIMIT ?
                    )
                    """,
                    (hint.agent, hint.agent, MAX_HINTS_PER_AGENT),
                )
        except Exception as exc:
            log.warning("LearningLoop._persist_hint failed: %s", exc)


# ── Singleton ──────────────────────────────────────────────────────────────────

_loop: LearningLoop | None = None
_loop_lock = threading.Lock()


def get_learning_loop() -> LearningLoop:
    global _loop
    if _loop is None:
        with _loop_lock:
            if _loop is None:
                _loop = LearningLoop()
    return _loop
