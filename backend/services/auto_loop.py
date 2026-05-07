"""
AutoLoop — controlled autonomous execution loop for JARVIS.

Implements the core autonomous cycle:
  for iteration in range(MAX_ITERATIONS):
    plan → execute → validate → improve

Safety guarantees:
  - Hard cap: MAX_ITERATIONS = 5
  - Stops on: success, repeated failure, security block
  - No recursive loops
  - Each iteration fully logged
  - SecurityGuard intercepts every action

Usage:
    from services.auto_loop import get_loop
    loop = get_loop()
    result = loop.run("create a FastAPI API", session_id="abc")
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum

log = logging.getLogger(__name__)

MAX_ITERATIONS = 5
MAX_STEPS      = 5


# ── State ──────────────────────────────────────────────────────────────────────

class AutoLoopState(str, Enum):
    RUNNING  = "running"
    SUCCESS  = "success"
    FAILED   = "failed"
    BLOCKED  = "blocked"
    ABORTED  = "aborted"   # repeated failure or max iterations


# ── Result types ───────────────────────────────────────────────────────────────

@dataclass
class IterationResult:
    iteration: int
    plan_summary: str
    steps_run: list[dict]
    output: str
    success: bool
    errors: list[str]
    duration_s: float

    def to_dict(self) -> dict:
        return {
            "iteration":    self.iteration,
            "plan_summary": self.plan_summary,
            "steps_run":    self.steps_run,
            "output":       self.output[:500],
            "success":      self.success,
            "errors":       self.errors,
            "duration_s":   round(self.duration_s, 2),
        }


@dataclass
class AutoLoopResult:
    objective: str
    state: AutoLoopState
    iterations: list[IterationResult] = field(default_factory=list)
    final_output: str = ""
    error: str | None = None

    def to_text(self) -> str:
        icon = {"success": "✅", "failed": "❌", "blocked": "🚫", "aborted": "⚠️", "running": "🔄"}.get(
            self.state.value, "❓"
        )
        lines = [
            f"## AutoLoop Result {icon}",
            f"**Objective**: {self.objective}",
            f"**State**: {self.state.value.upper()}",
            f"**Iterations**: {len(self.iterations)}/{MAX_ITERATIONS}",
            "",
        ]
        for it in self.iterations:
            status = "✅" if it.success else "❌"
            lines.append(f"### Iteration {it.iteration} {status} ({it.duration_s:.1f}s)")
            lines.append(f"Plan: {it.plan_summary[:120]}")
            if it.errors:
                lines.append(f"Errors: {', '.join(it.errors)}")
            lines.append("")
        if self.final_output:
            lines += ["---", "## Final Output", self.final_output[:2000]]
        if self.error:
            lines.append(f"\n**Error**: {self.error}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "objective":    self.objective,
            "state":        self.state.value,
            "iterations":   [it.to_dict() for it in self.iterations],
            "final_output": self.final_output,
            "error":        self.error,
        }


# ── AutoLoop ───────────────────────────────────────────────────────────────────

class AutoLoop:
    """
    Controlled autonomous loop that executes a task through plan→execute→validate→improve.

    Integrates:
    - Orchestrator for dispatching
    - SecurityGuard for all action validation
    - AgentManager for multi-step tasks
    - DebuggerAgent for self-correction
    """

    def run(
        self,
        objective: str,
        session_id: str = "default",
        history: list[dict] | None = None,
        mode: str = "auto_dev",
    ) -> AutoLoopResult:
        """
        Run the autonomous loop for the given objective.

        Args:
            objective:  High-level goal.
            session_id: Session for memory.
            history:    Prior conversation context.
            mode:       Execution mode hint ("auto_dev", "automation", "dev").

        Returns:
            LoopResult — always populated, never raises.
        """
        log.info("AutoLoop.run: objective=%r mode=%s session=%s", objective[:80], mode, session_id)

        result = AutoLoopResult(objective=objective, state=AutoLoopState.RUNNING)
        context = ""
        last_error_sig = ""

        for iteration in range(1, MAX_ITERATIONS + 1):
            t_start = time.monotonic()
            log.info("AutoLoop: iteration %d/%d", iteration, MAX_ITERATIONS)

            # ── Execute iteration ──────────────────────────────────────────
            iter_result, state_override = self._run_iteration(
                iteration=iteration,
                objective=objective,
                context=context,
                session_id=session_id,
                history=history,
                mode=mode,
            )

            iter_result.duration_s = time.monotonic() - t_start
            result.iterations.append(iter_result)

            # ── Check for security block ───────────────────────────────────
            if state_override == AutoLoopState.BLOCKED:
                result.state = AutoLoopState.BLOCKED
                result.error = f"Blocked at iteration {iteration}"
                result.final_output = iter_result.output
                log.warning("AutoLoop: blocked at iteration %d", iteration)
                return result

            # ── Check for success ──────────────────────────────────────────
            if iter_result.success and not iter_result.errors:
                result.state = AutoLoopState.SUCCESS
                result.final_output = iter_result.output
                log.info("AutoLoop: success at iteration %d", iteration)
                return result

            # ── Detect repeated failure ────────────────────────────────────
            error_sig = ",".join(sorted(iter_result.errors))
            if error_sig and error_sig == last_error_sig:
                result.state = AutoLoopState.ABORTED
                result.error = f"Repeated failure: {error_sig}. Aborting."
                result.final_output = iter_result.output
                log.warning("AutoLoop: repeated failure, aborting")
                return result
            last_error_sig = error_sig

            # Update context for next iteration
            context = iter_result.output[:2000]

        # Max iterations reached
        result.state = AutoLoopState.ABORTED
        result.error = f"Max iterations ({MAX_ITERATIONS}) reached."
        if result.iterations:
            result.final_output = result.iterations[-1].output
        return result

    # ── Private ────────────────────────────────────────────────────────────────

    def _run_iteration(
        self,
        iteration: int,
        objective: str,
        context: str,
        session_id: str,
        history: list[dict] | None,
        mode: str,
    ) -> tuple[IterationResult, AutoLoopState | None]:
        """
        Execute one iteration: plan → execute → collect result.

        Returns (IterationResult, optional state override for blocking).
        """
        from services.orchestrator import get_orchestrator

        orch = get_orchestrator()

        # Enrich message with context on iterations > 1
        message = objective
        if context and iteration > 1:
            message = f"[Iteration {iteration}] Fix/improve based on previous result.\n\nPrevious output:\n{context[:1000]}\n\nObjective: {objective}"

        orch_result = orch.dispatch(
            message=message,
            session_id=session_id,
            mode=mode,
            history=history,
        )

        if orch_result.blocked:
            return (
                IterationResult(
                    iteration=iteration,
                    plan_summary="BLOCKED",
                    steps_run=[],
                    output=orch_result.output,
                    success=False,
                    errors=["security_block"],
                    duration_s=0.0,
                ),
                AutoLoopState.BLOCKED,
            )

        # Detect errors in output
        errors = self._detect_errors(orch_result.output)

        plan_summary = ""
        if orch_result.steps:
            plan_summary = " → ".join(
                s.get("agent", s.get("action", "?")) for s in orch_result.steps[:5]
            )
        else:
            plan_summary = orch_result.mode

        return (
            IterationResult(
                iteration=iteration,
                plan_summary=plan_summary,
                steps_run=orch_result.steps or [],
                output=orch_result.output,
                success=orch_result.success and not errors,
                errors=errors,
                duration_s=0.0,
            ),
            None,
        )

    @staticmethod
    def _detect_errors(output: str) -> list[str]:
        """Return list of error type strings found in output."""
        import re
        errors: list[str] = []
        patterns = [
            (re.compile(r"SyntaxError|IndentationError", re.IGNORECASE), "syntax_error"),
            (re.compile(r"ModuleNotFoundError|ImportError", re.IGNORECASE), "import_error"),
            (re.compile(r"Traceback \(most recent call last\)|RuntimeError", re.IGNORECASE), "runtime_error"),
            (re.compile(r"❌\s*(Error|Failed|Erro)", re.IGNORECASE), "execution_error"),
        ]
        for pat, label in patterns:
            if pat.search(output):
                errors.append(label)
        return list(set(errors))


# ── Singleton ──────────────────────────────────────────────────────────────────

_loop: AutoLoop | None = None


def get_loop() -> AutoLoop:
    """Return the global AutoLoop singleton."""
    global _loop
    if _loop is None:
        _loop = AutoLoop()
    return _loop
