"""
health — Unified health check: GET /health
Returns 200 always, with status ok/degraded.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from pathlib import Path

from fastapi import APIRouter

from config import get_config
from backend.ai.client import get_ai_client

log = logging.getLogger(__name__)
router = APIRouter()

_START_TIME = time.time()
VERSION = "5.2"


def _check_llm() -> dict:
    try:
        health = get_ai_client().health_check()
        return {"ok": health["ok"], "url": get_ai_client().ollama_url, "model": get_ai_client().model}
    except Exception as exc:
        return {"ok": False, "url": "unknown", "model": "unknown"}


def _check_memory() -> dict:
    try:
        db = get_config().memory_db_path
        with sqlite3.connect(str(db), timeout=2.0) as conn:
            conn.execute("SELECT 1").fetchone()
        return {"ok": True}
    except Exception:
        return {"ok": False}


def _check_voice() -> dict:
    try:
        cfg = get_config()
        return {"ok": True, "enabled": cfg.voice_enabled}
    except Exception:
        return {"ok": False, "enabled": False}


def _check_autonomy() -> dict:
    try:
        from autonomy.controller import get_autonomy_controller
        ctrl = get_autonomy_controller()
        return {"ok": True}
    except Exception:
        return {"ok": False}


def _check_websocket() -> dict:
    return {"ok": True}


@router.get("/health")
async def health_check():
    """
    Unified health check — returns 200 always.

    Returns:
        status: ok | degraded
        version: "5.2"
        components: per-component status
        degraded: list of failing components
    """
    components = {
        "llm": _check_llm(),
        "memory": _check_memory(),
        "voice": _check_voice(),
        "autonomy": _check_autonomy(),
        "websocket": _check_websocket(),
    }

    # Determine degraded components
    degraded = [k for k, v in components.items() if not v.get("ok", True)]

    # Overall status
    status = "degraded" if degraded else "ok"

    return {
        "status": status,
        "version": VERSION,
        "components": components,
        "degraded": degraded,
    }
