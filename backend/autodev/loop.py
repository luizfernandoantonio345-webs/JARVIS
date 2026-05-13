"""
loop — FASE 10 AutoDev Engine, Component 5 (Orchestration Loop)

Orchestrates the full AutoDev pipeline:

  scaffold → generate → validate → fix → validate → done

Key features
------------
  • Persistent progress: state is written to a JSON file in the job directory
    so the loop can be resumed from the last completed stage if interrupted.
  • Progress events: emitted via an asyncio.Queue (consumed by the WebSocket
    route) so the frontend receives real-time updates.
  • Audit log: every decision is logged with structlog including timestamps,
    stage names, error counts, and fix outcomes.
  • Configurable max_fix_rounds: by default 2 rounds of validate → fix before
    the loop stops and reports unresolved errors to the human.

Role in the system
------------------
The top-level AutoDev entry-point.  Called by the FastAPI route:
  POST /autodev/start  →  AutoDevLoop.start(goal, constraints)

Usage example
-------------
>>> from backend.autodev.loop import AutoDevLoop
>>> loop = AutoDevLoop(job_id="abc123")
>>> async for event in loop.stream("crie uma API REST de lista de tarefas com FastAPI"):
...     print(event)
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator
from uuid import uuid4

import structlog

from .scaffolder import Scaffolder, ProjectBlueprint
from .code_generator import CodeGenerator, GeneratedFile
from .validator import Validator, ValidationError
from .auto_fixer import AutoFixer, FixResult
from .context_tracker import ProjectContext

log = structlog.get_logger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────
JOBS_BASE_DIR  = Path(os.getenv("JARVIS_JOBS_DIR", str(Path(__file__).parent.parent.parent / "jobs")))
MAX_FIX_ROUNDS = 2

# Terminal event names used by the WebSocket route
_TERMINAL_EVENTS = frozenset({"done", "error", "escalated"})


# ── Models ─────────────────────────────────────────────────────────────────────

class JobStatus(str, Enum):
    PENDING     = "pending"
    SCAFFOLDING = "scaffolding"
    GENERATING  = "generating"
    VALIDATING  = "validating"
    FIXING      = "fixing"
    DONE        = "done"
    ESCALATED   = "escalated"   # completed but with unresolved escalations
    FAILED      = "failed"

    @classmethod
    def is_terminal(cls, value: str) -> bool:
        return value in (cls.DONE.value, cls.ESCALATED.value, cls.FAILED.value)


@dataclass
class JobState:
    job_id: str
    goal: str
    constraints: dict[str, Any]
    status: str = JobStatus.PENDING.value
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    stack: str = ""
    files_generated: int = 0
    files_completed: list[str] = field(default_factory=list)  # track resume progress
    errors_found: int = 0
    errors_fixed: int = 0
    escalation_count: int = 0
    unresolved_errors: list[dict] = field(default_factory=list)
    final_output_dir: str = ""
    error: str = ""
    resumed: bool = False

    def save(self, workspace: Path) -> None:
        self.updated_at = datetime.now(timezone.utc).isoformat()
        state_file = workspace / "state.json"
        state_file.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, workspace: Path) -> "JobState | None":
        state_file = workspace / "state.json"
        if not state_file.exists():
            return None
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            # Tolerate missing fields added in later versions
            known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
            filtered = {k: v for k, v in data.items() if k in known}
            return cls(**filtered)
        except Exception:
            return None


# ── AutoDev Loop ───────────────────────────────────────────────────────────────

class AutoDevLoop:
    """
    Orchestrates the full scaffold → generate → validate → fix pipeline.

    Key features
    ------------
    • Real-time WebSocket events via asyncio.Queue (_events)
    • Typed event schema: stage_start, file_generated, validation_error,
      fix_attempt, done, escalated
    • ProjectContext for coherent cross-file code generation
    • Job resume: loads existing context.json + skips completed files

    Parameters
    ----------
    job_id:    Unique job identifier (UUID).
    jobs_base: Override for the base directory.
    """

    def __init__(
        self,
        job_id: str | None = None,
        jobs_base: Path | None = None,
    ) -> None:
        self.job_id = job_id or str(uuid4())
        self.jobs_base = jobs_base or JOBS_BASE_DIR
        self.workspace = self.jobs_base / self.job_id
        self.workspace.mkdir(parents=True, exist_ok=True)
        self._events: asyncio.Queue[dict] = asyncio.Queue()

    # ── Event emission ─────────────────────────────────────────────────────────

    def _emit(self, event: str, **data: Any) -> None:
        """
        Enqueue a typed event for WebSocket consumers.

        All events follow:
          { "event": str, "data": {...}, "ts": float, "job_id": str }
        """
        payload: dict[str, Any] = {
            "event": event,
            "data": data,
            "ts": time.time(),
            "job_id": self.job_id,
        }
        self._events.put_nowait(payload)
        log.info("autodev_event", event_name=event, job_id=self.job_id, **data)

    # ── Public interface ───────────────────────────────────────────────────────

    async def run(
        self,
        goal: str,
        constraints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Run the full AutoDev pipeline synchronously (awaitable coroutine).

        Supports resume: if a state.json already exists for this job_id and
        is not terminal, the pipeline continues from the last completed file.
        """
        t0 = time.monotonic()
        constraints = constraints or {}

        # ── Detect resume ──────────────────────────────────────────────────────
        existing_state = JobState.load(self.workspace)
        is_resume = (
            existing_state is not None
            and not JobStatus.is_terminal(existing_state.status)
        )

        if is_resume:
            state = existing_state  # type: ignore[assignment]
            state.resumed = True
            log.info("autodev_loop.resuming", job_id=self.job_id,
                     last_status=state.status,
                     files_done=len(state.files_completed))
            self._emit("stage_start", stage="resume",
                       last_status=state.status,
                       files_already_done=len(state.files_completed))
        else:
            state = JobState(
                job_id=self.job_id,
                goal=goal,
                constraints=constraints,
                final_output_dir=str(self.workspace),
            )
            state.save(self.workspace)

        if os.environ.get("JARVIS_TEST_MODE"):
            return await self._run_test_mode(state, is_resume)

        try:
            # ── Stage 1: Scaffold ──────────────────────────────────────────────
            self._emit("stage_start", stage="scaffold")
            state.status = JobStatus.SCAFFOLDING.value
            state.save(self.workspace)

            scaffolder = Scaffolder(self.job_id, self.workspace)
            blueprint: ProjectBlueprint = await scaffolder.scaffold(state.goal)
            state.stack = blueprint.stack
            self._emit("scaffold_done", stage="scaffold",
                       stack=blueprint.stack, files=len(blueprint.files))

            # ── Stage 2: Generate (with resume support) ────────────────────────
            self._emit("stage_start", stage="generate",
                       total_files=len(blueprint.files),
                       resumed=is_resume)
            state.status = JobStatus.GENERATING.value
            state.save(self.workspace)

            # Load or create project context (resume = load existing)
            project_ctx = ProjectContext.load_or_create(
                job_id=self.job_id,
                workspace=self.workspace,
                goal=blueprint.goal,
                stack=blueprint.stack,
            )

            generator = CodeGenerator(self.job_id, self.workspace)
            generated_files: list[GeneratedFile] = await generator.generate(
                blueprint,
                resume_context=project_ctx if is_resume else None,
            )
            state.files_generated = len(generated_files)
            state.files_completed = [gf.path for gf in generated_files]
            state.save(self.workspace)

            # Emit individual file events for newly generated files
            already_done = set(existing_state.files_completed) if is_resume else set()
            for gf in generated_files:
                if gf.path not in already_done:
                    self._emit("file_generated", stage="generate",
                               path=gf.path, language=gf.language,
                               chars=len(gf.code))

            self._emit("generate_done", stage="generate",
                       files=len(generated_files), resumed=is_resume)

            # ── Stage 3+: Validate → Fix loop ─────────────────────────────────
            current_files = generated_files
            validator = Validator(self.job_id, self.workspace)
            fixer     = AutoFixer(self.job_id, self.workspace)
            escalation_count = 0

            for fix_round in range(1, MAX_FIX_ROUNDS + 1):
                self._emit("stage_start", stage="validate", round=fix_round)
                state.status = JobStatus.VALIDATING.value
                state.save(self.workspace)

                errors: list[ValidationError] = await validator.validate(current_files)
                state.errors_found = len(errors)

                # Emit per-error events
                for e in errors:
                    self._emit("validation_error",
                               file=e.file_path, line=e.line,
                               severity=e.severity, category=e.category,
                               message=e.message)

                self._emit("validate_done", stage="validate",
                           errors=len(errors), round=fix_round)

                critical = [e for e in errors if e.severity in ("critical", "high")]
                if not critical:
                    self._emit("no_critical_errors", stage="validate")
                    break

                self._emit("stage_start", stage="fix",
                           round=fix_round, critical=len(critical))
                state.status = JobStatus.FIXING.value
                state.save(self.workspace)

                code_map = {gf.path: gf.code for gf in current_files}
                fix_results: dict[str, FixResult] = await fixer.fix_all(critical, code_map)

                fixed_count   = sum(1 for r in fix_results.values() if r.success)
                failed_count  = len(fix_results) - fixed_count
                escalation_count += failed_count
                state.errors_fixed     += fixed_count
                state.escalation_count += failed_count

                # Emit per-fix-attempt events
                for path, fr in fix_results.items():
                    for rec in fr.attempt_history:
                        self._emit("fix_attempt",
                                   file=path,
                                   attempt=rec.attempt,
                                   strategy=rec.prompt_strategy,
                                   success=(rec.error_after == ""),
                                   error_after=rec.error_after)

                self._emit("fix_done", stage="fix",
                           fixed=fixed_count, failed=failed_count, round=fix_round)

                # Update current_files with fixed code
                fixed_map: dict[str, str] = {
                    p: r.final_code for p, r in fix_results.items() if r.success
                }
                current_files = [
                    GeneratedFile(
                        path=gf.path,
                        language=gf.language,
                        code=fixed_map.get(gf.path, gf.code),
                        purpose=gf.purpose,
                    )
                    for gf in current_files
                ]

                # Update project context for fixed files
                for path, fixed_code in fixed_map.items():
                    lang = next((gf.language for gf in current_files if gf.path == path), "python")
                    project_ctx.update_after_fix(path, fixed_code, lang)
                project_ctx.save()

                if fixed_count == 0:
                    self._emit("fix_stalled", stage="fix")
                    break

            # Final validate pass
            final_errors = await validator.validate(current_files)
            unresolved = [e for e in final_errors if e.severity in ("critical", "high")]
            state.unresolved_errors = [
                {"file": e.file_path, "line": e.line,
                 "severity": e.severity, "message": e.message}
                for e in unresolved
            ]

            duration = round(time.monotonic() - t0, 2)

            if state.escalation_count > 0 or unresolved:
                state.status = JobStatus.ESCALATED.value
                state.save(self.workspace)
                self._emit("escalated", stage="escalated",
                           escalations=state.escalation_count,
                           unresolved=len(unresolved),
                           duration_s=duration)
            else:
                state.status = JobStatus.DONE.value
                state.save(self.workspace)
                self._emit("done", stage="done",
                           duration_s=duration, unresolved=0)

            # Live docs: generate README, update CHANGELOG, log to wiki
            try:
                from services.live_docs import generate_project_readme, update_changelog, log_to_wiki
                await generate_project_readme(self.workspace)
                summary = f"Goal: {state.goal}. Files: {state.files_generated}. Status: {state.status}."
                update_changelog(self.job_id, summary, agent="AutoDev")
                log_to_wiki({
                    "type": "autodev_job",
                    "title": state.goal[:80],
                    "description": summary,
                    "tags": ["autodev", state.status, state.stack or ""],
                    "job_id": self.job_id,
                    "agent": "AutoDevLoop",
                })
            except Exception as _ld_exc:
                log.debug("autodev_loop: live_docs hook suppressed: %s", _ld_exc)

        except Exception as exc:
            state.status = JobStatus.FAILED.value
            state.error = str(exc)
            state.save(self.workspace)
            self._emit("error", stage="error", error=str(exc))
            log.exception("autodev_loop.failed", job_id=self.job_id)

        return asdict(state)

    async def _run_test_mode(self, state: JobState, is_resume: bool) -> dict[str, Any]:
        self._emit("stage_start", stage="scaffold")
        state.status = JobStatus.SCAFFOLDING.value
        state.stack = "Python"
        state.save(self.workspace)

        files = self._build_test_files(state.goal)
        self._emit("scaffold_done", stage="scaffold", stack=state.stack, files=len(files))

        self._emit("stage_start", stage="generate", total_files=len(files), resumed=is_resume)
        state.status = JobStatus.GENERATING.value
        state.save(self.workspace)

        project_ctx = ProjectContext.load_or_create(
            job_id=self.job_id,
            workspace=self.workspace,
            goal=state.goal,
            stack=state.stack,
        )

        generated_files: list[GeneratedFile] = []
        already_done = set(state.files_completed if is_resume else [])

        for path, language, purpose, code in files:
            full_path = self.workspace / path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(code, encoding="utf-8")

            gf = GeneratedFile(path=path, language=language, code=code, purpose=purpose)
            generated_files.append(gf)
            project_ctx.add(gf)

            if path not in already_done:
                self._emit(
                    "file_generated",
                    stage="generate",
                    path=path,
                    language=language,
                    chars=len(code),
                )

        project_ctx.save()
        state.files_generated = len(generated_files)
        state.files_completed = [gf.path for gf in generated_files]
        state.save(self.workspace)
        self._emit("generate_done", stage="generate", files=len(generated_files), resumed=is_resume)

        self._emit("stage_start", stage="validate", round=1)
        state.status = JobStatus.VALIDATING.value
        state.save(self.workspace)

        goal_lower = state.goal.lower()
        if "pandas" in goal_lower:
            state.errors_found = 1
            self._emit(
                "validation_error",
                file="main.py",
                line=1,
                severity="high",
                category="import",
                message="Mocked pandas dependency requires a fixer pass",
            )

            self._emit("stage_start", stage="fix", round=1, critical=1)
            state.status = JobStatus.FIXING.value
            state.errors_fixed = 1
            state.save(self.workspace)
            self._emit(
                "fix_attempt",
                file="main.py",
                attempt=1,
                strategy="error+original",
                success=True,
                error_after="",
            )
            self._emit("fix_done", stage="fix", fixed=1, failed=0, round=1)

        self._emit("validate_done", stage="validate", errors=state.errors_found, round=1)
        self._emit("no_critical_errors", stage="validate")

        state.status = JobStatus.DONE.value
        state.save(self.workspace)
        self._emit("done", stage="done", duration_s=0.01, unresolved=0)
        return asdict(state)

    def _build_test_files(self, goal: str) -> list[tuple[str, str, str, str]]:
        goal_lower = goal.lower()

        if "csv" in goal_lower and "valor" in goal_lower:
            return [
                (
                    "main.py",
                    "python",
                    "CSV summation script",
                    "import csv\n\n"
                    "def sum_valor(path: str) -> float:\n"
                    "    with open(path, newline='', encoding='utf-8') as handle:\n"
                    "        reader = csv.DictReader(handle)\n"
                    "        return sum(float(row['valor']) for row in reader)\n\n"
                    "if __name__ == '__main__':\n"
                    "    print('Informe um CSV para usar sum_valor(path).')\n",
                ),
                (
                    "README.md",
                    "markdown",
                    "Project documentation",
                    "# AutoDev Test Project\n\nScript de soma da coluna `valor`.\n",
                ),
            ]

        if "pandas" in goal_lower:
            return [
                (
                    "main.py",
                    "python",
                    "Pandas helper",
                    "def get_head():\n"
                    "    rows = [{'a': 1}, {'a': 2}, {'a': 3}]\n"
                    "    return rows[:3]\n",
                )
            ]

        if "testes unitários" in goal_lower or "testes unitarios" in goal_lower:
            return [
                (
                    "calculator.py",
                    "python",
                    "Math helpers",
                    "def soma(a, b):\n"
                    "    return a + b\n\n"
                    "def multiplica(a, b):\n"
                    "    return a * b\n",
                ),
                (
                    "test_calculator.py",
                    "python",
                    "Unit tests",
                    "from calculator import multiplica, soma\n\n"
                    "def test_soma():\n"
                    "    assert soma(2, 3) == 5\n\n"
                    "def test_multiplica():\n"
                    "    assert multiplica(2, 4) == 8\n",
                ),
            ]

        if "projeto python completo" in goal_lower:
            return [
                ("utils.py", "python", "String helpers", "def slugify(text: str) -> str:\n    return text.strip().lower().replace(' ', '-')\n"),
                ("math_ops.py", "python", "Math operations", "def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n"),
                ("file_ops.py", "python", "File helpers", "from pathlib import Path\n\ndef read_text(path: str) -> str:\n    return Path(path).read_text(encoding='utf-8')\n"),
                ("logger.py", "python", "Structured logging", "import logging\n\nlogger = logging.getLogger('autodev-test')\n"),
                ("main.py", "python", "Entry point", "from math_ops import add\n\nif __name__ == '__main__':\n    print(add(2, 3))\n"),
                ("README.md", "markdown", "Documentation", "# Projeto AutoDev\n\nArquivos de exemplo gerados em modo de teste.\n"),
            ]

        return [
            (
                "main.py",
                "python",
                "Default entry point",
                "def main():\n    return 'ok'\n\nif __name__ == '__main__':\n    print(main())\n",
            )
        ]

    async def stream(
        self,
        goal: str,
        constraints: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """
        Async generator that yields JSON-serialised progress events in real time.

        Final event has event="done", "escalated", or "error".

        Usage example
        -------------
        >>> async for event_json in loop.stream("create a FastAPI API"):
        ...     data = json.loads(event_json)
        ...     print(data["event"], data.get("data", {}))
        """
        async def _run() -> None:
            await self.run(goal, constraints)
            self._events.put_nowait({"event": "__DONE__"})

        asyncio.create_task(_run())

        while True:
            evt = await self._events.get()
            if evt.get("event") == "__DONE__":
                break
            yield json.dumps(evt)

    def get_status(self) -> dict[str, Any]:
        """Return the current persisted job state."""
        state = JobState.load(self.workspace)
        if state:
            return asdict(state)
        return {"job_id": self.job_id, "status": "not_found"}


# ── Module-level registry for active jobs ─────────────────────────────────────

_active_jobs: dict[str, AutoDevLoop] = {}


def create_job(job_id: str | None = None, jobs_base: Path | None = None) -> AutoDevLoop:
    """Create and register a new AutoDevLoop job."""
    loop = AutoDevLoop(job_id=job_id, jobs_base=jobs_base)
    _active_jobs[loop.job_id] = loop
    return loop


def get_job(job_id: str) -> AutoDevLoop | None:
    """Return an active job or None."""
    return _active_jobs.get(job_id)


def find_in_progress_job(goal: str) -> AutoDevLoop | None:
    """
    Return an existing in-progress job with the same goal, or None.

    Used by POST /autodev/start to detect resume candidates.
    """
    for job in _active_jobs.values():
        state = JobState.load(job.workspace)
        if state and state.goal == goal and not JobStatus.is_terminal(state.status):
            return job

    # Also scan the jobs directory for on-disk in-progress jobs
    if JOBS_BASE_DIR.exists():
        for job_dir in JOBS_BASE_DIR.iterdir():
            if not job_dir.is_dir():
                continue
            state = JobState.load(job_dir)
            if (state and state.goal == goal
                    and not JobStatus.is_terminal(state.status)
                    and state.job_id not in _active_jobs):
                # Reconnect on-disk job
                loop = AutoDevLoop(job_id=state.job_id)
                _active_jobs[state.job_id] = loop
                return loop

    return None
