from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from core.audit_log import append_audit_event


@dataclass
class Action:
    action_type: str
    target: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    preview: str = ""


@dataclass
class SafetyDecision:
    allowed: bool
    decision: str
    risk_level: str
    action_type: str
    target: str = ""
    preview: str = ""
    reason: str = ""
    audit_id: str | None = None
    requires_confirmation: bool = False

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


class SafetyGate:
    RISK_LEVELS = {
        "read_file": "low",
        "write_file": "medium",
        "delete_file": "high",
        "shell_exec": "high",
        "git_push": "medium",
        "git_force_push": "critical",
        "install_package": "medium",
        "run_script": "high",
        "web_request": "low",
        "system_restart": "critical",
        "open_app": "low",
        "status": "low",
        "stop": "low",
        "voice_mute": "low",
        "voice_enable": "low",
        "daily_report": "low",
        "next_steps": "low",
        "search_web": "low",
        "night_mode": "low",
        "take_screenshot": "low",
        "create_file": "medium",
        "git_commit": "medium",
        "run_command": "high",
        "clear_memory": "high",
    }

    async def evaluate(self, action: Action) -> SafetyDecision:
        started = time.perf_counter()
        risk = self.RISK_LEVELS.get(action.action_type, "medium")
        preview = action.preview or self._build_preview(action)

        if risk == "low":
            decision = SafetyDecision(
                allowed=True,
                decision="approved",
                risk_level=risk,
                action_type=action.action_type,
                target=action.target,
                preview=preview,
                reason="Low-risk action auto-approved.",
                requires_confirmation=False,
            )
        elif risk == "medium":
            decision = SafetyDecision(
                allowed=False,
                decision="pending_confirmation",
                risk_level=risk,
                action_type=action.action_type,
                target=action.target,
                preview=preview,
                reason="Medium-risk action requires dry-run review.",
                requires_confirmation=True,
            )
        elif risk == "high":
            decision = SafetyDecision(
                allowed=False,
                decision="pending_confirmation",
                risk_level=risk,
                action_type=action.action_type,
                target=action.target,
                preview=preview,
                reason="High-risk action requires explicit confirmation.",
                requires_confirmation=True,
            )
        else:
            decision = SafetyDecision(
                allowed=False,
                decision="blocked",
                risk_level=risk,
                action_type=action.action_type,
                target=action.target,
                preview=preview,
                reason="Critical action blocked until explicit manual approval flow exists.",
                requires_confirmation=True,
            )

        event = append_audit_event(
            action_type=action.action_type,
            risk_level=risk,
            target=action.target,
            preview=preview,
            decision=decision.decision,
            confirmed_by="auto" if decision.allowed else None,
            result="approved" if decision.allowed else decision.decision,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            metadata={"parameters": action.parameters},
        )
        decision.audit_id = event["audit_id"]
        return decision

    def _build_preview(self, action: Action) -> str:
        if not action.parameters:
            return f"Executar acao: {action.action_type}"
        safe_pairs = []
        for key, value in action.parameters.items():
            text = str(value)
            if len(text) > 200:
                text = text[:197] + "..."
            safe_pairs.append(f"{key}={text}")
        return f"{action.action_type}: " + ", ".join(safe_pairs)


safety_gate = SafetyGate()


def check_safety(message: str) -> dict:
    """Convenience function — quick synchronous risk check for a text message."""
    _dangerous = ["bomb", "kill", "hack", "exploit", "malware", "ransom", "ddos", "rm -rf", "delete all"]
    text = message.lower()
    risk = "low"
    for kw in _dangerous:
        if kw in text:
            risk = "high"
            break
    return {"allowed": risk == "low", "risk_level": risk, "message": message[:100]}
