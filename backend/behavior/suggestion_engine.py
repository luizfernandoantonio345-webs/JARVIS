from __future__ import annotations

from datetime import datetime

from behavior.schemas import Suggestion


def generate_suggestion(context) -> Suggestion | None:
    patterns = context.get("patterns", []) if isinstance(context, dict) else []
    now = datetime.now()
    for pattern in patterns:
        name = pattern.get("name", "") if isinstance(pattern, dict) else pattern.name
        confidence = pattern.get("confidence", 0.0) if isinstance(pattern, dict) else pattern.confidence
        if confidence >= 0.65:
            action = name.split(":")[1] if ":" in name else None
            return Suggestion(
                text=f"Voce costuma fazer isso por volta de agora. Quer que eu execute {action or 'essa rotina'}?",
                confidence=confidence,
                reason=f"Pattern matched at {now.hour:02d}:00: {name}",
                action=action,
            )
    return None

