"""
ProjectRunner — detects project type and runs it safely with timeout.

Supported project types:
  Python  → finds main.py or uvicorn app, runs with timeout
  Node/JS → npm install + npm run dev (or npm start)

Security:
  - Uses shell_exec whitelist
  - Hard timeout via JARVIS_EXEC_TIMEOUT
  - Output capped at 8KB
  - CWD locked to WORKSPACE_DIR

Usage:
    from services.project_runner import ProjectRunner
    runner = ProjectRunner()
    result = runner.run_project("/path/to/project")
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from actions.shell_exec import run_process
from services.fs_controller import WORKSPACE_DIR, _safe_path

log = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = int(os.getenv("JARVIS_EXEC_TIMEOUT") or os.getenv("JARVIS_SHELL_TIMEOUT", "30"))


# ── Result type ────────────────────────────────────────────────────────────────

@dataclass
class RunResult:
    project_type: str
    command: str
    success: bool
    stdout: str = ""
    stderr: str = ""
    logs: list[str] = field(default_factory=list)
    error: str | None = None

    def to_text(self) -> str:
        lines = [f"Project type: {self.project_type}", f"Command: {self.command}"]
        status = "✅ Success" if self.success else "❌ Failed"
        lines.append(status)
        if self.stdout.strip():
            lines += ["--- Output ---", self.stdout[:4096]]
        if self.stderr.strip():
            lines += ["--- Errors ---", self.stderr[:2048]]
        if self.error:
            lines.append(f"Error: {self.error}")
        return "\n".join(lines)


# ── Detection ──────────────────────────────────────────────────────────────────

def _detect_project_type(project_dir: Path) -> str:
    """Detect project type from directory contents."""
    if (project_dir / "package.json").exists():
        return "node"
    if (project_dir / "pyproject.toml").exists() or (project_dir / "setup.py").exists():
        return "python"
    if (project_dir / "main.py").exists():
        return "python"
    if (project_dir / "app.py").exists():
        return "python"
    if (project_dir / "manage.py").exists():
        return "python"
    # Scan for any .py file
    if any(project_dir.glob("*.py")):
        return "python"
    if any(project_dir.glob("*.js")) or any(project_dir.glob("*.ts")):
        return "node"
    return "unknown"


def _find_python_entry(project_dir: Path) -> str | None:
    """Find the best Python entry point."""
    for candidate in ("main.py", "app.py", "run.py", "server.py"):
        if (project_dir / candidate).exists():
            return candidate
    # Look for uvicorn-style app
    for py_file in project_dir.glob("*.py"):
        text = py_file.read_text(encoding="utf-8", errors="replace")
        if "FastAPI" in text or "uvicorn" in text:
            # Guess module name from file
            return f"uvicorn {py_file.stem}:app --reload"
    return None


# ── Runner ─────────────────────────────────────────────────────────────────────

class ProjectRunner:
    """
    Detects and runs a project safely with timeout and output capping.
    """

    def run_project(self, path: str, timeout: int = _DEFAULT_TIMEOUT) -> RunResult:
        """
        Auto-detect project type and run it.

        Args:
            path:    Path relative to workspace or absolute (must be inside workspace).
            timeout: Max seconds to run.

        Returns:
            RunResult — always returned, never raises.
        """
        resolved = _safe_path(path)
        if hasattr(resolved, "error"):
            return RunResult(
                project_type="unknown",
                command="",
                success=False,
                error=resolved.error,
            )

        project_dir: Path = resolved if resolved.is_dir() else resolved.parent

        project_type = _detect_project_type(project_dir)
        log.info("ProjectRunner: detected type=%r for %s", project_type, project_dir)

        if project_type == "python":
            return self._run_python(project_dir, timeout)
        if project_type == "node":
            return self._run_node(project_dir, timeout)

        return RunResult(
            project_type="unknown",
            command="",
            success=False,
            error=(
                f"Cannot detect project type in {project_dir}. "
                "Expected main.py, app.py, package.json, etc."
            ),
        )

    def _run_python(self, project_dir: Path, timeout: int) -> RunResult:
        """Run Python project."""
        entry = _find_python_entry(project_dir)

        if entry is None:
            return RunResult(
                project_type="python",
                command="",
                success=False,
                error="No Python entry point found (main.py, app.py, etc.)",
            )

        # Build command
        if entry.startswith("uvicorn"):
            command = entry
        else:
            command = f"python {entry}"

        log.info("ProjectRunner: python command=%r cwd=%s", command, project_dir)
        proc = run_process(command, timeout=timeout, cwd=project_dir)

        return RunResult(
            project_type="python",
            command=command,
            success=proc.success,
            stdout=proc.stdout,
            stderr=proc.stderr,
            logs=proc.errors_detected,
        )

    def _run_node(self, project_dir: Path, timeout: int) -> RunResult:
        """Run Node.js project: npm install, then npm run dev or npm start."""
        logs: list[str] = []

        # Step 1: npm install (only if node_modules missing)
        nm = project_dir / "node_modules"
        if not nm.exists():
            log.info("ProjectRunner: running npm install in %s", project_dir)
            install_result = run_process("npm install", timeout=120, cwd=project_dir)
            logs.extend(install_result.errors_detected)
            if not install_result.success:
                return RunResult(
                    project_type="node",
                    command="npm install",
                    success=False,
                    stdout=install_result.stdout,
                    stderr=install_result.stderr,
                    logs=logs,
                    error="npm install failed",
                )

        # Step 2: detect run script
        pkg_json = project_dir / "package.json"
        run_script = "npm start"
        try:
            import json
            pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
            scripts = pkg.get("scripts", {})
            if "dev" in scripts:
                run_script = "npm run dev"
            elif "start" in scripts:
                run_script = "npm start"
        except Exception as exc:
            log.warning("ProjectRunner: failed to parse package.json: %s", exc)

        log.info("ProjectRunner: node command=%r cwd=%s", run_script, project_dir)
        proc = run_process(run_script, timeout=timeout, cwd=project_dir)
        logs.extend(proc.errors_detected)

        return RunResult(
            project_type="node",
            command=run_script,
            success=proc.success,
            stdout=proc.stdout,
            stderr=proc.stderr,
            logs=logs,
        )


# ── Singleton ──────────────────────────────────────────────────────────────────

_runner = ProjectRunner()


def get_runner() -> ProjectRunner:
    """Return the global ProjectRunner singleton."""
    return _runner
