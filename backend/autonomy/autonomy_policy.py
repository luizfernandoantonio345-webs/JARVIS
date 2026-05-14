"""
Autonomy Policy — defines the 3-level autonomy model.
"""
from __future__ import annotations

from enum import IntEnum


class AutonomyLevel(IntEnum):
    """
    LEVEL 0 — Reactive only. No suggestions, no auto-execution.
    LEVEL 1 — Suggestions only. No auto-execution.
    LEVEL 2 — Safe auto-execution of LOW-risk actions only.
    """
    REACTIVE = 0
    SUGGESTIONS = 1
    AUTO_SAFE = 2


# Default level used if not configured
DEFAULT_LEVEL = AutonomyLevel.REACTIVE
