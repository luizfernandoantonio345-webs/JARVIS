"""
health — FASE 12C (replaces routes/health.py basic check)

Unified health check: GET /health
Returns < 500ms with status of every system component.
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import time
from pathlib import Path

from fastapi import APIRouter

from config import get_config

log = logging.getLogger(__name__)
router = APIRouter()

_START_TIME = time.time()
VERSION = "1.0.0"


def _check_llm() -> dict:
    try:
        from services.llm_service import get_model_info
        info = get_model_info()
        return {"status": "ok", "active_model": info.get("local_model", "unknown"),
                "latency_ms": None}
    except Exception as exc:
        return {"status": "error", "error": str(exc)[:100]}


def _check_memory() -> dict:
    try:
        db = get_config().memory_db_path
        with sqlite3.connect(str(db), timeout=2.0) as conn:
            entries = conn.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
        size_mb = db.stat().st_size / (1024 * 1024) if db.exists() else 0
        return {"status": "ok", "entries": entries, "db_size_mb": round(size_mb, 2)}
    except Exception as exc:
        return {"status": "error", "error": str(exc)[:100]}


def _check_autonomy() -> dict:
    try:
        from autonomy.controller import get_autonomy_controller
        ctrl = get_autonomy_controller()
        st = ctrl.status_dict()
        return {
            "status": st["state"],
            "events_today": st["events_today"],
            "actions_today": st["actions_taken"],
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)[:100]}


def _check_autodev() -> dict:
    try:
        from autodev.loop import _active_jobs
        active = sum(
            1 for loop in _active_jobs.values()
            if loop._state and loop._state.status not in {"done", "escalated", "error"}
        )
        return {"status": "ok", "active_jobs": active}
    except Exception as exc:
        return {"status": "error", "error": str(exc)[:100]}


def _check_agents() -> dict:
    try:
        from services.memory_service import load_recent_episodic
        entries = load_recent_episodic(n=1)
        last_ts = entries[0][0] if entries else None
        if last_ts:
            delta = int(time.time() - last_ts)
            last_str = f"{delta // 60}min ago" if delta < 3600 else f"{delta // 3600}h ago"
        else:
            last_str = "never"
        return {"status": "ok", "last_run": last_str}
    except Exception as exc:
        return {"status": "ok", "last_run": "unknown"}


def _check_vscode() -> dict:
    try:
        from integrations.vscode_bridge import VSCodeBridge
        bridge = VSCodeBridge()
        connected = bridge.is_connected() if hasattr(bridge, "is_connected") else None
        return {"status": "connected" if connected else "disconnected"}
    except Exception:
        return {"status": "unknown"}


def _check_behavior() -> dict:
    try:
        from behavior.profile_manager import get_profile_manager
        p = get_profile_manager().get()
        return {"risk": p.risk_tolerance, "verbosity": p.verbosity}
    except Exception as exc:
        return {"status": "error", "error": str(exc)[:100]}


@router.get("/health")
async def health_check():
    """
    Unified health check — all components in one call.

    Returns:
        status: healthy | degraded | unhealthy
        components: per-component status dict
        uptime_hours, version
    """
    t0 = time.time()
    uptime_s = t0 - _START_TIME

    components = {
        "llm_router":       _check_llm(),
        "memory":           _check_memory(),
        "autonomy":         _check_autonomy(),
        "autodev":          _check_autodev(),
        "agents":           _check_agents(),
        "vscode_bridge":    _check_vscode(),
        "behavior_profile": _check_behavior(),
    }

    # Aggregate status
    statuses = {v.get("status", "error") for v in components.values()}
    if "error" in statuses:
        overall = "degraded"
    elif all(s in {"ok", "healthy", "connected", "running", "stopped", "paused",
                   "unknown", "disconnected"} for s in statuses):
        overall = "healthy"
    else:
        overall = "degraded"

    return {
        "status": overall,
        "components": components,
        "uptime_hours": round(uptime_s / 3600, 2),
        "version": VERSION,
        "response_ms": round((time.time() - t0) * 1000, 1),
    }
