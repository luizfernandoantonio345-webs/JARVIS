"""
night_scheduler — Asyncio-based cron scheduler for Night Mode  (FASE 13A)

Schedules two daily events using asyncio.sleep with wall-clock alignment:

  NIGHT_START_HOUR  (default 23:00)
    → NightModeController.run_night_work()

  MORNING_HOUR      (default 07:00)
    → NightModeController.generate_morning_summary()
    → DailyBriefing.deliver()  (via message bus so TTS picks it up)

No external dependencies — pure asyncio + datetime.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone, time as dtime
from typing import Any

from config import get_config

log = logging.getLogger(__name__)

_scheduler_task: asyncio.Task | None = None


# ── Time helpers ──────────────────────────────────────────────────────────────

def _seconds_until(hour: int, minute: int = 0) -> float:
    """Return seconds from now until the next occurrence of HH:MM (local time)."""
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


# ── Scheduler loop ────────────────────────────────────────────────────────────

async def _night_scheduler_loop() -> None:
    """
    Perpetual loop that fires night_work at NIGHT_START_HOUR and
    morning_briefing at MORNING_HOUR every day.
    """
    cfg = get_config()

    while True:
        night_start_h = cfg.night_mode_start_hour     # default 23
        morning_h     = cfg.night_mode_morning_hour   # default 7

        now_h = datetime.now().hour

        # Determine which event fires next
        secs_night   = _seconds_until(night_start_h)
        secs_morning = _seconds_until(morning_h)
        next_secs    = min(secs_night, secs_morning)

        log.info(
            "NightScheduler: next night=%dh in %.0fs, next morning=%dh in %.0fs — sleeping %.0fs",
            night_start_h, secs_night, morning_h, secs_morning, next_secs,
        )
        await asyncio.sleep(next_secs)

        # Re-evaluate which event is due (could be both if very close)
        now_h = datetime.now().hour
        now_m = datetime.now().minute

        if abs(_seconds_until(night_start_h) - 0) < 120 or \
           (now_h == night_start_h and now_m < 5):
            await _fire_night_work()
        elif abs(_seconds_until(morning_h) - 0) < 120 or \
             (now_h == morning_h and now_m < 5):
            await _fire_morning_briefing()
        else:
            # Recalculate — we woke up at the right time for one of them
            if secs_night <= secs_morning:
                await _fire_night_work()
            else:
                await _fire_morning_briefing()


async def _fire_night_work() -> None:
    log.info("NightScheduler: ▶ starting night work")
    try:
        from autonomy.night_mode import get_night_mode_controller
        ctrl = get_night_mode_controller()
        summary = await ctrl.run_night_work()
        log.info(
            "NightScheduler: ✓ night work done — jobs=%d tests_passed=%d",
            summary.jobs_processed, summary.test_passed,
        )
    except Exception as exc:
        log.error("NightScheduler: night work failed: %s", exc, exc_info=True)


async def _fire_morning_briefing() -> None:
    log.info("NightScheduler: ▶ generating morning briefing")
    try:
        from autonomy.night_mode import get_night_mode_controller
        from autonomy.daily_briefing import DailyBriefing

        ctrl = get_night_mode_controller()
        night_summary = await ctrl.generate_morning_summary()

        # Merge with the standard daily briefing
        briefing = DailyBriefing()
        daily_text = briefing.compose()
        full_text = f"{daily_text}\n\n{night_summary}"

        # Broadcast to WS so TTS and dashboard pick it up
        try:
            from services.message_bus import MessageBus
            await MessageBus.get_instance().broadcast({
                "event": "morning_briefing",
                "text": full_text,
                "night_summary": night_summary,
            })
        except Exception as exc:
            log.debug("NightScheduler: message bus broadcast suppressed: %s", exc)

        # Restore operational_mode to previous mode recorded before night run
        try:
            from core.system_mode import apply_mode
            from config import get_config
            status = ctrl.get_status()
            prev_mode = None
            if status.get("summary"):
                prev_mode = status["summary"].get("previous_mode")
            if not prev_mode and status.get("last_summary"):
                prev_mode = status["last_summary"].get("previous_mode")

            target_mode = prev_mode if prev_mode in {"dev", "assistant", "silent"} else get_config().operational_mode
            apply_mode(target_mode)
            log.info("NightScheduler: operational_mode restored to %s", target_mode)
        except Exception as exc:
            log.debug("NightScheduler: mode restore suppressed: %s", exc)

        log.info("NightScheduler: ✓ morning briefing delivered")
    except Exception as exc:
        log.error("NightScheduler: morning briefing failed: %s", exc, exc_info=True)


# ── Public API ────────────────────────────────────────────────────────────────

def start_night_scheduler() -> asyncio.Task:
    """
    Start the night scheduler as a background asyncio task.
    Safe to call multiple times — only one instance runs at a time.
    Returns the running Task.
    """
    global _scheduler_task
    if _scheduler_task is not None and not _scheduler_task.done():
        log.info("NightScheduler: already running")
        return _scheduler_task

    _scheduler_task = asyncio.create_task(_night_scheduler_loop(), name="night_scheduler")
    _scheduler_task.add_done_callback(
        lambda t: log.error("NightScheduler crashed: %s", t.exception())
        if not t.cancelled() and t.exception() else None
    )
    log.info("NightScheduler: started (night=%dh, morning=%dh)",
             get_config().night_mode_start_hour,
             get_config().night_mode_morning_hour)
    return _scheduler_task


def stop_night_scheduler() -> None:
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        log.info("NightScheduler: stopped")


def get_scheduler_status() -> dict[str, Any]:
    """Return scheduler state for health/status endpoints."""
    running = _scheduler_task is not None and not _scheduler_task.done()
    cfg = get_config()
    return {
        "running": running,
        "night_start_hour": cfg.night_mode_start_hour,
        "morning_hour": cfg.night_mode_morning_hour,
        "seconds_until_night": round(_seconds_until(cfg.night_mode_start_hour)),
        "seconds_until_morning": round(_seconds_until(cfg.night_mode_morning_hour)),
    }
