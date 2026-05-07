"""
night_mode route — REST endpoints for Night Mode  (FASE 13A)

GET  /night-mode/status        — current state + last summary
POST /night-mode/trigger        — manually trigger night work (for testing)
POST /night-mode/morning        — manually trigger morning briefing
POST /night-mode/scheduler/start  — start/restart the scheduler
POST /night-mode/scheduler/stop   — stop the scheduler
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/status")
async def night_mode_status() -> dict:
    """Return current night mode state, last summary, and scheduler status."""
    from autonomy.night_mode import get_night_mode_controller
    from autonomy.night_scheduler import get_scheduler_status
    ctrl = get_night_mode_controller()
    return {
        **ctrl.get_status(),
        "scheduler": get_scheduler_status(),
    }


@router.post("/trigger")
async def trigger_night_work(background_tasks: BackgroundTasks) -> dict:
    """
    Manually trigger a full night work cycle.
    Runs in background so the request returns immediately.
    """
    from autonomy.night_mode import get_night_mode_controller, NightModeState
    ctrl = get_night_mode_controller()
    if ctrl.state == NightModeState.ACTIVE:
        raise HTTPException(status_code=409, detail="Night mode already running")

    async def _run() -> None:
        try:
            await ctrl.run_night_work()
        except Exception as exc:
            log.error("/night-mode/trigger background task failed: %s", exc)

    background_tasks.add_task(_run)
    return {"status": "started", "message": "Night work triggered in background"}


@router.post("/morning")
async def trigger_morning_briefing() -> dict:
    """Manually trigger the morning briefing generation and delivery."""
    from autonomy.night_mode import get_night_mode_controller
    ctrl = get_night_mode_controller()
    text = await ctrl.generate_morning_summary()

    # Also deliver via message bus
    try:
        from services.message_bus import MessageBus
        await MessageBus.get_instance().broadcast({
            "event": "morning_briefing",
            "text": text,
        })
    except Exception as exc:
        log.debug("morning_briefing broadcast suppressed: %s", exc)

    return {"status": "delivered", "briefing": text}


@router.post("/scheduler/start")
async def start_scheduler() -> dict:
    """Start (or restart) the night mode scheduler."""
    from autonomy.night_scheduler import start_night_scheduler, get_scheduler_status
    start_night_scheduler()
    return {"status": "started", **get_scheduler_status()}


@router.post("/scheduler/stop")
async def stop_scheduler() -> dict:
    """Stop the night mode scheduler."""
    from autonomy.night_scheduler import stop_night_scheduler, get_scheduler_status
    stop_night_scheduler()
    return {"status": "stopped", **get_scheduler_status()}
