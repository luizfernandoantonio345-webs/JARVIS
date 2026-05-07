"""
daily_briefing — FASE 12B

Generates a spoken daily briefing summarising:
  - Today's goal (from daily_goal.json if exists)
  - Pending / completed jobs
  - Recent errors from autonomy log
  - Suggested focus

Triggered at 09:00 by ScheduleWatcher or by voice: "Jarvis, bom dia"
"""

from __future__ import annotations

import json
import logging
import asyncio
import os
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path

from config import get_config

log = logging.getLogger(__name__)

DAILY_GOAL_FILE = Path(__file__).parent / "daily_goal.json"
_briefing_task: asyncio.Task | None = None


class DailyBriefing:
    """Composes and delivers the morning daily briefing."""

    def compose(self) -> str:
        """Build briefing text (30-60s read aloud)."""
        today = date.today().isoformat()
        sections: list[str] = ["Bom dia."]

        # Daily goal
        goal_info = self._load_daily_goal()
        if goal_info:
            sections.append(f"O objetivo de hoje é: {goal_info.get('goal', 'não definido')}.")
        else:
            sections.append("Nenhum objetivo definido para hoje ainda.")

        # AutoDev jobs
        pending, done_yesterday = self._job_summary(today)
        if done_yesterday:
            sections.append(f"Ontem concluí {done_yesterday} tarefa(s).")
        if pending:
            sections.append(f"Você tem {pending} job(s) pendente(s).")

        # Recent errors
        errors = self._recent_errors(hours=24)
        if errors:
            sections.append(
                f"Detectei {len(errors)} erro(s) nas últimas 24 horas que ainda precisam de atenção."
            )

        # Night work summary (if available)
        night_section = self._night_work_section()
        if night_section:
            sections.append(night_section)

        # Suggestion
        if not goal_info:
            sections.append("Qual é o foco de hoje?")
        else:
            sections.append("Posso começar com a primeira tarefa do workplan quando quiser.")

        return " ".join(sections)

    def set_daily_goal(self, goal: str) -> dict:
        """Save today's goal and trigger workplan decomposition."""
        today = date.today().isoformat()
        data = {"date": today, "goal": goal, "set_at": datetime.utcnow().isoformat()}
        DAILY_GOAL_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log.info("DailyBriefing: goal set for %s: '%s'", today, goal[:80])
        return data

    def get_daily_goal(self) -> dict | None:
        return self._load_daily_goal()

    async def deliver(self) -> str:
        """Compose briefing and broadcast for TTS playback."""
        text = self.compose()
        try:
            from services.message_bus import MessageBus
            await MessageBus.get_instance().broadcast({
                "event": "voice_notification",
                "text": text,
            })
        except Exception as exc:
            log.debug("[autonomy.daily_briefing] suppressed exception", exc_info=exc)
            pass
        return text

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _load_daily_goal(self) -> dict | None:
        today = date.today().isoformat()
        if DAILY_GOAL_FILE.exists():
            try:
                data = json.loads(DAILY_GOAL_FILE.read_text(encoding="utf-8"))
                if data.get("date") == today:
                    return data
            except Exception as exc:
                log.debug("[autonomy.daily_briefing] suppressed exception", exc_info=exc)
                pass
        return None

    def _job_summary(self, today: str) -> tuple[int, int]:
        """Return (pending_count, done_yesterday_count)."""
        try:
            import os
            from pathlib import Path
            jobs_base = Path(os.getenv("JARVIS_JOBS_DIR", "D:/JAVIS/jobs"))
            if not jobs_base.exists():
                return 0, 0

            yesterday = (date.today() - timedelta(days=1)).isoformat()
            pending = 0
            done_yest = 0
            for job_dir in jobs_base.iterdir():
                state_file = job_dir / "state.json"
                if not state_file.exists():
                    continue
                try:
                    state = json.loads(state_file.read_text())
                    status = state.get("status", "")
                    updated = (state.get("updated_at") or "")[:10]
                    if status not in {"done", "escalated", "error"}:
                        pending += 1
                    elif updated == yesterday and status == "done":
                        done_yest += 1
                except Exception as exc:
                    log.debug("[autonomy.daily_briefing] suppressed exception", exc_info=exc)
                    pass
            return pending, done_yest
        except Exception:
            return 0, 0

    def _night_work_section(self) -> str:
        """Return a one-line summary of overnight autonomous work, or empty string."""
        try:
            from autonomy.night_mode import get_night_mode_controller
            ctrl = get_night_mode_controller()
            summary = ctrl._load_last_summary()
            if summary is None:
                return ""
            jobs_p = summary.get("jobs_processed", 0)
            t_pass = summary.get("test_passed", 0)
            t_fail = summary.get("test_failed", 0)
            if jobs_p == 0 and t_pass == 0:
                return ""
            parts = []
            if jobs_p:
                parts.append(f"{jobs_p} job(s) processados durante a noite")
            if t_pass or t_fail:
                test_status = "passaram" if t_fail == 0 else f"{t_pass} passaram, {t_fail} falharam"
                parts.append(f"testes: {test_status}")
            return "Durante a noite, " + ", ".join(parts) + "."
        except Exception:
            return ""

    def _recent_errors(self, hours: int = 24) -> list[str]:
        try:
            import sqlite3, time
            from pathlib import Path
            db = get_config().memory_db_path
            if not db.exists():
                return []
            cutoff = time.time() - hours * 3600
            with sqlite3.connect(str(db)) as conn:
                rows = conn.execute(
                    "SELECT goal FROM autonomy_log WHERE ts > ? AND status = 'error' "
                    "ORDER BY ts DESC LIMIT 5",
                    (cutoff,),
                ).fetchall()
            return [r[0] for r in rows]
        except Exception:
            return []


async def generate_briefing() -> str:
    pendencias = await get_pending_tasks()
    ultimo_commit = await git_last_commit_info()
    erros_log = await check_recent_errors(hours=8)
    clima = await get_weather_local()
    return format_briefing(pendencias, ultimo_commit, erros_log, clima)


async def get_pending_tasks() -> list[str]:
    def _load() -> list[str]:
        items: list[str] = []
        todo = Path(__file__).resolve().parents[2] / "TODO.md"
        if todo.exists():
            for line in todo.read_text(encoding="utf-8", errors="replace").splitlines():
                stripped = line.strip()
                if stripped.startswith(("- [x]", "- [X]", "* [x]", "* [X]")):
                    continue
                if stripped.startswith(("- [ ]", "* [ ]")):
                    items.append(stripped[5:].strip())
                elif stripped.startswith(("-", "*")) and len(items) < 5:
                    items.append(stripped[1:].strip())
        return [item for item in items if item][:5]

    return await asyncio.to_thread(_load)


async def git_last_commit_info() -> str:
    def _run() -> str:
        try:
            root = Path(__file__).resolve().parents[2]
            proc = subprocess.run(
                ["git", "log", "-1", "--pretty=%cr: %s"],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return proc.stdout.strip()
        except Exception:
            pass
        return "sem commit detectado"

    return await asyncio.to_thread(_run)


async def check_recent_errors(hours: int = 8) -> list[str]:
    return await asyncio.to_thread(DailyBriefing()._recent_errors, hours)


async def get_weather_local() -> str | None:
    api_url = os.getenv("JARVIS_WEATHER_TEXT")
    if api_url:
        return api_url
    return None


def format_briefing(
    pendencias: list[str],
    ultimo_commit: str,
    erros_log: list[str],
    clima: str | None,
) -> str:
    now = datetime.now()
    hour_text = f"{now.hour}h" if now.minute == 0 else f"{now.hour}h{now.minute:02d}"
    if pendencias:
        pending_text = ", ".join(pendencias[:3])
        first = f"Bom dia. Sao {hour_text}. Hoje voce tem {len(pendencias)} pendencias: {pending_text}."
    else:
        first = f"Bom dia. Sao {hour_text}. Nenhuma pendencia registrada no JARVIS."
    errors = "Nada critico nos logs." if not erros_log else f"Detectei {len(erros_log)} erro(s) recentes nos logs."
    weather = f" Temperatura aqui: {clima}." if clima else ""
    return f"{first} Ultimo commit: {ultimo_commit}. {errors}{weather} Pode comecar."


async def deliver_morning_briefing() -> str:
    text = await generate_briefing()
    try:
        from voice_v2.output import speak
        await speak(text)
    except Exception:
        pass
    try:
        from services.message_bus import MessageBus
        await MessageBus.get_instance().broadcast({"event": "morning_briefing", "text": text})
    except Exception:
        pass
    return text


def _load_briefing_time() -> tuple[int, int, bool]:
    profile_path = Path(__file__).resolve().parents[1] / "behavior" / "jarvis_profile.json"
    try:
        data = json.loads(profile_path.read_text(encoding="utf-8"))
        prefs = data.get("preferences", {})
        enabled = bool(prefs.get("daily_briefing", True))
        raw_time = str(prefs.get("daily_briefing_time", "09:00"))
        hour, minute = raw_time.split(":", 1)
        return int(hour), int(minute), enabled
    except Exception:
        return 9, 0, True


async def _daily_briefing_loop() -> None:
    last_date = ""
    while True:
        hour, minute, enabled = _load_briefing_time()
        now = datetime.now()
        if enabled and now.hour == hour and now.minute == minute and last_date != now.date().isoformat():
            last_date = now.date().isoformat()
            await deliver_morning_briefing()
            await asyncio.sleep(65)
        await asyncio.sleep(20)


def start_daily_briefing_scheduler() -> asyncio.Task:
    global _briefing_task
    if _briefing_task is not None and not _briefing_task.done():
        return _briefing_task
    _briefing_task = asyncio.create_task(_daily_briefing_loop(), name="daily_briefing_scheduler")
    return _briefing_task
