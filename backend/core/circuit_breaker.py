"""
circuit_breaker — FASE 12C

Protects the system against cascading failures:
  - LLM fails 3x consecutive → auto-fallback to alternative model
  - AutoDev has 5 escalations/hour → pause AutoDev + voice notification
  - Memory SQLite > 500MB → trigger cleanup of old entries
  - Event Loop > 10 events/min → throttle to prevent spam
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from collections import deque
from pathlib import Path

from config import get_config

log = logging.getLogger(__name__)

DB_PATH = get_config().memory_db_path

# ── LLM Circuit Breaker ───────────────────────────────────────────────────────

class LLMCircuitBreaker:
    """
    Tracks consecutive LLM failures per backend and triggers fallback.
    """

    _MAX_FAILURES = 3
    _FALLBACK_CHAIN = ["ollama", "gpt-4o-mini", "claude"]

    def __init__(self) -> None:
        self._failures: dict[str, int] = {}
        self._tripped: set[str] = set()

    def record_success(self, backend: str) -> None:
        self._failures[backend] = 0
        self._tripped.discard(backend)

    def record_failure(self, backend: str) -> str | None:
        """
        Record a failure. If threshold reached, return the fallback backend name.
        Returns None if not yet tripped.
        """
        self._failures[backend] = self._failures.get(backend, 0) + 1
        if self._failures[backend] >= self._MAX_FAILURES:
            if backend not in self._tripped:
                self._tripped.add(backend)
                fallback = self._get_fallback(backend)
                log.warning(
                    "CircuitBreaker: LLM '%s' tripped after %d failures → fallback '%s'",
                    backend, self._MAX_FAILURES, fallback,
                )
                return fallback
        return None

    def _get_fallback(self, current: str) -> str:
        idx = self._FALLBACK_CHAIN.index(current) if current in self._FALLBACK_CHAIN else -1
        for alt in self._FALLBACK_CHAIN[idx + 1:] + self._FALLBACK_CHAIN[:idx]:
            if alt != current:
                return alt
        return "ollama"

    def is_tripped(self, backend: str) -> bool:
        return backend in self._tripped


# ── AutoDev Circuit Breaker ───────────────────────────────────────────────────

class AutoDevCircuitBreaker:
    """
    Monitors escalation rate. Pauses AutoDev if 5+ escalations in 1 hour.
    """

    _MAX_ESCALATIONS_PER_HOUR = 5
    _paused = False
    _escalation_times: deque = deque()

    def record_escalation(self) -> bool:
        """Returns True if AutoDev should be paused."""
        now = time.time()
        self._escalation_times = deque(
            t for t in self._escalation_times if now - t < 3600
        )
        self._escalation_times.append(now)
        if len(self._escalation_times) >= self._MAX_ESCALATIONS_PER_HOUR and not self._paused:
            self._paused = True
            log.warning(
                "CircuitBreaker: AutoDev paused — %d escalations in the last hour",
                len(self._escalation_times),
            )
            return True
        return False

    def reset(self) -> None:
        self._paused = False
        self._escalation_times.clear()

    @property
    def paused(self) -> bool:
        return self._paused


# ── Memory Circuit Breaker ────────────────────────────────────────────────────

class MemoryCircuitBreaker:
    """
    Monitors SQLite size and prunes old entries when above threshold.
    """

    _MAX_SIZE_MB = 500
    _RETAIN_DAYS = 30

    def check_and_prune(self) -> bool:
        """Returns True if pruning was triggered."""
        if not DB_PATH.exists():
            return False
        size_mb = DB_PATH.stat().st_size / (1024 * 1024)
        if size_mb < self._MAX_SIZE_MB:
            return False

        log.warning(
            "CircuitBreaker: Memory DB is %.1f MB — pruning entries older than %d days",
            size_mb, self._RETAIN_DAYS,
        )
        try:
            cutoff = time.time() - self._RETAIN_DAYS * 86400
            with sqlite3.connect(str(DB_PATH)) as conn:
                conn.execute("DELETE FROM memory WHERE timestamp < ?", (cutoff,))
                conn.execute("VACUUM")
                conn.commit()
            log.info("CircuitBreaker: Memory pruning completed")
            return True
        except Exception as exc:
            log.error("CircuitBreaker: Memory pruning failed: %s", exc)
            return False


# ── Event Loop Throttle ───────────────────────────────────────────────────────

class EventLoopThrottle:
    """
    Enforces a maximum events-per-minute rate to prevent action spam.
    """

    _MAX_EVENTS_PER_MINUTE = 10

    def __init__(self) -> None:
        self._window: deque = deque()
        self._throttled = False

    def check(self) -> bool:
        """Returns True if the event should be processed (not throttled)."""
        now = time.time()
        self._window = deque(t for t in self._window if now - t < 60)
        self._window.append(now)
        if len(self._window) > self._MAX_EVENTS_PER_MINUTE:
            if not self._throttled:
                self._throttled = True
                log.warning(
                    "CircuitBreaker: Event loop throttled — %d events/min exceeds limit of %d",
                    len(self._window), self._MAX_EVENTS_PER_MINUTE,
                )
            return False
        self._throttled = False
        return True


# ── Singletons ────────────────────────────────────────────────────────────────

_llm_cb   = LLMCircuitBreaker()
_autodev_cb = AutoDevCircuitBreaker()
_memory_cb  = MemoryCircuitBreaker()
_evt_throttle = EventLoopThrottle()


def get_llm_circuit_breaker()     -> LLMCircuitBreaker:     return _llm_cb
def get_autodev_circuit_breaker() -> AutoDevCircuitBreaker: return _autodev_cb
def get_memory_circuit_breaker()  -> MemoryCircuitBreaker:  return _memory_cb
def get_event_throttle()          -> EventLoopThrottle:     return _evt_throttle


async def run_periodic_checks(interval_seconds: float = 300) -> None:
    """Background task that runs circuit breaker checks periodically."""
    while True:
        try:
            _memory_cb.check_and_prune()
        except Exception as exc:
            log.error("CircuitBreaker periodic check failed: %s", exc)
        await asyncio.sleep(interval_seconds)
