from __future__ import annotations

import json
import tempfile
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

_MAX_EVENTS = 500
_events: deque[dict[str, Any]] = deque(maxlen=_MAX_EVENTS)
_lock = Lock()
_audit_path = Path(tempfile.gettempdir()) / "jarvis_audit_log.jsonl"


def append_audit_event(
    *,
    action_type: str,
    risk_level: str,
    target: str = "",
    preview: str = "",
    decision: str,
    confirmed_by: str | None = None,
    result: str = "pending",
    duration_ms: float = 0.0,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = {
        "audit_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action_type": action_type,
        "risk_level": risk_level,
        "target": target,
        "preview": preview,
        "decision": decision,
        "confirmed_by": confirmed_by,
        "result": result,
        "duration_ms": round(float(duration_ms), 2),
        "metadata": metadata or {},
    }
    with _lock:
        _events.appendleft(event)
        try:
            with _audit_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        except OSError:
            pass
    return event


def list_audit_events(limit: int = 100, risk: str | None = None) -> list[dict[str, Any]]:
    limit = max(1, min(limit, _MAX_EVENTS))
    with _lock:
        items = list(_events)
    if risk:
        items = [item for item in items if item.get("risk_level") == risk]
    return items[:limit]


def update_audit_decision(
    audit_id: str,
    *,
    decision: str,
    confirmed_by: str = "user",
    result: str = "pending",
) -> dict[str, Any] | None:
    with _lock:
        for item in _events:
            if item.get("audit_id") == audit_id:
                item["decision"] = decision
                item["confirmed_by"] = confirmed_by
                item["result"] = result
                item["updated_at"] = datetime.now(timezone.utc).isoformat()
                return dict(item)
    return None
