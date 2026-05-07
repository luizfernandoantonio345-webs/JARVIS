"""
Decision Engine — evaluates whether a suggestion should be:
  - surfaced to the user (Level 1+)
  - auto-executed (Level 2 only, low-risk only, safety gate must pass)

This module NEVER calls tools directly. It returns a DecisionResult that
the AutonomyManager acts on through the orchestrator.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from autonomy_v2.autonomy_policy import AutonomyLevel
from autonomy_v2.safety_gate import SafetyGate
from autonomy_v2.suggestion_engine import Suggestion
from core.logger import log_autonomy
from core.risk_engine import RiskDecision, evaluate_risk
from intents.schemas import Intent


class DecisionOutcome(str, Enum):
    SUPPRESS = "suppress"      # Level 0 or too low confidence
    SUGGEST = "suggest"        # Show to user, do not execute
    AUTO_EXECUTE = "auto_execute"  # Safe to run without user prompt


@dataclass
class DecisionResult:
    outcome: DecisionOutcome
    suggestion: Suggestion
    risk: RiskDecision
    reason: str


class DecisionEngine:
    def __init__(self, level: AutonomyLevel) -> None:
        self._level = level
        self._gate = SafetyGate()

    def evaluate(self, suggestion: Suggestion) -> DecisionResult:
        # Level 0 — suppress everything
        if self._level == AutonomyLevel.REACTIVE:
            return DecisionResult(
                outcome=DecisionOutcome.SUPPRESS,
                suggestion=suggestion,
                risk=RiskDecision.LOW,
                reason="autonomy level 0: reactive only",
            )

        # Build a minimal Intent to evaluate risk
        intent = Intent(
            action=suggestion.action,
            parameters=suggestion.parameters,
            steps=[],
        )
        risk = evaluate_risk(intent)

        # Level 1 — suggestions only, never execute
        if self._level == AutonomyLevel.SUGGESTIONS:
            outcome = DecisionOutcome.SUGGEST if suggestion.confidence >= 0.4 else DecisionOutcome.SUPPRESS
            log_autonomy("decision_suggest", action=suggestion.action, risk=risk.value)
            return DecisionResult(outcome=outcome, suggestion=suggestion, risk=risk, reason="level 1: suggest only")

        # Level 2 — may auto-execute if safety gate passes
        if self._gate.check(risk, self._level):
            log_autonomy("decision_auto_execute", action=suggestion.action, risk=risk.value)
            return DecisionResult(
                outcome=DecisionOutcome.AUTO_EXECUTE,
                suggestion=suggestion,
                risk=risk,
                reason="level 2: low-risk auto-execution allowed",
            )

        # Failed safety gate — fall back to suggest
        return DecisionResult(
            outcome=DecisionOutcome.SUGGEST,
            suggestion=suggestion,
            risk=risk,
            reason="safety gate blocked auto-execution; surfacing as suggestion",
        )
