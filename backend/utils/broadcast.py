"""
utils/broadcast.py — Convenience helpers for posting WS status updates
from anywhere in the backend without importing main.py.

Usage:
    from utils.broadcast import broadcast_status
    await broadcast_status("thinking", "Analisando...", source="planner")
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests

log = logging.getLogger(__name__)

_JARVIS_API = os.getenv("JARVIS_API_URL", "http://localhost:8000")


def broadcast_status(
    status: str,
    message: str,
    *,
    source: str = "system",
    data: dict[str, Any] | None = None,
    audio_url: str | None = None,
    task_id: str | None = None,
) -> bool:
    """POST a WS status update to the local JARVIS API (non-blocking HTTP).

    Returns True on success, False on failure (best-effort — never raises).
    """
    payload: dict[str, Any] = {
        "status": status,
        "message": message,
        "source": source,
        "ts": time.time(),
    }
    if data:
        payload["data"] = data
    if audio_url:
        payload["audio_url"] = audio_url
    if task_id:
        payload["task_id"] = task_id

    try:
        resp = requests.post(
            f"{_JARVIS_API}/system/update",
            json=payload,
            timeout=3,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        log.debug("[broadcast_status] failed: %s", exc)
        return False
