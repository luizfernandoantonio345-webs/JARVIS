"""
Safety Gate — ALL autonomous actions must pass this check.

Rules:
  HIGH risk   → NEVER auto-execute
  MEDIUM risk → require user confirmation
  LOW risk    → allow only at LEVEL 2
"""
from __future__ import annotations

from core.logger import log_security
from core.risk_engine import RiskDecision
from autonomy.autonomy_policy import AutonomyLevel


class SafetyGate:
    """Stateless safety evaluator for autonomous actions."""

    @staticmethod
    def check(risk: RiskDecision, level: AutonomyLevel) -> bool:
        """
        Returns True if the action is permitted to auto-execute.

        HIGH  → always False
        MEDIUM → always False (requires explicit confirmation via orchestrator)
        LOW   → True only at LEVEL 2
        """
        if risk == RiskDecision.HIGH:
            log_security("safety_gate_blocked_high_risk", risk=risk.value, level=level.value)
            return False
        if risk == RiskDecision.MEDIUM:
            log_security("safety_gate_blocked_medium_risk", risk=risk.value, level=level.value)
            return False
        # LOW risk
        if level < AutonomyLevel.AUTO_SAFE:
            return False
        return True

    @staticmethod
    def requires_confirmation(risk: RiskDecision) -> bool:
        return risk in (RiskDecision.HIGH, RiskDecision.MEDIUM)
