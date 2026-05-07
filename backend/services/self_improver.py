"""
SelfImprover — JARVIS observes its own performance and improves.

Tracks:
  - Per-agent success rates
  - Per-action failure patterns
  - Per-mode response quality scores
  - Improvement recommendations (prompt adjustments, routing changes)

Storage:
  - In-memory ring buffer (last 1000 events)
  - SQLite persistence via PerformanceDB (same memory.db)

Auto-improvement:
  - If an agent has >30% failure rate: generate improved SYSTEM_PROMPT suggestion
  - If an action fails repeatedly with same error: add to known-issues registry
  - Weekly digest summarizing improvement opportunities

Usage:
    from services.self_improver import get_improver
    imp = get_improver()
    imp.record_success("dev", "code_generation", duration=1.2)
    imp.record_failure("executor", "shell_exec", error="timeout")
    report = imp.digest()
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Deque

from config import get_config

log = logging.getLogger(__name__)

_DB_PATH       = get_config().memory_db_path
MAX_EVENTS     = 1000    # in-memory ring buffer size
FAILURE_THRESHOLD = 0.30  # 30% failure rate triggers improvement suggestion


# ── Event types ────────────────────────────────────────────────────────────────

@dataclass
class PerformanceEvent:
    event_id:   str
    agent:      str
    action:     str
    success:    bool
    duration_s: float
    error:      str | None
    session_id: str
    timestamp:  float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "event_id":   self.event_id,
            "agent":      self.agent,
            "action":     self.action,
            "success":    self.success,
            "duration_s": round(self.duration_s, 3),
            "error":      self.error,
            "session_id": self.session_id,
            "timestamp":  self.timestamp,
        }


@dataclass
class AgentStats:
    agent:         str
    total:         int
    successes:     int
    failures:      int
    avg_duration_s: float
    top_errors:    list[str]

    @property
    def success_rate(self) -> float:
        return (self.successes / self.total) if self.total else 0.0

    @property
    def failure_rate(self) -> float:
        return 1.0 - self.success_rate

    def to_dict(self) -> dict:
        return {
            "agent":          self.agent,
            "total":          self.total,
            "successes":      self.successes,
            "failures":       self.failures,
            "success_rate":   round(self.success_rate, 3),
            "failure_rate":   round(self.failure_rate, 3),
            "avg_duration_s": round(self.avg_duration_s, 3),
            "top_errors":     self.top_errors,
        }


# ── PerformanceDB ──────────────────────────────────────────────────────────────

class PerformanceDB:
    """Thin SQLite persistence layer for performance events."""

    def __init__(self, db_path: Path = _DB_PATH) -> None:
        self._db = str(db_path)
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS perf_events (
                    event_id   TEXT PRIMARY KEY,
                    agent      TEXT NOT NULL,
                    action     TEXT NOT NULL,
                    success    INTEGER NOT NULL,
                    duration_s REAL,
                    error      TEXT,
                    session_id TEXT,
                    timestamp  REAL NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_perf_agent ON perf_events(agent)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_perf_ts ON perf_events(timestamp)")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db, timeout=5)

    def insert(self, event: PerformanceEvent) -> None:
        with self._lock:
            try:
                with self._connect() as conn:
                    conn.execute(
                        "INSERT OR IGNORE INTO perf_events VALUES (?,?,?,?,?,?,?,?)",
                        (
                            event.event_id, event.agent, event.action,
                            int(event.success), event.duration_s, event.error,
                            event.session_id, event.timestamp,
                        ),
                    )
            except Exception as exc:
                log.warning("PerformanceDB.insert failed: %s", exc)

    def query(
        self,
        agent: str | None = None,
        since: float | None = None,
        limit: int = 500,
    ) -> list[dict]:
        clauses = []
        params: list = []
        if agent:
            clauses.append("agent = ?")
            params.append(agent)
        if since:
            clauses.append("timestamp >= ?")
            params.append(since)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            try:
                with self._connect() as conn:
                    rows = conn.execute(
                        f"SELECT * FROM perf_events {where} ORDER BY timestamp DESC LIMIT ?",
                        params + [limit],
                    ).fetchall()
                cols = ["event_id", "agent", "action", "success", "duration_s",
                        "error", "session_id", "timestamp"]
                return [dict(zip(cols, row)) for row in rows]
            except Exception as exc:
                log.warning("PerformanceDB.query failed: %s", exc)
                return []

    def cleanup_old(self, max_age_days: int = 30) -> int:
        cutoff = time.time() - (max_age_days * 86400)
        with self._lock:
            try:
                with self._connect() as conn:
                    c = conn.execute("DELETE FROM perf_events WHERE timestamp < ?", (cutoff,))
                    return c.rowcount
            except Exception:
                return 0


# ── SelfImprover ───────────────────────────────────────────────────────────────

class SelfImprover:
    """
    Records agent performance events and generates improvement insights.
    """

    def __init__(self) -> None:
        self._ring:     Deque[PerformanceEvent] = deque(maxlen=MAX_EVENTS)
        self._lock      = threading.Lock()
        self._db        = PerformanceDB()
        self._known_issues: dict[str, int] = defaultdict(int)  # error_key → count
        self._improvement_cache: dict[str, str] = {}
        import uuid
        self._uuid = uuid

    # ── Recording ─────────────────────────────────────────────────────────────

    def record_success(
        self,
        agent: str,
        action: str,
        duration_s: float = 0.0,
        session_id: str = "",
    ) -> None:
        self._record(agent, action, success=True, duration_s=duration_s,
                     error=None, session_id=session_id)

    def record_failure(
        self,
        agent: str,
        action: str,
        error: str,
        duration_s: float = 0.0,
        session_id: str = "",
    ) -> None:
        self._record(agent, action, success=False, duration_s=duration_s,
                     error=error[:500], session_id=session_id)
        error_key = f"{agent}:{action}:{error[:50]}"
        with self._lock:
            self._known_issues[error_key] += 1

    def _record(
        self,
        agent: str,
        action: str,
        success: bool,
        duration_s: float,
        error: str | None,
        session_id: str,
    ) -> None:
        event = PerformanceEvent(
            event_id=str(self._uuid.uuid4()),
            agent=agent,
            action=action,
            success=success,
            duration_s=duration_s,
            error=error,
            session_id=session_id,
        )
        with self._lock:
            self._ring.append(event)
        # Async DB write to avoid blocking the calling thread
        threading.Thread(
            target=self._db.insert,
            args=(event,),
            daemon=True,
        ).start()

    # ── Stats ──────────────────────────────────────────────────────────────────

    def agent_stats(self, agent: str | None = None) -> list[AgentStats]:
        with self._lock:
            events = list(self._ring)

        if agent:
            events = [e for e in events if e.agent == agent]

        # Group by agent
        by_agent: dict[str, list[PerformanceEvent]] = defaultdict(list)
        for e in events:
            by_agent[e.agent].append(e)

        results: list[AgentStats] = []
        for ag, evs in by_agent.items():
            total     = len(evs)
            successes = sum(1 for e in evs if e.success)
            failures  = total - successes
            avg_dur   = sum(e.duration_s for e in evs) / total if total else 0.0

            # Top error messages
            error_counts: dict[str, int] = defaultdict(int)
            for e in evs:
                if e.error:
                    error_counts[e.error[:80]] += 1
            top_errors = sorted(error_counts, key=error_counts.get, reverse=True)[:3]  # type: ignore[arg-type]

            results.append(AgentStats(
                agent=ag,
                total=total,
                successes=successes,
                failures=failures,
                avg_duration_s=avg_dur,
                top_errors=top_errors,
            ))

        return sorted(results, key=lambda s: s.agent)

    def top_known_issues(self, top_n: int = 10) -> list[dict]:
        with self._lock:
            issues = dict(self._known_issues)
        return [
            {"error": k, "count": v}
            for k, v in sorted(issues.items(), key=lambda x: x[1], reverse=True)[:top_n]
        ]

    # ── Improvement suggestions ────────────────────────────────────────────────

    def get_improvement_suggestions(self) -> list[dict]:
        """
        Analyze stats and return actionable improvement suggestions.
        Returns list of {agent, suggestion, failure_rate, severity}.
        """
        suggestions: list[dict] = []
        stats = self.agent_stats()

        for stat in stats:
            if stat.total < 5:
                continue  # Not enough data

            if stat.failure_rate > FAILURE_THRESHOLD:
                severity = "high" if stat.failure_rate > 0.5 else "medium"
                suggestions.append({
                    "agent":        stat.agent,
                    "failure_rate": round(stat.failure_rate, 2),
                    "severity":     severity,
                    "suggestion": (
                        f"Agent '{stat.agent}' has {stat.failure_rate:.0%} failure rate "
                        f"({stat.failures}/{stat.total} calls). "
                        f"Top errors: {stat.top_errors}. "
                        "Consider reviewing system prompt and input preprocessing."
                    ),
                    "top_errors": stat.top_errors,
                })

        # Suggest routing changes based on known issues
        issues = self.top_known_issues(5)
        for issue in issues:
            if issue["count"] >= 5:
                suggestions.append({
                    "agent":      issue["error"].split(":")[0],
                    "severity":   "medium",
                    "suggestion": f"Recurring issue (×{issue['count']}): {issue['error']}. Consider adding a retry or fallback.",
                    "count":      issue["count"],
                })

        return suggestions

    def generate_improved_prompt(self, agent: str) -> str | None:
        """
        Ask the LLM to generate an improved system prompt for an underperforming agent.
        Returns the suggested prompt or None if insufficient data.
        """
        stats = {s.agent: s for s in self.agent_stats()}
        if agent not in stats:
            return None

        stat = stats[agent]
        if stat.total < 5 or stat.failure_rate < FAILURE_THRESHOLD:
            return None  # Not enough data or not failing

        # Use cache to avoid repeated LLM calls
        if agent in self._improvement_cache:
            return self._improvement_cache[agent]

        try:
            from services.llm_service import call_llm
            from services.agent_registry import get_agent

            current_prompt = getattr(get_agent(agent), "SYSTEM_PROMPT", "")
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are an AI prompt engineer. Improve the given system prompt "
                        "based on the failure analysis. Return ONLY the improved prompt text."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Agent: {agent}\n"
                        f"Failure rate: {stat.failure_rate:.0%}\n"
                        f"Top errors: {stat.top_errors}\n"
                        f"Current system prompt:\n{current_prompt[:1000]}\n\n"
                        "Provide an improved system prompt that addresses these failure patterns."
                    ),
                },
            ]
            improved = call_llm(messages, force_local=True)
            if improved and len(improved) > 50:
                self._improvement_cache[agent] = improved
                log.info("SelfImprover: generated improved prompt for %r (%d chars)", agent, len(improved))
                return improved
        except Exception as exc:
            log.warning("SelfImprover.generate_improved_prompt failed: %s", exc)

        return None

    # ── Digest ─────────────────────────────────────────────────────────────────

    def digest(self) -> str:
        """Generate a human-readable performance digest."""
        stats   = self.agent_stats()
        issues  = self.top_known_issues(5)
        suggestions = self.get_improvement_suggestions()

        total_events = sum(s.total for s in stats)
        if total_events == 0:
            return "📊 No performance data collected yet."

        lines = [
            "## JARVIS Performance Digest",
            f"Total events: {total_events} (in-memory ring buffer)",
            "",
            "### Agent Stats",
        ]
        for s in stats:
            icon = "✅" if s.failure_rate < 0.2 else ("⚠️" if s.failure_rate < 0.5 else "❌")
            lines.append(
                f"  {icon} **{s.agent}**: {s.successes}/{s.total} OK "
                f"({s.success_rate:.0%}), avg {s.avg_duration_s:.1f}s"
            )

        if issues:
            lines += ["", "### Top Recurring Issues"]
            for iss in issues:
                lines.append(f"  • ×{iss['count']} {iss['error']}")

        if suggestions:
            lines += ["", "### Improvement Suggestions"]
            for sug in suggestions:
                lines.append(f"  [{sug['severity'].upper()}] {sug['suggestion'][:200]}")

        return "\n".join(lines)

    def summary_dict(self) -> dict:
        return {
            "agent_stats":     [s.to_dict() for s in self.agent_stats()],
            "known_issues":    self.top_known_issues(),
            "suggestions":     self.get_improvement_suggestions(),
        }


# ── Singleton ──────────────────────────────────────────────────────────────────

_improver: SelfImprover | None = None


def get_improver() -> SelfImprover:
    """Return the global SelfImprover singleton."""
    global _improver
    if _improver is None:
        _improver = SelfImprover()
    return _improver
