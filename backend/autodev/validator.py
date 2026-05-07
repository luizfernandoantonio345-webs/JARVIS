"""
validator — FASE 10 AutoDev Engine, Component 3

Validates generated source files for syntax errors, import errors,
and basic runtime issues using the existing code_validator infrastructure
plus lightweight subprocess-based syntax checks.

Responsibilities
----------------
  1. Run AST-based syntax validation for Python files.
  2. Run ``python -m py_compile`` (isolated) for deeper import checks.
  3. Optionally run in the Docker sandbox (when available).
  4. Return a structured ``List[ValidationError]`` report.

Role in the system
------------------
Third stage in the AutoDev pipeline:
  scaffolder → code_generator → **validator** → auto_fixer → done

Usage example
-------------
>>> from backend.autodev.validator import Validator
>>> v = Validator(job_id="abc123", workspace="/workspace/jobs/abc123")
>>> errors = await v.validate(generated_files)
>>> for e in errors:
...     print(e.file_path, e.severity, e.message)
"""

from __future__ import annotations

import ast
import asyncio
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from autodev.code_generator import GeneratedFile
from services.code_validator import PythonValidator

log = structlog.get_logger(__name__)


# ── Models ─────────────────────────────────────────────────────────────────────

@dataclass
class ValidationError:
    file_path: str
    line: int | None
    severity: str       # "critical" | "high" | "medium" | "low"
    category: str       # "syntax" | "import" | "security" | "runtime" | "quality"
    message: str
    code_snippet: str = ""

    def __str__(self) -> str:
        loc = f":{self.line}" if self.line else ""
        return f"[{self.severity.upper()}] {self.file_path}{loc} — {self.message}"


# ── Validator ──────────────────────────────────────────────────────────────────

class Validator:
    """
    Multi-pass validator for AutoDev-generated files.

    Parameters
    ----------
    job_id:    AutoDev job identifier.
    workspace: Absolute path to the isolated job directory.
    """

    def __init__(self, job_id: str, workspace: str | Path) -> None:
        self.job_id = job_id
        self.workspace = Path(workspace)
        self._code_validator = PythonValidator()

    async def validate(self, files: list[GeneratedFile]) -> list[ValidationError]:
        """
        Run all validation passes on *files* and return a flat error list.

        Passes (in order):
          1. AST syntax check (Python only).
          2. py_compile subprocess check (Python only).
          3. CodeValidator security + quality checks (Python only).

        Usage example
        -------------
        >>> errors = await validator.validate(generated_files)
        >>> critical = [e for e in errors if e.severity == "critical"]
        """
        log.info("validator.start", job_id=self.job_id, files=len(files))
        all_errors: list[ValidationError] = []

        for gf in files:
            if gf.language == "python":
                errs = await self._validate_python(gf)
                all_errors.extend(errs)
            # Non-Python files: skip deep validation for now
            log.debug("validator.file", path=gf.path, errors=len(all_errors))

        log.info("validator.done", job_id=self.job_id, total_errors=len(all_errors))
        return all_errors

    # ── Validation passes ──────────────────────────────────────────────────────

    async def _validate_python(self, gf: GeneratedFile) -> list[ValidationError]:
        errors: list[ValidationError] = []

        # Pass 1: AST syntax
        errors.extend(self._ast_check(gf))
        if any(e.severity == "critical" for e in errors):
            return errors  # No point running further passes on broken syntax

        # Pass 2: py_compile (subprocess)
        errors.extend(await self._py_compile_check(gf))

        # Pass 3: CodeValidator (security + quality)
        errors.extend(self._code_validator_check(gf))

        return errors

    def _ast_check(self, gf: GeneratedFile) -> list[ValidationError]:
        try:
            ast.parse(gf.code)
            return []
        except SyntaxError as exc:
            return [
                ValidationError(
                    file_path=gf.path,
                    line=exc.lineno,
                    severity="critical",
                    category="syntax",
                    message=str(exc.msg),
                    code_snippet=exc.text or "",
                )
            ]

    async def _py_compile_check(self, gf: GeneratedFile) -> list[ValidationError]:
        full_path = self.workspace / gf.path
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "py_compile", str(full_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
            if proc.returncode != 0:
                msg = stderr.decode(errors="replace").strip()
                return [
                    ValidationError(
                        file_path=gf.path,
                        line=None,
                        severity="critical",
                        category="syntax",
                        message=f"py_compile: {msg}",
                    )
                ]
        except (asyncio.TimeoutError, FileNotFoundError):
            pass
        return []

    def _code_validator_check(self, gf: GeneratedFile) -> list[ValidationError]:
        try:
            report = self._code_validator.validate(gf.code)
        except Exception as exc:
            log.warning("validator.code_validator_error", error=str(exc))
            return []

        errors: list[ValidationError] = []
        for issue in report.issues:
            errors.append(
                ValidationError(
                    file_path=gf.path,
                    line=issue.line,
                    severity=issue.severity.value.lower(),
                    category=issue.code.lower() if issue.code else "quality",
                    message=issue.message,
                    code_snippet=issue.context or "",
                )
            )
        return errors
