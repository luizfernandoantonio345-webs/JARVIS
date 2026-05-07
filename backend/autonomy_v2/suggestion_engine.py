"""
Suggestion Engine — generates proactive suggestions based on user patterns.
Suggestions are NEVER executed automatically unless safety gate allows it.
"""
from __future__ import annotations

import time
from typing import Any

from autonomy_v2.activity_tracker import ActivityTracker
from core.logger import log_autonomy


class Suggestion:
    __slots__ = ("text", "action", "parameters", "confidence")

    def __init__(self, text: str, action: str, parameters: dict, confidence: float) -> None:
        self.text = text
        self.action = action
        self.parameters = parameters
        self.confidence = confidence

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "action": self.action,
            "parameters": self.parameters,
            "confidence": round(self.confidence, 3),
        }


class SuggestionEngine:
    """
    Generates suggestions based on:
    - Most frequently used actions
    - Time of day patterns
    - Repeated workflows
    """

    MIN_FREQUENCY = 3   # Action must appear at least this many times
    CONFIDENCE_THRESHOLD = 0.4

    def __init__(self, tracker: ActivityTracker) -> None:
        self._tracker = tracker

    def generate(self) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        current_hour = int(time.localtime().tm_hour)

        # Suggestion based on common actions
        for action, count in self._tracker.most_common_actions(top_n=3):
            if count < self.MIN_FREQUENCY:
                continue
            confidence = min(0.9, count / 20)
            if confidence < self.CONFIDENCE_THRESHOLD:
                continue
            text = self._action_to_suggestion_text(action, count)
            suggestions.append(Suggestion(
                text=text,
                action=action,
                parameters={},
                confidence=confidence,
            ))

        # Suggestion based on time-of-day pattern
        for hour, count in self._tracker.busiest_hours(top_n=2):
            if abs(hour - current_hour) <= 1 and count >= self.MIN_FREQUENCY:
                confidence = min(0.8, count / 15)
                suggestions.append(Suggestion(
                    text=f"You're usually active around this time. Ready to start your session?",
                    action="open_app",
                    parameters={"app": "code"},
                    confidence=confidence,
                ))
                break  # one time-based suggestion is enough

        log_autonomy("suggestions_generated", count=len(suggestions))
        return suggestions

    @staticmethod
    def _action_to_suggestion_text(action: str, count: int) -> str:
        templates: dict[str, str] = {
            "open_app": f"You often open apps ({count}×). Want me to open something?",
            "open_browser": f"You frequently browse the web. Want me to open the browser?",
            "go_to_url": f"You often navigate to URLs. Want me to go somewhere?",
            "run_shell": f"You frequently run shell commands. Start a terminal session?",
            "git_commit": f"You commit often ({count}×). Want to run a git commit now?",
            "write_file": f"You write files often ({count}×). Create a new file?",
        }
        return templates.get(action, f"You often use '{action}' ({count}×). Run it again?")
