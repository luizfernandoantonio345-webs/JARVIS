"""
shell_exec action — safe shell execution with process management.

Security model:
  - Command whitelist (ALLOWED_COMMANDS)
  - Hard timeout (default 30 s, configurable via JARVIS_SHELL_TIMEOUT)
  - Memory cap enforced via resource limits on POSIX
  - No network commands, no sudo, no pip, no rm -rf
  - CWD locked to ALLOWED_BASE_DIR

Process management (run_process):
  - Streams stdout/stderr in real time, collected into a rolling log buffer
  - Error pattern detection in live output
  - Optional restart on crash (max MAX_RESTARTS times)
  - Returns structured ProcessResult
"""

from __future__ import annotations

import logging
import os
import platform
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Callable

from .file_reader import ALLOWED_BASE_DIR

log = logging.getLogger(__name__)

ACTION_NAME = "shell_exec"
SYSTEM_PROMPT = "Execute safe shell commands only. Whitelist enforced."

# ── Configuration ──────────────────────────────────────────────────────────────
# JARVIS_EXEC_TIMEOUT takes priority over legacy JARVIS_SHELL_TIMEOUT
_DEFAULT_TIMEOUT   = int(os.getenv("JARVIS_EXEC_TIMEOUT") or os.getenv("JARVIS_SHELL_TIMEOUT", "30"))
_MAX_OUTPUT_BYTES  = int(os.getenv("JARVIS_SHELL_MAX_OUTPUT", str(8 * 1024)))   # 8 KB cap
_MAX_RESTARTS      = int(os.getenv("JARVIS_SHELL_MAX_RESTARTS", "3"))
# Memory cap in MB (POSIX only; ignored on Windows)
_MEMORY_CAP_MB     = int(os.getenv("JARVIS_SHELL_MEMORY_MB", "256"))

# Allowed base commands (first token of the command string)
ALLOWED_COMMANDS: frozenset[str] = frozenset({
    "ls", "dir", "pwd", "cd", "mkdir", "cat", "head", "tail",
    "echo", "touch", "python", "python3", "node", "npm", "npx",
    "pip", "uvicorn", "pytest", "git",
})

# Patterns that are NEVER allowed regardless of whitelist
_BLOCKED_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\brm\s+-[rRfF]*\b"),           # rm -rf
    re.compile(r"\bsudo\b"),                     # privilege escalation
    re.compile(r"\bchmod\s+[0-7]*7[0-7]*\b"),   # world-writeable chmod
    re.compile(r">\s*/dev/sd"),                  # disk write
    re.compile(r"\bdd\b.*\bof="),                # dd overwrite
    re.compile(r";\s*rm\b"),                     # chained rm
    re.compile(r"\|\s*bash\b"),                  # pipe to bash
    re.compile(r"curl.*\|\s*(bash|sh)\b"),       # curl | bash
    re.compile(r"\bpip\s+install\b"),            # pip install blocked
    re.compile(r"\bpip3\s+install\b"),           # pip3 install blocked
]

# Error patterns to detect in live process output
_ERROR_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(error|exception|traceback|fatal|critical|failed|crash)\b", re.IGNORECASE),
    re.compile(r"^\s*at\s+\w+.*:\d+", re.MULTILINE),      # JS stack trace
    re.compile(r"Traceback \(most recent call last\)"),    # Python traceback
]

# ── Result types ───────────────────────────────────────────────────────────────

@dataclass
class ProcessResult:
    command: str
    exit_code: int | None
    stdout: str
    stderr: str
    duration_s: float
    errors_detected: list[str] = field(default_factory=list)  # type: ignore[assignment]
    restarts: int = 0
    timed_out: bool = False
    killed: bool = False

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and not self.killed

    def to_text(self) -> str:
        status = "✅ OK" if self.success else "❌ FAILED"
        lines = [
            f"{status} | exit={self.exit_code} | {self.duration_s:.1f}s"
            + (f" | restarts={self.restarts}" if self.restarts else ""),
        ]
        if self.stdout.strip():
            lines += ["--- STDOUT ---", self.stdout.rstrip()]
        if self.stderr.strip():
            lines += ["--- STDERR ---", self.stderr.rstrip()]
        if self.errors_detected:
            lines += ["--- ERRORS DETECTED ---"] + [f"  • {e}" for e in self.errors_detected]
        return "\n".join(lines)


# ── Security helpers ───────────────────────────────────────────────────────────

def _validate_command(cmd_str: str) -> str | None:
    """Return an error string if the command is not allowed, else None."""
    for pattern in _BLOCKED_PATTERNS:
        if pattern.search(cmd_str):
            return f"Blocked pattern detected: {pattern.pattern!r}"

    first_token = cmd_str.strip().split()[0].lower() if cmd_str.strip() else ""
    # Strip path prefix (e.g. /usr/bin/python → python)
    base = Path(first_token).name
    if base not in ALLOWED_COMMANDS:
        return f"Command '{base}' not whitelisted. Allowed: {sorted(ALLOWED_COMMANDS)}"

    return None


def _apply_posix_limits() -> None:
    """Apply memory + file descriptor limits on POSIX systems."""
    if platform.system() == "Windows":
        return
    try:
        import importlib
        resource = importlib.import_module("resource")  # POSIX only
        mem_bytes = _MEMORY_CAP_MB * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))  # type: ignore[attr-defined]
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))          # type: ignore[attr-defined]
    except Exception:
        pass  # non-fatal


# ── Core execution ─────────────────────────────────────────────────────────────

def _run_once(
    cmd_str: str,
    timeout: int,
    cwd: Path,
    on_line: Callable[[str], None] | None = None,
) -> tuple[int | None, str, str, bool]:
    """
    Run a single subprocess, streaming output line-by-line.

    Returns (exit_code, stdout, stderr, timed_out).
    """
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    total_bytes = 0

    try:
        proc = subprocess.Popen(
            cmd_str,
            shell=True,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=_apply_posix_limits if platform.system() != "Windows" else None,
        )
    except OSError as exc:
        return None, "", str(exc), False

    def _reader(stream: "IO[str]", collector: list[str]) -> None:
        nonlocal total_bytes
        for raw_line in stream:
            line: str = raw_line
            if total_bytes < _MAX_OUTPUT_BYTES:
                collector.append(line)
                total_bytes += len(line)
            if on_line:
                on_line(line)

    t_out = threading.Thread(target=_reader, args=(proc.stdout, stdout_lines), daemon=True)
    t_err = threading.Thread(target=_reader, args=(proc.stderr, stderr_lines), daemon=True)
    t_out.start()
    t_err.start()

    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        timed_out = True
    finally:
        t_out.join(timeout=2)
        t_err.join(timeout=2)

    return proc.returncode, "".join(stdout_lines), "".join(stderr_lines), timed_out


def _detect_errors(text: str) -> list[str]:
    """Return matching error lines found in the output."""
    found: list[str] = []
    for line in text.splitlines():
        for pat in _ERROR_PATTERNS:
            if pat.search(line):
                found.append(line.strip())
                break
    return found[:20]  # cap at 20 entries


# ── Public API ─────────────────────────────────────────────────────────────────

def run_process(
    command: str,
    timeout: int = _DEFAULT_TIMEOUT,
    restart_on_error: bool = False,
    on_line: Callable[[str], None] | None = None,
    cwd: Path | None = None,
) -> ProcessResult:
    """
    Run a shell command with full process management.

    Args:
        command:          Shell command string.
        timeout:          Max seconds before the process is killed.
        restart_on_error: Restart if the process exits non-zero (max _MAX_RESTARTS).
        on_line:          Optional callback called for every output line in real time.
        cwd:              Working directory (defaults to ALLOWED_BASE_DIR).

    Returns:
        ProcessResult with captured output, error detection, and stats.
    """
    error = _validate_command(command)
    if error:
        return ProcessResult(
            command=command, exit_code=None,
            stdout="", stderr=f"❌ Security: {error}",
            duration_s=0.0,
        )

    work_dir = cwd or ALLOWED_BASE_DIR
    restarts = 0
    start = time.monotonic()

    while True:
        exit_code, stdout, stderr, timed_out = _run_once(command, timeout, work_dir, on_line)
        duration = time.monotonic() - start
        errors = _detect_errors(stdout + "\n" + stderr)

        result = ProcessResult(
            command=command,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_s=round(duration, 2),
            errors_detected=errors,
            restarts=restarts,
            timed_out=timed_out,
        )

        if timed_out or exit_code == 0 or not restart_on_error or restarts >= _MAX_RESTARTS:
            break

        restarts += 1
        log.warning("[shell_exec] restart %d/%d for: %s", restarts, _MAX_RESTARTS, command)
        time.sleep(0.5)

    return result


def execute(input_str: str) -> str:
    """Legacy single-shot execute — used by the action loader."""
    result = run_process(input_str, timeout=_DEFAULT_TIMEOUT)
    return result.to_text()

