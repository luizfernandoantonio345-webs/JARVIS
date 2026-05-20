"""
routes/dashboard — FASE 12A

WebSocket /dashboard/stream — aggregates:
  - Autonomy controller events
  - Active AutoDev job status
  - System metrics (CPU/RAM via psutil if available)
  - Behavior profile summary

Pushes JSON updates every 2 seconds.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from pathlib import Path

router = APIRouter()
log = logging.getLogger(__name__)

DASHBOARD_HTML = Path(__file__).parent.parent.parent / "frontend" / "dashboard.html"


@router.get("/", response_class=HTMLResponse)
async def dashboard_page():
    """Serve the dashboard HTML page."""
    if DASHBOARD_HTML.exists():
        return FileResponse(str(DASHBOARD_HTML))
    return HTMLResponse("<h1>Dashboard HTML not found</h1>", status_code=404)


def _get_system_metrics() -> dict:
    try:
        import psutil
        return {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "ram_percent": psutil.virtual_memory().percent,
            "ram_used_mb": psutil.virtual_memory().used // (1024 * 1024),
        }
    except ImportError:
        return {}
    except Exception:
        return {}


def _get_active_jobs() -> list[dict]:
    try:
        from autodev.loop import _active_jobs
        jobs = []
        for job_id, loop in list(_active_jobs.items()):
            if loop._state:
                st = loop._state
                total = len(st.files_completed) if st.files_completed else 0
                jobs.append({
                    "job_id": job_id,
                    "goal": st.goal[:80] if st.goal else "",
                    "status": st.status,
                    "files_completed": total,
                })
        return jobs
    except Exception:
        return []


def _get_profile_summary() -> dict:
    try:
        from behavior.profile_manager import get_profile_manager
        p = get_profile_manager().get()
        return {
            "risk_tolerance": p.risk_tolerance,
            "verbosity": p.verbosity,
            "llm_routing": p.llm_routing,
            "test_preference": p.test_preference,
        }
    except Exception:
        return {}


def _get_autonomy_status() -> dict:
    try:
        return get_autonomy_controller().status_dict()
    except Exception:
        return {"state": "unknown"}


@router.websocket("/stream")
async def dashboard_stream(ws: WebSocket):
    """
    WebSocket endpoint for the real-time dashboard.
    Sends a full system snapshot every 2 seconds.
    """
    await ws.accept()
    log.info("Dashboard: client connected")
    _start = time.time()
    try:
        while True:
            payload = {
                "ts": time.time(),
                "uptime_seconds": time.time() - _start,
                "autonomy": _get_autonomy_status(),
                "active_jobs": _get_active_jobs(),
                "profile": _get_profile_summary(),
                "metrics": _get_system_metrics(),
            }
            await ws.send_json(payload)
            await asyncio.sleep(2.0)
    except WebSocketDisconnect:
        log.info("Dashboard: client disconnected")
    except Exception as exc:
        log.warning("Dashboard WS error: %s", exc)
