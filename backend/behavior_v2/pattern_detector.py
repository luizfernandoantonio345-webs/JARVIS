from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime

from behavior_v2.schemas import Pattern


def detect_patterns(event_logs: list) -> list[Pattern]:
    events = [e if isinstance(e, dict) else getattr(e, "model_dump", lambda: {})() for e in event_logs]
    patterns: list[Pattern] = []

    actions = [str(e.get("action", "")) for e in events if e.get("action")]
    for action, count in Counter(actions).most_common(5):
        if count >= 3:
            patterns.append(Pattern(
                name=f"repeated:{action}",
                description=f"Action '{action}' repeated {count} times.",
                confidence=min(0.95, 0.45 + count * 0.1),
                evidence=[action],
            ))

    by_hour: dict[tuple[str, int], int] = defaultdict(int)
    for e in events:
        action = str(e.get("action", ""))
        raw_ts = e.get("timestamp")
        try:
            ts = raw_ts if isinstance(raw_ts, datetime) else datetime.fromisoformat(str(raw_ts))
        except Exception:
            continue
        by_hour[(action, ts.hour)] += 1
    for (action, hour), count in by_hour.items():
        if action and count >= 3:
            patterns.append(Pattern(
                name=f"time:{action}:{hour}",
                description=f"Action '{action}' often happens near {hour:02d}:00.",
                confidence=min(0.9, 0.4 + count * 0.12),
                evidence=[f"{action}@{hour:02d}:00"],
            ))
    return patterns

