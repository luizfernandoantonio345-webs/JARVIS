"""
routes/autonomy — FASE 11A

POST /autonomy/start
POST /autonomy/pause
POST /autonomy/stop
POST /autonomy/resume
POST /autonomy/confirm/{confirm_id}  — answer a safe-mode confirmation
GET  /autonomy/status
GET  /autonomy/log
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.autonomy.controller import get_autonomy_controller

router = APIRouter()


def _ctrl():
    return get_autonomy_controller()


# ── Lifecycle endpoints ───────────────────────────────────────────────────────

@router.post("/start")
async def autonomy_start():
    """Start the autonomous event loop."""
    ctrl = _ctrl()
    await ctrl.start()
    return {"ok": True, "state": ctrl.status_dict()["state"]}


@router.post("/pause")
async def autonomy_pause():
    """Pause the autonomous event loop (keeps watching, skips actions)."""
    ctrl = _ctrl()
    await ctrl.pause()
    return {"ok": True, "state": ctrl.status_dict()["state"]}


@router.post("/resume")
async def autonomy_resume():
    """Resume a paused event loop."""
    ctrl = _ctrl()
    await ctrl.resume()
    return {"ok": True, "state": ctrl.status_dict()["state"]}


@router.post("/stop")
async def autonomy_stop():
    """Stop the autonomous event loop completely."""
    ctrl = _ctrl()
    await ctrl.stop()
    return {"ok": True, "state": ctrl.status_dict()["state"]}


# ── Confirmation endpoint ─────────────────────────────────────────────────────

class ConfirmBody(BaseModel):
    approved: bool


@router.post("/confirm/{confirm_id}")
async def autonomy_confirm(confirm_id: str, body: ConfirmBody):
    """
    Respond to a safe-mode confirmation request from the Event Loop.
    Used when the dashboard or voice presents a 'Confirm?' prompt.
    """
    _ctrl().confirm(confirm_id, body.approved)
    return {"ok": True, "confirm_id": confirm_id, "approved": body.approved}


# ── Status + log endpoints ─────────────────────────────────────────────────────

@router.get("/status")
async def autonomy_status():
    """
    Return current autonomy state and today's metrics.

    Returns:
        state, events_today, actions_taken, last_action
    """
    return _ctrl().status_dict()


@router.get("/log")
async def autonomy_log(limit: int = 50):
    """Return last N autonomous actions with their results (from SQLite)."""
    limit = min(max(1, limit), 200)
    return {"log": _ctrl().get_db_log(limit=limit)}
