"""
event_router — FASE 11A

Receives events from EventDetector, matches them against rules.json,
and dispatches goals to the MultiAgentOrchestrator.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

RULES_FILE = Path(__file__).parent / "rules.json"


class EventRouter:
    """
    Matches incoming events to routing rules and generates action goals.

    Rules are loaded from rules.json. Each rule has:
      trigger: conditions to match
      action:  goal template (may contain {path}, {message}, {job_id}, {goal})
      priority: lower = more urgent (1=critical, 2=normal, 3=low)
    """

    def __init__(self, session_id: str = "autonomy") -> None:
        self._session_id = session_id
        self._rules: list[dict] = []
        self._reload_rules()

    def _reload_rules(self) -> None:
        if RULES_FILE.exists():
            try:
                self._rules = json.loads(RULES_FILE.read_text(encoding="utf-8"))
                self._rules.sort(key=lambda r: r.get("priority", 9))
            except Exception as exc:
                log.warning("EventRouter: failed to load rules.json: %s", exc)
                self._rules = []

    def _match_trigger(self, trigger: dict, event: Any) -> bool:
        """Return True if event satisfies all trigger conditions."""
        evt_type = getattr(event, "event_type", "")
        if trigger.get("event_type") and trigger["event_type"] != evt_type:
            return False

        # FileEvent conditions
        if evt_type == "file":
            ct = trigger.get("change_type")
            if ct and isinstance(ct, list) and event.change_type not in ct:
                return False
            if ct and isinstance(ct, str) and event.change_type != ct:
                return False
            ext = trigger.get("extension")
            if ext and not event.path.endswith(ext):
                return False

        # LogEvent conditions
        if evt_type == "log":
            lvl = trigger.get("level")
            if lvl and isinstance(lvl, list) and event.level not in lvl:
                return False
            if lvl and isinstance(lvl, str) and event.level != lvl:
                return False
            msg_contains = trigger.get("message_contains")
            if msg_contains and msg_contains.lower() not in event.message.lower():
                return False

        # IdleEvent conditions
        if evt_type == "idle":
            if "pending_jobs_gt" in trigger and event.pending_jobs_count <= trigger["pending_jobs_gt"]:
                return False
            if "pending_jobs_eq" in trigger and event.pending_jobs_count != trigger["pending_jobs_eq"]:
                return False

        return True

    def _render_action(self, template: str, event: Any) -> str:
        """Substitute event fields into the action template."""
        subs: dict[str, str] = {
            "path": getattr(event, "path", ""),
            "message": getattr(event, "message", ""),
            "job_id": getattr(event, "job_id", ""),
            "goal": getattr(event, "goal", ""),
            "task_name": getattr(event, "task_name", ""),
        }
        result = template
        for k, v in subs.items():
            result = result.replace("{" + k + "}", v)
        return result

    def route(self, event: Any) -> list[dict]:
        """
        Match event against rules and return list of action dicts.

        Returns:
            List of { rule_id, goal, priority } — usually 0 or 1 items.
        """
        actions = []
        for rule in self._rules:
            trigger = rule.get("trigger", {})
            if self._match_trigger(trigger, event):
                goal = self._render_action(rule.get("action", ""), event)
                if goal.strip():
                    actions.append({
                        "rule_id": rule.get("id", "unknown"),
                        "goal": goal,
                        "priority": rule.get("priority", 3),
                    })
                    break  # first matching rule wins (rules are priority-sorted)
        return actions

    async def dispatch(self, goal: str, rule_id: str = "manual") -> dict:
        """
        Send a goal to the MultiAgentOrchestrator and return the result.
        """
        try:
            from agents.multi_agent_orchestrator import MultiAgentOrchestrator
            orch = MultiAgentOrchestrator(session_id=self._session_id)
            result = await orch.run(goal)
            return {
                "rule_id": rule_id,
                "goal": goal,
                "status": result.status,
                "output": result.output[:2000] if result.output else "",
            }
        except Exception as exc:
            log.error("EventRouter.dispatch failed: %s", exc)
            return {"rule_id": rule_id, "goal": goal, "status": "error", "output": str(exc)}
