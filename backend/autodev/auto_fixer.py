"""
auto_fixer — FASE 10 AutoDev Engine, Component 4

Receives a ValidationError and the original source code, calls the LLM to
produce a corrected version, and retries up to MAX_ATTEMPTS times.

If all attempts fail, the error is escalated (returned un-fixed) so the
AutoDev loop can surface it to a human reviewer.

Responsibilities
----------------
  1. Build a focused prompt: "here is the error, here is the code, fix it."
  2. Call LLM with force_api=True for best correctness.
  3. Validate the fix (AST check) before accepting.
  4. Write the fixed file to the workspace.
  5. Return a ``FixResult`` with status, attempts, and final code.

Role in the system
------------------
Fourth stage in the AutoDev pipeline:
  scaffolder → code_generator → validator → **auto_fixer** → validate again → done

Usage example
-------------
>>> from backend.autodev.auto_fixer import AutoFixer
>>> fixer = AutoFixer(job_id="abc123", workspace="/workspace/jobs/abc123")
>>> fix_result = await fixer.fix(validation_error, original_code)
>>> if fix_result.success:
...     print("Fixed after", fix_result.attempts, "attempt(s)")
>>> else:
...     print("Escalating to human:", fix_result.error)
"""

from __future__ import annotations

import ast
import asyncio
import difflib
import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from services.llm_service import call_llm
from autodev.validator import ValidationError

log = structlog.get_logger(__name__)

MAX_ATTEMPTS = 3
_ESCALATIONS_FILE = "escalations.json"


# ── Models ─────────────────────────────────────────────────────────────────────

@dataclass
class AttemptRecord:
    attempt: int
    prompt_strategy: str       # "error+original" | "error+diff" | "full_history"
    code_before: str
    code_after: str
    error_after: str           # empty string if the fix was accepted


@dataclass
class FixResult:
    file_path: str
    success: bool
    attempts: int
    final_code: str
    error: str = ""            # populated when success=False (for human escalation)
    attempt_history: list[AttemptRecord] = field(default_factory=list)


@dataclass
class FixEscalationReport:
    job_id: str
    file_path: str
    original_error: str
    category: str
    severity: str
    attempts: list[dict]       # serialised AttemptRecord list
    escalated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ── Prompt templates ────────────────────────────────────────────────────────────

_FIXER_SYSTEM = """\
You are an expert code debugger and fixer. Given code with a specific error,
produce a corrected version.

Rules:
- Output ONLY the complete corrected source code.
- Do NOT include markdown fences or explanations.
- Fix ONLY the reported error — do not refactor unrelated code.
- The output must be syntactically valid.
"""

_ATTEMPT1_TEMPLATE = """\
File: {file_path}
Error [{severity} — {category}]{loc}: {message}
{snippet}
Full source code:
{code}

Output the complete corrected file:"""

_ATTEMPT2_TEMPLATE = """\
File: {file_path}
Error [{severity} — {category}]{loc}: {message}

IMPORTANT: A previous fix attempt failed. Here is the diff of what changed:
--- original
+++ attempt_1
{diff}

Current (failed) code:
{code}

Analyse the diff — the previous fix introduced a new problem or did not address
the root cause. Fix the error correctly this time.
Output the complete corrected file:"""

_ATTEMPT3_TEMPLATE = """\
File: {file_path}
Original error [{severity} — {category}]{loc}: {message}

Two previous fix attempts both failed. Full history:

=== Attempt 1 (strategy: error+original) ===
Result error: {err1}
Code produced:
{code1}

=== Attempt 2 (strategy: error+diff) ===
Result error: {err2}
Code produced:
{code2}

Try a completely different approach. Do NOT repeat the same patterns.
{snippet}
Output the complete corrected file:"""


# ── AutoFixer ──────────────────────────────────────────────────────────────────

class AutoFixer:
    """
    Attempts to fix validation errors using a progressive retry strategy.

    Attempt 1: error + original code
    Attempt 2: error + attempt-1 code + unified diff of what changed
    Attempt 3: full history of both attempts + request for different approach

    On all-fail: writes a FixEscalationReport to escalations.json.

    Parameters
    ----------
    job_id:    AutoDev job identifier (for logging and escalation reports).
    workspace: Absolute path to the isolated job directory.
    """

    def __init__(self, job_id: str, workspace: str | Path) -> None:
        self.job_id = job_id
        self.workspace = Path(workspace)

    # ── Public interface ───────────────────────────────────────────────────────

    async def fix(self, error: ValidationError, original_code: str) -> FixResult:
        """
        Attempt to fix *error* in *original_code* with progressive learning.

        Returns FixResult(success=True) on first accepted fix.
        Returns FixResult(success=False) after MAX_ATTEMPTS, and writes
        a FixEscalationReport to jobs/{job_id}/escalations.json.

        Usage example
        -------------
        >>> result = await fixer.fix(validation_error, source_code)
        >>> print(result.success, result.attempts)
        """
        log.info(
            "auto_fixer.start",
            job_id=self.job_id,
            file=error.file_path,
            severity=error.severity,
            category=error.category,
        )

        history: list[AttemptRecord] = []
        codes: list[str] = [original_code]    # codes[0]=original, codes[i]=attempt_i result
        errors_after: list[str] = []

        for attempt in range(1, MAX_ATTEMPTS + 1):
            log.debug("auto_fixer.attempt", attempt=attempt, file=error.file_path,
                      strategy=_strategy_name(attempt))

            # Build attempt-specific prompt
            prompt = self._build_prompt(
                attempt=attempt,
                error=error,
                original_code=original_code,
                codes=codes,
                errors_after=errors_after,
            )

            fixed_code = await self._call_llm_with_prompt(prompt)

            if not fixed_code.strip():
                err_msg = "LLM returned empty fix."
                errors_after.append(err_msg)
                history.append(AttemptRecord(
                    attempt=attempt,
                    prompt_strategy=_strategy_name(attempt),
                    code_before=codes[-1],
                    code_after="",
                    error_after=err_msg,
                ))
                codes.append(codes[-1])  # no progress
                continue

            # Quick AST check before accepting Python fixes
            if error.category in ("syntax", "import") and _is_python(error.file_path):
                if not _ast_valid(fixed_code):
                    err_msg = "Fixed code failed AST validation."
                    errors_after.append(err_msg)
                    history.append(AttemptRecord(
                        attempt=attempt,
                        prompt_strategy=_strategy_name(attempt),
                        code_before=codes[-1],
                        code_after=fixed_code,
                        error_after=err_msg,
                    ))
                    codes.append(fixed_code)
                    continue

            # ── Accept the fix ─────────────────────────────────────────────────
            history.append(AttemptRecord(
                attempt=attempt,
                prompt_strategy=_strategy_name(attempt),
                code_before=codes[-1],
                code_after=fixed_code,
                error_after="",
            ))
            self._write(error.file_path, fixed_code)
            log.info("auto_fixer.fixed", job_id=self.job_id,
                     file=error.file_path, attempts=attempt)
            return FixResult(
                file_path=error.file_path,
                success=True,
                attempts=attempt,
                final_code=fixed_code,
                attempt_history=history,
            )

        # ── All attempts failed — escalate ─────────────────────────────────────
        last_error = errors_after[-1] if errors_after else error.message
        log.warning(
            "auto_fixer.escalate",
            job_id=self.job_id,
            file=error.file_path,
            attempts=MAX_ATTEMPTS,
            last_error=last_error,
        )
        result = FixResult(
            file_path=error.file_path,
            success=False,
            attempts=MAX_ATTEMPTS,
            final_code=codes[-1],
            error=f"Unfixed after {MAX_ATTEMPTS} attempts. Last error: {last_error}",
            attempt_history=history,
        )
        self._save_escalation(error, history, errors_after)
        return result

    async def fix_all(
        self,
        errors: list[ValidationError],
        code_map: dict[str, str],
    ) -> dict[str, FixResult]:
        """
        Fix all critical errors in *errors*.

        Parameters
        ----------
        errors:   List of ValidationError from the Validator.
        code_map: Dict mapping file_path → source code.

        Returns
        -------
        Dict mapping file_path → FixResult.
        """
        to_fix = [e for e in errors if e.severity in ("critical", "high")]
        # One fix per file (first error wins)
        seen: set[str] = set()
        unique: list[ValidationError] = []
        for e in to_fix:
            if e.file_path not in seen:
                seen.add(e.file_path)
                unique.append(e)

        results: dict[str, FixResult] = {}
        for error in unique:
            original = code_map.get(error.file_path, "")
            results[error.file_path] = await self.fix(error, original)
        return results

    # ── Prompt builder ─────────────────────────────────────────────────────────

    def _build_prompt(
        self,
        attempt: int,
        error: ValidationError,
        original_code: str,
        codes: list[str],      # codes[0]=original, codes[i]=attempt result i
        errors_after: list[str],
    ) -> str:
        loc = f" (line {error.line})" if error.line else ""
        snippet = (
            f"Code snippet:\n{error.code_snippet}\n" if error.code_snippet else ""
        )

        if attempt == 1:
            return _ATTEMPT1_TEMPLATE.format(
                file_path=error.file_path,
                severity=error.severity.upper(),
                category=error.category,
                loc=loc,
                message=error.message,
                snippet=snippet,
                code=codes[0],
            )

        if attempt == 2:
            diff = _unified_diff(codes[0], codes[1] if len(codes) > 1 else codes[0])
            return _ATTEMPT2_TEMPLATE.format(
                file_path=error.file_path,
                severity=error.severity.upper(),
                category=error.category,
                loc=loc,
                message=error.message,
                diff=diff,
                code=codes[-1],
            )

        # attempt == 3
        return _ATTEMPT3_TEMPLATE.format(
            file_path=error.file_path,
            severity=error.severity.upper(),
            category=error.category,
            loc=loc,
            message=error.message,
            err1=errors_after[0] if len(errors_after) > 0 else "unknown",
            code1=codes[1] if len(codes) > 1 else "(same as original)",
            err2=errors_after[1] if len(errors_after) > 1 else "unknown",
            code2=codes[2] if len(codes) > 2 else "(same as original)",
            snippet=snippet,
        )

    # ── LLM call ───────────────────────────────────────────────────────────────

    async def _call_llm_with_prompt(self, prompt: str) -> str:
        raw = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: call_llm(
                [
                    {"role": "system", "content": _FIXER_SYSTEM},
                    {"role": "user",   "content": prompt},
                ],
                force_api=True,
            ),
        )
        fixed = raw or ""
        fixed = re.sub(r"^```[a-z]*\n?", "", fixed, flags=re.MULTILINE)
        fixed = re.sub(r"\n?```$", "", fixed, flags=re.MULTILINE)
        return fixed.strip() + "\n"

    # ── File I/O ───────────────────────────────────────────────────────────────

    def _write(self, relative_path: str, code: str) -> None:
        full_path = self.workspace / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(code, encoding="utf-8")

    def _save_escalation(
        self,
        error: ValidationError,
        history: list[AttemptRecord],
        errors_after: list[str],
    ) -> None:
        """Append a FixEscalationReport to jobs/{job_id}/escalations.json."""
        report = FixEscalationReport(
            job_id=self.job_id,
            file_path=error.file_path,
            original_error=error.message,
            category=error.category,
            severity=error.severity,
            attempts=[
                {
                    "attempt": r.attempt,
                    "strategy": r.prompt_strategy,
                    "error_after": r.error_after,
                }
                for r in history
            ],
        )
        esc_file = self.workspace / _ESCALATIONS_FILE
        existing: list[dict] = []
        if esc_file.exists():
            try:
                existing = json.loads(esc_file.read_text(encoding="utf-8"))
            except Exception as exc:
                log.debug("[autodev.auto_fixer] suppressed exception", exc_info=exc)
                pass
        existing.append(asdict(report))
        esc_file.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        log.info("auto_fixer.escalation_saved", job_id=self.job_id,
                 file=error.file_path, path=str(esc_file))


# ── Helpers ────────────────────────────────────────────────────────────────────

def _strategy_name(attempt: int) -> str:
    return {1: "error+original", 2: "error+diff", 3: "full_history"}.get(attempt, "unknown")


def _unified_diff(before: str, after: str) -> str:
    lines_a = before.splitlines(keepends=True)
    lines_b = after.splitlines(keepends=True)
    diff = difflib.unified_diff(lines_a, lines_b, fromfile="before", tofile="after", n=3)
    result = "".join(diff)
    return result[:2000] if len(result) > 2000 else result


def _is_python(path: str) -> bool:
    return path.endswith(".py")


def _ast_valid(code: str) -> bool:
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False
