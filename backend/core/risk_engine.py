"""
Unified Risk Engine — wraps existing intents.risk_evaluator.
ALL risk decisions must go through this module.

Returns a RiskDecision enum so callers don't import intents layer.
"""
from __future__ import annotations

from enum import Enum

try:
    from intents.risk_evaluator import evaluate_risk as _legacy_evaluate
    from intents.schemas import Intent, RiskLevel
except ImportError:
    from backend.intents.risk_evaluator import evaluate_risk as _legacy_evaluate
    from backend.intents.schemas import Intent, RiskLevel


class RiskDecision(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def evaluate_risk(intent: Intent | None) -> RiskDecision:
    """
    Evaluate the risk of an intent.
    Returns RiskDecision.LOW for None (chat-only input).
    """
    if intent is None:
        return RiskDecision.LOW

    enriched = _legacy_evaluate(intent)
    level: RiskLevel = enriched.risk_level
    return RiskDecision(level)


def is_safe_to_auto_execute(risk: RiskDecision, autonomy_level: int) -> bool:
    """
    Returns True only if the action is safe for autonomous execution
    at the given autonomy level.

    Level 0 — reactive only, never auto-execute
    Level 1 — suggestions only, never auto-execute
    Level 2 — low-risk only
    """
    if autonomy_level < 2:
        return False
    return risk == RiskDecision.LOW
