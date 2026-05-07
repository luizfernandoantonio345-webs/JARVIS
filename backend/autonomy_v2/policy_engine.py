from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable


class PolicyDecision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_CONFIRMATION = "REQUIRE_CONFIRMATION"


@dataclass
class Event:
    type: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Policy:
    name: str
    event_type: str
    action: str
    risk: str
    auto_approve: bool = False
    require_confirmation: bool = False
    block: bool = False
    condition: Callable[[Event], bool] = lambda event: True


class PolicyEngine:
    def __init__(self, policies: list[Policy] | None = None) -> None:
        self.policies = policies or default_policies()

    def evaluate(self, event: Event) -> PolicyDecision:
        for policy in self.policies:
            if policy.event_type != event.type:
                continue
            if not policy.condition(event):
                continue
            if policy.block:
                return PolicyDecision.DENY
            safe_mode = bool(event.metadata.get("safe_mode", True))
            if policy.require_confirmation or not policy.auto_approve:
                return PolicyDecision.REQUIRE_CONFIRMATION
            if policy.risk == "low" and safe_mode:
                return PolicyDecision.ALLOW
            return PolicyDecision.REQUIRE_CONFIRMATION
        return PolicyDecision.DENY


def default_policies() -> list[Policy]:
    return [
        Policy(
            name="idle_detected",
            event_type="idle_detected",
            action="run_daily_briefing",
            risk="low",
            auto_approve=True,
            condition=lambda event: float(event.metadata.get("idle_seconds", 0)) > 300
            and bool(event.metadata.get("safe_mode", True)),
        ),
        Policy(
            name="file_changed",
            event_type="file_changed",
            action="run_linter_check",
            risk="low",
            auto_approve=True,
            condition=lambda event: _watched_source_file(event.metadata.get("file", "")),
        ),
        Policy(
            name="error_in_log",
            event_type="error_in_log",
            action="notify_owner",
            risk="low",
            auto_approve=True,
            condition=lambda event: str(event.metadata.get("severity", "")).upper() == "ERROR"
            and int(event.metadata.get("repeated", 0)) > 3,
        ),
        Policy(
            name="disk_above_90pct",
            event_type="disk_above_90pct",
            action="notify_owner",
            risk="low",
            auto_approve=True,
            condition=lambda event: float(event.metadata.get("disk_usage", 0)) > 90,
        ),
        Policy(
            name="auto_commit",
            event_type="auto_commit",
            action="git_commit",
            risk="medium",
            auto_approve=False,
            require_confirmation=True,
        ),
        Policy(
            name="delete_files",
            event_type="delete_files",
            action="delete",
            risk="high",
            auto_approve=False,
            block=True,
        ),
    ]


def _watched_source_file(path: str) -> bool:
    suffix = Path(path).suffix.lower()
    return suffix in {".py", ".ts"} and any(part in path.replace("\\", "/") for part in ("backend/", "frontend/", "src/"))


def run_policy_self_tests() -> dict[str, Any]:
    engine = PolicyEngine()
    cases = [
        (Event("idle_detected", {"idle_seconds": 301, "safe_mode": True}), PolicyDecision.ALLOW),
        (Event("file_changed", {"file": "backend/main.py"}), PolicyDecision.ALLOW),
        (Event("error_in_log", {"severity": "ERROR", "repeated": 4}), PolicyDecision.ALLOW),
        (Event("disk_above_90pct", {"disk_usage": 91}), PolicyDecision.ALLOW),
        (Event("auto_commit", {}), PolicyDecision.REQUIRE_CONFIRMATION),
        (Event("delete_files", {}), PolicyDecision.DENY),
    ]
    failures = []
    for event, expected in cases:
        actual = engine.evaluate(event)
        if actual != expected:
            failures.append({"event": event.type, "expected": expected.value, "actual": actual.value})
    return {"ok": not failures, "failures": failures, "count": len(cases)}
