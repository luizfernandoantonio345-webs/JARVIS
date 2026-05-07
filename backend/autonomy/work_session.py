"""
work_session — FASE 12B

Manages execution of a daily workplan — picks tasks by priority, sends them
to the MultiAgentOrchestrator, tracks progress, and notifies via voice/WS.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

from autonomy.goal_decomposer import GoalDecomposer
from autonomy.confirmation_gate import ConfirmationGate

log = logging.getLogger(__name__)

REPORTS_DIR = Path(__file__).parent.parent / "reports" / "daily"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

_TASK_INTERVAL = 30  # seconds between tasks


class WorkSession:
    """
    Executes the daily workplan task by task with confirmation gating,
    voice notifications, and progress persistence.
    """

    def __init__(self) -> None:
        self._decomposer = GoalDecomposer()
        self._gate = ConfirmationGate()
        self._running = False
        self._paused = False
        self._current_task: dict | None = None
        self._workplan: dict | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    async def start(self, goal: str | None = None) -> None:
        """Start (or resume) the work session for today."""
        if goal:
            workplan = self._decomposer.decompose(goal)
            self._decomposer.save(workplan)
            self._workplan = workplan
        else:
            self._workplan = self._decomposer.load_today()
            if not self._workplan:
                log.warning("WorkSession: no workplan for today and no goal provided")
                return

        self._running = True
        self._paused = False
        log.info("WorkSession: starting — %d tasks", len(self._workplan.get("tasks", [])))
        await self._notify_voice(
            f"Iniciando sessão de trabalho. {len(self._workplan['tasks'])} tarefas programadas."
        )
        await self._run_loop()

    async def pause(self) -> None:
        self._paused = True
        log.info("WorkSession: paused")
        await self._notify_voice("Sessão de trabalho pausada. Retome quando quiser.")

    async def resume(self) -> None:
        if self._paused:
            self._paused = False
            log.info("WorkSession: resumed")

    async def stop(self) -> None:
        self._running = False
        log.info("WorkSession: stopped")

    def skip_current_task(self) -> None:
        if self._current_task:
            self._current_task["status"] = "skipped"
            log.info("WorkSession: skipped task %d", self._current_task.get("id"))

    def status(self) -> dict:
        if not self._workplan:
            return {"status": "no_workplan"}
        tasks = self._workplan.get("tasks", [])
        done = [t for t in tasks if t.get("status") == "done"]
        pending = [t for t in tasks if t.get("status") == "pending"]
        return {
            "running": self._running,
            "paused": self._paused,
            "goal": self._workplan.get("goal", ""),
            "total_tasks": len(tasks),
            "done": len(done),
            "pending": len(pending),
            "current_task": self._current_task,
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _run_loop(self) -> None:
        while self._running:
            if self._paused:
                await asyncio.sleep(5)
                continue

            task = self._next_task()
            if not task:
                log.info("WorkSession: all tasks done — generating EOD report")
                await self._generate_eod_report()
                await self._notify_voice("Todas as tarefas do dia foram concluídas. Gerando relatório.")
                self._running = False
                break

            self._current_task = task
            await self._execute_task(task)
            await asyncio.sleep(_TASK_INTERVAL)

    def _next_task(self) -> dict | None:
        priority_order = {"high": 0, "medium": 1, "low": 2}
        tasks = self._workplan.get("tasks", [])
        pending = [t for t in tasks if t.get("status") == "pending"]
        if not pending:
            return None
        return sorted(pending, key=lambda t: priority_order.get(t.get("priority", "low"), 3))[0]

    async def _execute_task(self, task: dict) -> None:
        goal = task.get("description", "")
        task_id = task.get("id", 0)
        log.info("WorkSession: executing task %d: '%s'", task_id, goal[:60])

        # Confirmation gate
        confirm_result = await self._gate.request(goal)
        if confirm_result in {"rejected", "timeout"}:
            self._decomposer.update_task_status(self._workplan, task_id, "skipped",
                                                notes=f"confirmation_{confirm_result}")
            self._decomposer.save(self._workplan)
            await self._notify_voice(f"Tarefa {task_id} cancelada por falta de confirmação.")
            return

        # Execute via orchestrator
        try:
            from agents.multi_agent_orchestrator import MultiAgentOrchestrator
            orch = MultiAgentOrchestrator(session_id=f"work_{task_id}")
            result = await orch.run(goal)
            status = "done" if result.status == "success" else "failed"
            notes = (result.output or "")[:500]
        except Exception as exc:
            status = "failed"
            notes = str(exc)[:300]
            log.error("WorkSession: task %d failed: %s", task_id, exc)

        self._decomposer.update_task_status(self._workplan, task_id, status, notes=notes)
        self._decomposer.save(self._workplan)

        msg = f"Tarefa {task_id} {'concluída com sucesso' if status == 'done' else 'falhou'}."
        await self._notify_voice(msg)
        log.info("WorkSession: task %d → %s", task_id, status)

    async def _notify_voice(self, text: str) -> None:
        try:
            from services.message_bus import MessageBus
            await MessageBus.get_instance().broadcast({
                "event": "voice_notification",
                "text": text,
            })
        except Exception as exc:
            log.debug("[autonomy.work_session] suppressed exception", exc_info=exc)
            pass

    async def _generate_eod_report(self) -> Path:
        wp = self._workplan or {}
        tasks = wp.get("tasks", [])
        done_tasks    = [t for t in tasks if t.get("status") == "done"]
        failed_tasks  = [t for t in tasks if t.get("status") == "failed"]
        skipped_tasks = [t for t in tasks if t.get("status") == "skipped"]
        pending_tasks = [t for t in tasks if t.get("status") == "pending"]

        def _task_line(t: dict) -> str:
            hrs = t.get("estimated_hours", "?")
            return f"- [{t.get('id')}] {t.get('description', '')} (~{hrs}h)"

        today = date.today().isoformat()
        done_lines    = [_task_line(t) for t in done_tasks]    or ["- Nenhuma tarefa concluida"]
        pending_lines = [_task_line(t) for t in (pending_tasks + skipped_tasks)] or ["- Nenhuma"]
        failed_lines  = [f"- [{t.get('id')}] {t.get('notes', '-')}" for t in failed_tasks] or ["- Nenhum"]
        amanha_line   = (
            "- Continuar com: " + ", ".join(t.get("description", "")[:50] for t in pending_tasks[:3])
            if pending_tasks else "- Todas as tarefas foram concluidas. Defina novo objetivo."
        )
        lines = (
            [f"# Relatorio - {today}", "", "## Objetivo do dia", wp.get("goal", "-"), ""]
            + ["## Concluido"] + done_lines + [""]
            + ["## Pendente"] + pending_lines + [""]
            + ["## Problemas encontrados"] + failed_lines + [""]
            + ["## Aprendizados", "- (Ver evolution report semanal para padroes identificados)", ""]
            + ["## Amanha", amanha_line]
        )

        report_path = REPORTS_DIR / f"{today}.md"
        report_path.write_text("\n".join(lines), encoding="utf-8")
        log.info("WorkSession: EOD report saved to %s", report_path)
        return report_path


# ── Module-level singleton ────────────────────────────────────────────────────

_session: WorkSession | None = None


def get_work_session() -> WorkSession:
    global _session
    if _session is None:
        _session = WorkSession()
    return _session
