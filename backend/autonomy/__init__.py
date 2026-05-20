"""
autonomy_v2 — Safe proactive intelligence layer.
Analyzes user patterns and generates suggestions WITHOUT executing autonomously
unless the safety gate explicitly allows it.

Level 0 — reactive only (no suggestions)
Level 1 — suggestions only (no auto-execution)
Level 2 — low-risk auto-execution only (must pass safety gate)
"""
from backend.autonomy.autonomy_manager import AutonomyManager, get_autonomy_manager
from backend.autonomy.autonomy_policy import AutonomyLevel
from backend.autonomy.safety_gate import SafetyGate

__all__ = ["AutonomyManager", "get_autonomy_manager", "AutonomyLevel", "SafetyGate"]
