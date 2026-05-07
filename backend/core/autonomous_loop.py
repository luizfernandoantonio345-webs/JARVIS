"""
autonomous_loop — FASE 8, Etapa 3

True **observe–plan–execute–re-plan** cycle for JARVIS.

This module implements a higher-fidelity autonomous loop than the existing
``services/auto_loop.py``.  Key differences:

  1. **Real observation**: each execution step produces a ``ShellObservation``
     (stdout + stderr + exit-code + timestamp) that is injected verbatim into
     the next LLM plan call.
  2. **Re-planning on failure**: if an execution step fails, the loop calls the
     LLM planner again with the failure context before retrying.
  3. **Session-persistent state**: loop state is written to the SessionStore so
     it survives process restart (within the same session).
  4. **VS Code awareness**: after file-generation steps the loop optionally
     reads IDE diagnostics via the VS Code bridge and folds them into the
     observation context.
  5. **Configurable stop criteria**: task_complete=True (LLM signals done) or
     max_iterations (default 10) or max_consecutive_failures (default 3).

Role in the system
------------------
Intended as the *core engine* for the AutonomousAgent / AutoDev pipeline.
The orchestrator calls ``AutonomousLoop.run(goal)`` and streams progress events
to the frontend via WebSocket.

Usage example
-------------
>>> from backend.core.autonomous_loop import AutonomousLoop
>>> loop = AutonomousLoop(session_id="sess-abc")
>>> result = await loop.run("Create a FastAPI CRUD for a 'books' resource")
>>> print(result.state, result.iterations_run)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, AsyncIterator, Callable

import structlog

from services.llm_service import call_llm
from services.memory_service import save_memory, build_context_for_task
from services.session_store import get_history, append_message
from tools.shell_feedback import run_with_feedback, FeedbackResult
from integrations.vscode_bridge import read_diagnostics, is_available as vscode_available

log: structlog.BoundLogger = structlog.get_logger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
DEFAULT_MAX_ITERATIONS = 10
DEFAULT_MAX_FAILURES   = 3


# ── Enums & Models ─────────────────────────────────────────────────────────────

class LoopState(str, Enum):
    IDLE     = "idle"
    RUNNING  = "running"
    SUCCESS  = "success"
    FAILED   = "failed"
    BLOCKED  = "blocked"
    ABORTED  = "aborted"


@dataclass
class PlanStep:
    """A single step produced by the LLM planner."""
    index: int
    action: str          # "shell" | "write_file" | "read_file" | "search" | "done"
    description: str
    command: str | None = None   # populated for "shell" actions
    file_path: str | None = None
    file_content: str | None = None


@dataclass
class Observation:
    """Structured observation after executing one PlanStep."""
    step_index: int
    action: str
    success: bool
    output: str
    error: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def as_context_text(self) -> str:
        status = "SUCCESS" if self.success else "FAILURE"
        return (
            f"[STEP {self.step_index} OBSERVATION @ {self.timestamp}]\n"
            f"Action : {self.action}\n"
            f"Status : {status}\n"
            f"Output :\n{self.output[:2000]}\n"
            + (f"Error  :\n{self.error[:500]}\n" if self.error else "")
            + "[END OBSERVATION]"
        )


@dataclass
class IterationRecord:
    iteration: int
    goal: str
    plan_json: str
    observations: list[Observation]
    task_complete: bool
    duration_s: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "iteration":     self.iteration,
            "goal":          self.goal,
            "plan_json":     self.plan_json,
            "task_complete": self.task_complete,
            "observations":  [asdict(o) for o in self.observations],
            "duration_s":    round(self.duration_s, 2),
        }


@dataclass
class LoopResult:
    goal: str
    state: LoopState
    iterations_run: int
    iterations: list[IterationRecord] = field(default_factory=list)
    final_output: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal":          self.goal,
            "state":         self.state.value,
            "iterations_run": self.iterations_run,
            "iterations":    [r.to_dict() for r in self.iterations],
            "final_output":  self.final_output,
            "error":         self.error,
        }


# ── Planner prompt templates ───────────────────────────────────────────────────

_PLAN_SYSTEM = """\
You are a precise autonomous AI planner. Given a goal and optional observations
from previous steps, produce a JSON execution plan.

Rules:
- Return ONLY valid JSON — no markdown, no prose.
- "steps" is an ordered list of actions.
- Valid actions: "shell", "write_file", "read_file", "search", "done".
- For "shell": include a "command" field (safe, whitelisted commands only).
- For "write_file": include "file_path" and "file_content".
- For "read_file": include "file_path".
- Set "task_complete": true only when the goal is fully achieved.
- Maximum 6 steps per plan.

Schema:
{
  "task_complete": false,
  "steps": [
    {"action": "shell", "description": "...", "command": "..."},
    {"action": "write_file", "description": "...", "file_path": "...", "file_content": "..."},
    {"action": "done", "description": "Goal achieved."}
  ]
}
"""


def _build_plan_prompt(goal: str, observations: list[Observation], iteration: int) -> str:
    obs_text = "\n\n".join(o.as_context_text() for o in observations) if observations else "None yet."
    return (
        f"Goal: {goal}\n\n"
        f"Iteration: {iteration}\n\n"
        f"Previous observations:\n{obs_text}\n\n"
        "Produce the next execution plan as JSON:"
    )


# ── Executor ───────────────────────────────────────────────────────────────────

async def _execute_step(
    step: PlanStep,
    session_id: str,
    on_event: Callable[[str], None] | None,
) -> Observation:
    """Execute a single plan step and return a structured Observation."""

    def _emit(msg: str) -> None:
        if on_event:
            on_event(msg)
        log.debug("autonomous_loop.step", step=step.index, action=step.action, msg=msg)

    _emit(f"▶ Step {step.index}: [{step.action}] {step.description}")

    if step.action == "shell":
        if not step.command:
            return Observation(step.index, step.action, False, "", error="No command provided.")
        result: FeedbackResult = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: run_with_feedback(
                step.command,  # type: ignore[arg-type]
                session_id=session_id,
                inject_to_memory=True,
            ),
        )
        return Observation(
            step_index=step.index,
            action=step.action,
            success=result.success,
            output=result.stdout,
            error=result.stderr if not result.success else "",
        )

    elif step.action == "write_file":
        if not step.file_path or step.file_content is None:
            return Observation(step.index, step.action, False, "", error="file_path and file_content required.")
        try:
            from pathlib import Path
            path = Path(step.file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(step.file_content, encoding="utf-8")
            # Optionally read VS Code diagnostics after writing
            diag_text = ""
            if vscode_available():
                diag_result = read_diagnostics(step.file_path)
                if diag_result.ok and diag_result.result:
                    diag_text = f"\nIDE diagnostics: {json.dumps(diag_result.result[:5])}"
            return Observation(step.index, step.action, True, f"Written: {step.file_path}{diag_text}")
        except Exception as exc:
            return Observation(step.index, step.action, False, "", error=str(exc))

    elif step.action == "read_file":
        if not step.file_path:
            return Observation(step.index, step.action, False, "", error="file_path required.")
        try:
            from pathlib import Path
            content = Path(step.file_path).read_text(encoding="utf-8")
            return Observation(step.index, step.action, True, content[:3000])
        except Exception as exc:
            return Observation(step.index, step.action, False, "", error=str(exc))

    elif step.action == "done":
        return Observation(step.index, step.action, True, step.description)

    else:
        return Observation(step.index, step.action, False, "", error=f"Unknown action: {step.action}")


# ── Parser ─────────────────────────────────────────────────────────────────────

def _parse_plan(raw_json: str) -> tuple[bool, list[PlanStep]]:
    """Parse LLM JSON plan into (task_complete, steps). Returns empty steps on failure."""
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        # Attempt to extract JSON block from prose
        import re
        match = re.search(r"\{[\s\S]+\}", raw_json)
        if not match:
            return False, []
        try:
            data = json.loads(match.group())
        except json.JSONDecodeError:
            return False, []

    task_complete: bool = bool(data.get("task_complete", False))
    raw_steps: list[dict] = data.get("steps", [])
    steps: list[PlanStep] = []
    for i, s in enumerate(raw_steps):
        steps.append(
            PlanStep(
                index=i,
                action=s.get("action", "done"),
                description=s.get("description", ""),
                command=s.get("command"),
                file_path=s.get("file_path"),
                file_content=s.get("file_content"),
            )
        )
    return task_complete, steps


# ── Main Loop Class ────────────────────────────────────────────────────────────

class AutonomousLoop:
    """
    Orchestrates the plan → execute → observe → re-plan cycle.

    Parameters
    ----------
    session_id:        Identifies the session in memory and session store.
    max_iterations:    Hard stop after this many plan–execute cycles.
    max_failures:      Stop early if this many consecutive steps fail.
    on_event:          Optional callback for real-time progress events (str).

    Usage example
    -------------
    >>> loop = AutonomousLoop(session_id="sess-001", max_iterations=5)
    >>> result = await loop.run("Build a Python CLI tool that lists files")
    >>> print(result.state)
    """

    def __init__(
        self,
        session_id: str = "autonomous",
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        max_failures: int = DEFAULT_MAX_FAILURES,
        on_event: Callable[[str], None] | None = None,
    ) -> None:
        self.session_id = session_id
        self.max_iterations = max_iterations
        self.max_failures = max_failures
        self.on_event = on_event

        self._state = LoopState.IDLE
        self._iteration_records: list[IterationRecord] = []
        self._all_observations: list[Observation] = []

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _emit(self, msg: str) -> None:
        log.info("autonomous_loop", msg=msg)
        if self.on_event:
            self.on_event(msg)

    async def _call_planner(self, goal: str, observations: list[Observation], iteration: int) -> str:
        """Call the LLM planner and return raw JSON."""
        prompt = _build_plan_prompt(goal, observations, iteration)
        mem_context = build_context_for_task(self.session_id, goal, task_type="autonomous")
        full_prompt = (mem_context + "\n\n" + prompt) if mem_context else prompt

        messages = [
            {"role": "system", "content": _PLAN_SYSTEM},
            {"role": "user",   "content": full_prompt},
        ]
        raw = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: call_llm(messages, force_api=False),
        )
        return raw or "{}"

    # ── Public interface ───────────────────────────────────────────────────────

    async def run(self, goal: str) -> LoopResult:
        """
        Run the autonomous plan–execute–observe cycle until done or exhausted.

        Returns a LoopResult with the full history of iterations and observations.
        """
        self._state = LoopState.RUNNING
        self._emit(f"🚀 Starting autonomous loop for goal: {goal}")

        # Persist goal to session store
        append_message(self.session_id, "user", goal)

        consecutive_failures = 0
        t_total = time.monotonic()

        for iteration in range(1, self.max_iterations + 1):
            self._emit(f"\n── Iteration {iteration}/{self.max_iterations} ──")
            t_iter = time.monotonic()

            # 1. PLAN
            self._emit("Planning…")
            raw_plan = await self._call_planner(goal, self._all_observations, iteration)
            task_complete, steps = _parse_plan(raw_plan)

            if not steps:
                self._emit("⚠️  Planner returned empty plan — aborting.")
                self._state = LoopState.ABORTED
                break

            self._emit(f"Plan: {len(steps)} step(s), task_complete={task_complete}")

            # 2. EXECUTE each step and OBSERVE
            iter_observations: list[Observation] = []
            for step in steps:
                obs = await _execute_step(step, self.session_id, self.on_event)
                iter_observations.append(obs)
                self._all_observations.append(obs)
                self._emit(obs.as_context_text())

                if not obs.success:
                    consecutive_failures += 1
                    self._emit(f"❌ Step {step.index} failed (consecutive_failures={consecutive_failures})")
                    if consecutive_failures >= self.max_failures:
                        self._state = LoopState.ABORTED
                        break
                else:
                    consecutive_failures = 0

                if self._state == LoopState.ABORTED:
                    break

            # Record iteration
            record = IterationRecord(
                iteration=iteration,
                goal=goal,
                plan_json=raw_plan,
                observations=iter_observations,
                task_complete=task_complete,
                duration_s=time.monotonic() - t_iter,
            )
            self._iteration_records.append(record)

            # Persist observations to episodic memory
            try:
                obs_summary = "\n".join(o.as_context_text() for o in iter_observations)
                save_memory(
                    session_id=self.session_id,
                    message=f"[iteration {iteration}] {goal}",
                    response=obs_summary,
                    action="autonomous_loop",
                )
            except Exception as exc:
                log.warning("autonomous_loop.memory_save_failed", error=str(exc))

            # 3. RE-PLAN or STOP
            if self._state == LoopState.ABORTED:
                break

            if task_complete:
                self._emit("✅ Task complete!")
                self._state = LoopState.SUCCESS
                break

        else:
            # Exhausted iterations
            self._emit(f"⚠️  Max iterations ({self.max_iterations}) reached.")
            self._state = LoopState.ABORTED

        final_output = self._all_observations[-1].output if self._all_observations else ""
        duration = round(time.monotonic() - t_total, 2)
        self._emit(f"Loop finished in {duration}s with state={self._state.value}")

        return LoopResult(
            goal=goal,
            state=self._state,
            iterations_run=len(self._iteration_records),
            iterations=self._iteration_records,
            final_output=final_output,
        )

    async def stream(self, goal: str) -> AsyncIterator[str]:
        """
        Async generator that yields progress events as plain strings.
        Yields a final ``__RESULT__:<json>`` line when done.

        Usage example
        -------------
        >>> async for event in loop.stream("fix the failing tests"):
        ...     if event.startswith("__RESULT__:"):
        ...         result = json.loads(event[len("__RESULT__:"):])
        ...     else:
        ...         print(event)
        """
        events: asyncio.Queue[str] = asyncio.Queue()

        def _push(msg: str) -> None:
            events.put_nowait(msg)

        original_cb = self.on_event
        self.on_event = _push

        async def _runner() -> None:
            result = await self.run(goal)
            events.put_nowait("__RESULT__:" + json.dumps(result.to_dict()))
            events.put_nowait("__DONE__")

        task = asyncio.create_task(_runner())

        while True:
            event = await events.get()
            if event == "__DONE__":
                break
            yield event

        await task
        self.on_event = original_cb


# ── Module-level singleton ─────────────────────────────────────────────────────

_default_loop: AutonomousLoop | None = None


def get_autonomous_loop(session_id: str = "autonomous") -> AutonomousLoop:
    """Return a session-scoped AutonomousLoop instance."""
    global _default_loop
    if _default_loop is None or _default_loop.session_id != session_id:
        _default_loop = AutonomousLoop(session_id=session_id)
    return _default_loop
