"""
Autonomy Manager — coordinates all autonomy_v2 components.

Flow (non-blocking, parallel to main pipeline):
  Orchestrator → logs activity → AutonomyManager analyzes
                              → LEVEL 0: nothing
                              → LEVEL 1: surface suggestions
                              → LEVEL 2: auto-execute LOW-risk via orchestrator

CRITICAL: AutonomyManager NEVER calls tools directly.
All execution goes through the CoreOrchestrator.

Anti-spam rules (Phase 3 tuning):
  - Same suggestion text deduplicates within DEDUP_WINDOW_S seconds
  - At most MAX_PENDING suggestions are kept in queue
  - Suggestions are re-evaluated at most every EVAL_COOLDOWN_S seconds
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from autonomy.activity_tracker import ActivityTracker
from autonomy.autonomy_policy import AutonomyLevel, DEFAULT_LEVEL
from autonomy.decision_engine import DecisionEngine, DecisionOutcome
from autonomy.suggestion_engine import SuggestionEngine
from core.logger import log_autonomy, log_error

DEDUP_WINDOW_S = 300.0   # 5 min: same suggestion text won't repeat within this window
MAX_PENDING    = 5       # max suggestions queued at any time
EVAL_COOLDOWN_S = 60.0   # re-evaluate suggestions at most once per minute


class AutonomyManager:
    def __init__(self, level: AutonomyLevel = DEFAULT_LEVEL) -> None:
        self._level = level
        self._tracker = ActivityTracker()
        self._suggestion_engine = SuggestionEngine(self._tracker)
        self._decision_engine = DecisionEngine(self._level)
        self._pending_suggestions: list[dict[str, Any]] = []
        self._seen_suggestions: dict[str, float] = {}   # text → last_shown_ts
        self._last_eval_ts: float = 0.0
        log_autonomy("autonomy_manager_init", level=level.value)

    # ── Called by Orchestrator after each interaction ──────────────────────────

    async def track_activity(
        self, user_input: str, action: str, session_id: str
    ) -> None:
        """Record activity and potentially generate suggestions."""
        await self._tracker.record(user_input, action, session_id)

        if self._level == AutonomyLevel.REACTIVE:
            return  # Level 0: do nothing else

        # Respect cooldown to avoid re-evaluating on every single interaction
        now = time.monotonic()
        if now - self._last_eval_ts < EVAL_COOLDOWN_S:
            return
        self._last_eval_ts = now

        asyncio.create_task(self._evaluate_suggestions(session_id))

    async def _evaluate_suggestions(self, session_id: str) -> None:
        suggestions = await asyncio.to_thread(self._suggestion_engine.generate)
        for suggestion in suggestions:
            decision = await asyncio.to_thread(self._decision_engine.evaluate, suggestion)

            if decision.outcome == DecisionOutcome.SUPPRESS:
                continue

            # Anti-spam: skip if same text was surfaced recently
            now = time.time()
            last_shown = self._seen_suggestions.get(suggestion.text, 0.0)
            if now - last_shown < DEDUP_WINDOW_S:
                continue

            if decision.outcome == DecisionOutcome.SUGGEST:
                if len(self._pending_suggestions) >= MAX_PENDING:
                    continue  # don't overflow the queue
                self._pending_suggestions.append(suggestion.to_dict())
                self._seen_suggestions[suggestion.text] = now
                # Prune old seen entries (keep last 100)
                if len(self._seen_suggestions) > 100:
                    oldest = sorted(self._seen_suggestions, key=self._seen_suggestions.get)[:50]
                    for k in oldest:
                        del self._seen_suggestions[k]
                log_autonomy("suggestion_queued", action=suggestion.action, session_id=session_id)

            elif decision.outcome == DecisionOutcome.AUTO_EXECUTE:
                self._seen_suggestions[suggestion.text] = now
                await self._auto_execute(suggestion, session_id)

    async def _auto_execute(self, suggestion, session_id: str) -> None:
        """Execute a suggestion through the orchestrator (NOT directly)."""
        try:
            from core.orchestrator import get_orchestrator  # noqa: PLC0415
            orchestrator = get_orchestrator()
            log_autonomy(
                "autonomy_auto_execute",
                action=suggestion.action,
                session_id=session_id,
                text=suggestion.text,
            )
            await orchestrator.process(
                user_input=suggestion.text,
                session_id=session_id,
                source="autonomy",
            )
        except Exception as exc:
            log_error("auto_execute_error", action=suggestion.action, error=str(exc))

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_suggestions(self) -> list[dict[str, Any]]:
        """Return pending suggestions and clear the queue."""
        suggestions = list(self._pending_suggestions)
        self._pending_suggestions.clear()
        return suggestions

    def set_level(self, level: AutonomyLevel) -> None:
        self._level = level
        self._decision_engine = DecisionEngine(level)
        log_autonomy("autonomy_level_changed", new_level=level.value)

    def status(self) -> dict[str, Any]:
        return {
            "level": self._level.value,
            "level_name": self._level.name,
            "pending_suggestions": len(self._pending_suggestions),
            "top_actions": self._tracker.most_common_actions(top_n=5),
            "busiest_hours": self._tracker.busiest_hours(top_n=3),
        }


# ── Singleton ──────────────────────────────────────────────────────────────────

_manager: AutonomyManager | None = None


def get_autonomy_manager(level: AutonomyLevel | None = None) -> AutonomyManager:
    global _manager
    if _manager is None:
        _manager = AutonomyManager(level or DEFAULT_LEVEL)
    return _manager

