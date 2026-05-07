"""
AutoDev — Autonomous development mode for JARVIS (Phase 6).

Jarvis receives a high-level objective and autonomously:
  1. Plans the project
  2. Creates the folder/file structure
  3. Implements code via CoderAgent
  4. Runs and validates via ExecutorAgent
  5. Debugs errors via DebuggerAgent
  6. Iterates until success or max iterations

Rules:
  - Max 5 iterations (never infinite)
  - Each iteration fully logged
  - Aborts on repeated identical failures
  - No infinite retries

Usage:
    from services.auto_dev import AutoDev
    dev = AutoDev()
    result = dev.build("create a FastAPI hello-world API")
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

MAX_ITERATIONS = 5


# ── Result types ───────────────────────────────────────────────────────────────

@dataclass
class IterationLog:
    iteration: int
    plan_summary: str
    code_generated: bool
    run_output: str
    errors_found: list[str]
    fixed: bool

    def to_dict(self) -> dict:
        return {
            "iteration": self.iteration,
            "plan_summary": self.plan_summary,
            "code_generated": self.code_generated,
            "run_output": self.run_output[:500],
            "errors_found": self.errors_found,
            "fixed": self.fixed,
        }


@dataclass
class AutoDevResult:
    objective: str
    success: bool
    iterations: list[IterationLog] = field(default_factory=list)
    final_output: str = ""
    files_created: list[str] = field(default_factory=list)
    errors_fixed: list[str] = field(default_factory=list)
    error: str | None = None

    def to_text(self) -> str:
        lines = [
            f"## AutoDev Result",
            f"**Objective**: {self.objective}",
            f"**Status**: {'✅ Success' if self.success else '❌ Failed'}",
            f"**Iterations**: {len(self.iterations)}",
            "",
        ]
        if self.files_created:
            lines += ["**Files Created**:"] + [f"  - {f}" for f in self.files_created] + [""]
        if self.errors_fixed:
            lines += ["**Errors Fixed**:"] + [f"  - {e}" for e in self.errors_fixed] + [""]
        for it in self.iterations:
            lines += [
                f"### Iteration {it.iteration}",
                f"Plan: {it.plan_summary}",
                f"Code generated: {'Yes' if it.code_generated else 'No'}",
                f"Errors: {it.errors_found or 'None'}",
                f"Fixed: {'Yes' if it.fixed else 'No'}",
                "",
            ]
        if self.final_output:
            lines += ["---", "## Final Output", self.final_output]
        if self.error:
            lines.append(f"\n**Fatal Error**: {self.error}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "objective": self.objective,
            "success": self.success,
            "iterations": [it.to_dict() for it in self.iterations],
            "final_output": self.final_output,
            "files_created": self.files_created,
            "errors_fixed": self.errors_fixed,
            "error": self.error,
        }


# ── Error detection ────────────────────────────────────────────────────────────

_SYNTAX_PATTERNS = [
    re.compile(r"SyntaxError", re.IGNORECASE),
    re.compile(r"IndentationError", re.IGNORECASE),
    re.compile(r"unexpected token", re.IGNORECASE),
]

_IMPORT_PATTERNS = [
    re.compile(r"ModuleNotFoundError", re.IGNORECASE),
    re.compile(r"ImportError", re.IGNORECASE),
    re.compile(r"No module named", re.IGNORECASE),
]

_RUNTIME_PATTERNS = [
    re.compile(r"RuntimeError", re.IGNORECASE),
    re.compile(r"AttributeError", re.IGNORECASE),
    re.compile(r"TypeError", re.IGNORECASE),
    re.compile(r"ValueError", re.IGNORECASE),
    re.compile(r"KeyError", re.IGNORECASE),
    re.compile(r"Traceback \(most recent call last\)", re.IGNORECASE),
]


def _detect_errors(output: str) -> list[str]:
    """Parse output and return list of error descriptions."""
    errors: list[str] = []
    for pat in _SYNTAX_PATTERNS:
        if pat.search(output):
            errors.append("syntax_error")
    for pat in _IMPORT_PATTERNS:
        if pat.search(output):
            errors.append("import_error")
    for pat in _RUNTIME_PATTERNS:
        if pat.search(output):
            errors.append("runtime_error")
    return list(set(errors))


def _extract_code_blocks(text: str) -> list[str]:
    """Extract all code blocks from markdown text."""
    blocks = re.findall(r"```(?:\w+)?\n(.*?)```", text, re.DOTALL)
    return blocks


# ── AutoDev ────────────────────────────────────────────────────────────────────

class AutoDev:
    """
    Autonomous development loop.

    Orchestrates: plan → code → write → run → debug → iterate
    """

    def __init__(self) -> None:
        self._log = logging.getLogger("services.auto_dev")

    def build(
        self,
        objective: str,
        project_path: str = ".",
        history: list[dict] | None = None,
    ) -> AutoDevResult:
        """
        Autonomously implement the given objective.

        Args:
            objective:    High-level goal (e.g., "create a FastAPI API").
            project_path: Workspace-relative directory to write files into.
            history:      Prior conversation context.

        Returns:
            AutoDevResult — always returned, never raises.
        """
        self._log.info("AutoDev.build: starting for '%s'", objective[:80])

        result = AutoDevResult(objective=objective)
        context = ""          # Accumulated context across iterations
        last_error_sig = ""   # Detect repeated identical failures

        for iteration in range(1, MAX_ITERATIONS + 1):
            self._log.info("AutoDev: iteration %d/%d", iteration, MAX_ITERATIONS)

            iteration_log = IterationLog(
                iteration=iteration,
                plan_summary="",
                code_generated=False,
                run_output="",
                errors_found=[],
                fixed=False,
            )

            # ── 1. Plan / Code ─────────────────────────────────────────────────
            try:
                code_output, plan_summary, files = self._generate_code(
                    objective=objective,
                    context=context,
                    project_path=project_path,
                    iteration=iteration,
                    history=history,
                )
            except Exception as exc:
                self._log.error("AutoDev: code generation error: %s", exc)
                iteration_log.errors_found = ["code_generation_error"]
                result.iterations.append(iteration_log)
                result.error = f"Code generation failed: {exc}"
                break

            iteration_log.plan_summary = plan_summary
            iteration_log.code_generated = bool(files)
            result.files_created.extend(f for f in files if f not in result.files_created)

            # ── 2. Run / Validate ─────────────────────────────────────────────
            run_output = self._run_project(project_path)
            iteration_log.run_output = run_output

            errors = _detect_errors(run_output)
            iteration_log.errors_found = errors

            if not errors:
                # Success!
                iteration_log.fixed = True
                result.iterations.append(iteration_log)
                result.final_output = run_output
                result.success = True
                self._log.info("AutoDev: success on iteration %d", iteration)
                return result

            # ── 3. Detect repeated failure ─────────────────────────────────────
            error_sig = ",".join(sorted(errors))
            if error_sig == last_error_sig:
                self._log.warning("AutoDev: repeated failure, aborting")
                result.iterations.append(iteration_log)
                result.error = f"Repeated failure: {errors}. Aborting."
                result.final_output = run_output
                break
            last_error_sig = error_sig

            # ── 4. Self-correct ────────────────────────────────────────────────
            try:
                fix_summary = self._fix_errors(
                    objective=objective,
                    code=code_output,
                    run_output=run_output,
                    errors=errors,
                    project_path=project_path,
                    history=history,
                )
                result.errors_fixed.extend(
                    e for e in errors if e not in result.errors_fixed
                )
                context = f"Previous code:\n{code_output[:1000]}\nFix applied: {fix_summary}"
                iteration_log.fixed = True
            except Exception as exc:
                self._log.error("AutoDev: fix error: %s", exc)
                context = f"Error on iteration {iteration}: {errors}"

            result.iterations.append(iteration_log)

        # Max iterations reached without success
        if not result.success:
            if not result.error:
                result.error = f"Max iterations ({MAX_ITERATIONS}) reached without success."
            if not result.final_output:
                result.final_output = f"❌ {result.error}"

        return result

    # ── Private helpers ────────────────────────────────────────────────────────

    def _generate_code(
        self,
        objective: str,
        context: str,
        project_path: str,
        iteration: int,
        history: list[dict] | None,
    ) -> tuple[str, str, list[str]]:
        """
        Use DevAgent to generate code, then write files to workspace.

        Returns:
            (code_output, plan_summary, list_of_files_created)
        """
        from services.agent_registry import get_agent
        from services.fs_controller import get_fs

        coder = get_agent("dev")
        prompt = objective
        if context:
            prompt = f"Context from previous attempt:\n{context}\n\nObjective: {objective}"
        if iteration > 1:
            prompt = f"[Iteration {iteration}] Fix and improve: {prompt}"

        agent_result = coder.run(prompt, history)
        code_output = agent_result.response

        # ── Validate generated code before writing ─────────────────────────
        from services.code_validator import validate_response, Severity
        val_report = validate_response(code_output)
        if not val_report.valid:
            crits = val_report.critical_summary()
            self._log.warning("AutoDev: code has CRITICAL issues:\n%s", crits)
            # Request a safer version from the coder
            fix_prompt = (
                f"The code you generated has critical security/syntax issues:\n{crits}\n\n"
                f"Original task: {objective}\n\n"
                "Provide corrected, safe code without those issues."
            )
            agent_result = coder.run(fix_prompt, history)
            code_output = agent_result.response

        # Extract and write code blocks to workspace files
        files_created: list[str] = []
        fs = get_fs()
        wm = None
        try:
            from services.workspace_manager import get_workspace_manager
            wm = get_workspace_manager()
        except Exception as exc:
            log.debug("[services.auto_dev] suppressed exception", exc_info=exc)
            pass

        # Look for file path hints like: `# File: main.py` or ```python main.py
        file_blocks = re.findall(
            r"(?:File:|filename:|#\s*file:)\s*([\w/.\-]+)\s*\n```(?:\w+)?\n(.*?)```",
            code_output,
            re.DOTALL | re.IGNORECASE,
        )

        if file_blocks:
            for fname, code in file_blocks:
                target = f"{project_path}/{fname}".lstrip("./")
                write_result = fs.write_file(target, code.strip())
                if write_result.success:
                    files_created.append(target)
                    self._log.info("AutoDev: wrote %s", target)
        else:
            # Heuristic: write the first Python code block to main.py
            blocks = _extract_code_blocks(code_output)
            if blocks and project_path:
                first_block = blocks[0].strip()
                if first_block:
                    target = f"{project_path}/main.py".lstrip("./")
                    write_result = fs.write_file(target, first_block)
                    if write_result.success:
                        files_created.append(target)

        plan_summary = code_output[:200].replace("\n", " ")
        return code_output, plan_summary, files_created

    def _run_project(self, project_path: str) -> str:
        """Run project and return output text — tries WorkspaceManager first."""
        try:
            from services.workspace_manager import get_workspace_manager
            wm = get_workspace_manager()
            run_result = wm.run_project(project_path, timeout=20.0)
            return run_result.to_text()
        except Exception as exc:
            log.debug("[services.auto_dev] suppressed exception", exc_info=exc)
            pass
        # Fallback to project_runner
        from services.project_runner import get_runner
        runner = get_runner()
        run_result = runner.run_project(project_path)
        return run_result.to_text()

    def _fix_errors(
        self,
        objective: str,
        code: str,
        run_output: str,
        errors: list[str],
        project_path: str,
        history: list[dict] | None,
    ) -> str:
        """
        Send error back to DebuggerAgent for analysis and fix.
        Also runs CodeValidator to surface specific line-level issues.
        Returns fix summary.
        """
        from services.agent_registry import get_agent
        from services.fs_controller import get_fs
        from services.code_validator import validate_code, extract_code_blocks as _ecb

        # Run code validator on current code for precise feedback
        val_feedback = ""
        raw_blocks = _ecb(f"```python\n{code}\n```")
        if raw_blocks:
            _, src = raw_blocks[0]
            val_report = validate_code(src)
            if val_report.issues:
                val_feedback = "\n".join(str(i) for i in val_report.issues[:5])

        debugger = get_agent("debugger")
        prompt = (
            f"Objective: {objective}\n\n"
            f"Error types detected: {errors}\n\n"
            f"Run output:\n{run_output[:2000]}\n\n"
        )
        if val_feedback:
            prompt += f"Static analysis issues:\n{val_feedback}\n\n"
        prompt += f"Current code:\n```python\n{code[:3000]}\n```\n\nProvide the complete corrected code."

        fix_result = debugger.run(prompt, history)
        fix_text = fix_result.response

        # Write corrected code blocks back to workspace
        fs = get_fs()
        blocks = _extract_code_blocks(fix_text)
        if blocks:
            target = f"{project_path}/main.py".lstrip("./")
            fs.write_file(target, blocks[0].strip())
            self._log.info("AutoDev: wrote fix to %s", target)

        return fix_text[:300]


# ── Singleton ──────────────────────────────────────────────────────────────────

_auto_dev: AutoDev | None = None


def get_auto_dev() -> AutoDev:
    """Return the global AutoDev singleton."""
    global _auto_dev
    if _auto_dev is None:
        _auto_dev = AutoDev()
    return _auto_dev
