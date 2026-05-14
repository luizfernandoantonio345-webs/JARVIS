from __future__ import annotations

import uuid

from behavior.schemas import Pattern, Routine


def generate_routines(patterns: list[Pattern]) -> list[Routine]:
    routines: list[Routine] = []
    for pattern in patterns:
        if pattern.confidence < 0.65:
            continue
        action = pattern.evidence[0].split("@")[0] if pattern.evidence else pattern.name
        routines.append(Routine(
            id=uuid.uuid4().hex,
            name=f"Suggested routine for {action}",
            actions=[action],
            approved=False,
            risk_level="low",
        ))
    return routines

