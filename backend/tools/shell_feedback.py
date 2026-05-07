"""
shell_feedback — FASE 8, Etapa 1

Shell execution with a **real feedback loop**:

  1. Streams stdout/stderr line-by-line via subprocess (no buffering).
  2. After execution, the full output is injected into the LLM context so
     the next reasoning step can observe what happened.
  3. The result is persisted to the episodic Memory System with timestamp,
     exit-code, and status label so future sessions can recall past runs.

Role in the system:
  • Replaces the fire-and-forget shell_exec for autonomous loop scenarios.
  • Used by AutonomousLoop (core/autonomous_loop.py) to produce observable
    execution results that feed back into the planner.
  • Compatible with the existing shell_exec whitelist / blocked-pattern
    security layer.
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator, Callable, List

import structlog

from actions.shell_exec import ALLOWED_COMMANDS, _BLOCKED_PATTERNS, ALLOWED_BASE_DIR
from services.memory_service import save_memory

log: structlog.BoundLogger = structlog.get_logger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────
_DEFAULT_TIMEOUT = int(os.getenv("JARVIS_EXEC_TIMEOUT", "30"))
_MAX_OUTPUT_BYTES = int(os.getenv("JARVIS_SHELL_MAX_OUTPUT", str(16 * 1024)))  # 16 KB

# Session-id used for episodic memory when no external session is provided
_FEEDBACK_SESSION_ID = "__shell_feedback__"


# ── Result model ───────────────────────────────────────────────────────────────

@dataclass
class FeedbackResult:
    """Structured outcome of a shell command with feedback-loop metadata."""

    command: str
    exit_code: int | None
    stdout: str
    stderr: str
    duration_s: float
    timestamp: str
    status: str                           # "success" | "error" | "timeout" | "blocked"
    llm_context_snippet: str = ""        # pre-built snippet ready to inject into prompt
    memory_saved: bool = False

    @property
    def success(self) -> bool:
        return self.status == "success"


# ── Security check (re-uses shell_exec rules) ─────────────────────────────────

def _security_check(command: str) -> str | None:
    """Return an error string if the command is blocked, else None."""
    tokens = command.split()
    if not tokens:
        return "Empty command."
    base_cmd = Path(tokens[0]).name
    if base_cmd not in ALLOWED_COMMANDS:
        return f"Command '{base_cmd}' is not in the allowed whitelist."
    for pattern in _BLOCKED_PATTERNS:
        if pattern.search(command):
            return f"Blocked pattern detected: {pattern.pattern}"
    return None


# ── Sync streaming execution ───────────────────────────────────────────────────

def run_with_feedback(
    command: str,
    *,
    session_id: str = _FEEDBACK_SESSION_ID,
    cwd: str | None = None,
    timeout: int = _DEFAULT_TIMEOUT,
    on_line: Callable[[str], None] | None = None,
    inject_to_memory: bool = True,
) -> FeedbackResult:
    """
    Execute *command* synchronously, stream output line-by-line, then:
      - Build an LLM context snippet from the output.
      - Optionally persist the result to the episodic memory tier.

    Parameters
    ----------
    command:          Shell command string (security-checked against whitelist).
    session_id:       Memory session to persist result under.
    cwd:              Working directory (defaults to ALLOWED_BASE_DIR).
    timeout:          Hard timeout in seconds.
    on_line:          Optional callback invoked for each output line in real time.
    inject_to_memory: Whether to persist result to episodic memory.

    Returns
    -------
    FeedbackResult with structured metadata + LLM-ready context snippet.

    Usage example
    -------------
    >>> result = run_with_feedback("python main.py", session_id="sess-001")
    >>> print(result.llm_context_snippet)
    >>> if not result.success:
    ...     # feed result back to planner for re-planning
    ...     planner.replan(result.llm_context_snippet)
    """
    block_reason = _security_check(command)
    if block_reason:
        ts = datetime.now(timezone.utc).isoformat()
        snippet = f"[SHELL BLOCKED @ {ts}]\nReason: {block_reason}\nCommand: {command}"
        return FeedbackResult(
            command=command,
            exit_code=None,
            stdout="",
            stderr=block_reason,
            duration_s=0.0,
            timestamp=ts,
            status="blocked",
            llm_context_snippet=snippet,
            memory_saved=False,
        )

    effective_cwd = cwd or str(ALLOWED_BASE_DIR)
    stdout_lines: List[str] = []
    stderr_lines: List[str] = []
    total_bytes = 0

    log.info("shell_feedback.start", command=command, cwd=effective_cwd, timeout=timeout)
    t0 = time.monotonic()

    try:
        proc = subprocess.Popen(
            command,
            shell=False,
            executable=None,
            args=command.split(),
            cwd=effective_cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=os.environ.copy(),
        )

        def _drain(stream: object, bucket: List[str], label: str) -> None:
            nonlocal total_bytes
            for raw_line in stream:  # type: ignore[union-attr]
                if total_bytes > _MAX_OUTPUT_BYTES:
                    break
                line = raw_line.rstrip("\n")
                total_bytes += len(line)
                bucket.append(line)
                if on_line:
                    on_line(f"[{label}] {line}")
                log.debug("shell_feedback.output", label=label, line=line)

        import threading

        t_out = threading.Thread(target=_drain, args=(proc.stdout, stdout_lines, "stdout"), daemon=True)
        t_err = threading.Thread(target=_drain, args=(proc.stderr, stderr_lines, "stderr"), daemon=True)
        t_out.start()
        t_err.start()

        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            t_out.join(timeout=2)
            t_err.join(timeout=2)
            ts = datetime.now(timezone.utc).isoformat()
            snippet = _build_snippet(command, None, stdout_lines, stderr_lines, "timeout", ts)
            log.warning("shell_feedback.timeout", command=command)
            return FeedbackResult(
                command=command,
                exit_code=None,
                stdout="\n".join(stdout_lines),
                stderr="\n".join(stderr_lines),
                duration_s=time.monotonic() - t0,
                timestamp=ts,
                status="timeout",
                llm_context_snippet=snippet,
                memory_saved=False,
            )

        t_out.join(timeout=2)
        t_err.join(timeout=2)

    except FileNotFoundError as exc:
        ts = datetime.now(timezone.utc).isoformat()
        err = f"Command not found: {exc}"
        snippet = _build_snippet(command, 127, [], [err], "error", ts)
        return FeedbackResult(
            command=command,
            exit_code=127,
            stdout="",
            stderr=err,
            duration_s=time.monotonic() - t0,
            timestamp=ts,
            status="error",
            llm_context_snippet=snippet,
            memory_saved=False,
        )

    duration = time.monotonic() - t0
    ts = datetime.now(timezone.utc).isoformat()
    exit_code = proc.returncode
    status = "success" if exit_code == 0 else "error"

    snippet = _build_snippet(command, exit_code, stdout_lines, stderr_lines, status, ts)

    memory_saved = False
    if inject_to_memory:
        try:
            save_memory(
                session_id=session_id,
                message=f"shell: {command}",
                response=snippet,
                action="shell_feedback",
            )
            memory_saved = True
        except Exception as exc:
            log.warning("shell_feedback.memory_save_failed", error=str(exc))

    log.info(
        "shell_feedback.done",
        command=command,
        exit_code=exit_code,
        duration_s=round(duration, 2),
        status=status,
        memory_saved=memory_saved,
    )

    return FeedbackResult(
        command=command,
        exit_code=exit_code,
        stdout="\n".join(stdout_lines),
        stderr="\n".join(stderr_lines),
        duration_s=round(duration, 2),
        timestamp=ts,
        status=status,
        llm_context_snippet=snippet,
        memory_saved=memory_saved,
    )


# ── Async streaming execution ──────────────────────────────────────────────────

async def run_with_feedback_async(
    command: str,
    *,
    session_id: str = _FEEDBACK_SESSION_ID,
    cwd: str | None = None,
    timeout: int = _DEFAULT_TIMEOUT,
    inject_to_memory: bool = True,
) -> AsyncIterator[str]:
    """
    Async generator that yields output lines in real time, then yields a final
    JSON-serialisable summary line prefixed with ``__RESULT__:``.

    Usage example
    -------------
    >>> async for line in run_with_feedback_async("python tests.py"):
    ...     if line.startswith("__RESULT__:"):
    ...         result = json.loads(line[len("__RESULT__:"):])
    ...     else:
    ...         print(line)          # stream to UI / WebSocket
    """
    block_reason = _security_check(command)
    if block_reason:
        ts = datetime.now(timezone.utc).isoformat()
        yield f"[BLOCKED] {block_reason}"
        import json
        yield "__RESULT__:" + json.dumps(
            {"status": "blocked", "exit_code": None, "command": command, "timestamp": ts}
        )
        return

    effective_cwd = cwd or str(ALLOWED_BASE_DIR)
    stdout_lines: List[str] = []
    stderr_lines: List[str] = []
    t0 = asyncio.get_event_loop().time()

    proc = await asyncio.create_subprocess_exec(
        *command.split(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=effective_cwd,
    )

    async def _read_stream(stream: asyncio.StreamReader, label: str) -> None:
        async for raw in stream:
            line = raw.decode().rstrip("\n")
            stdout_lines.append(line) if label == "stdout" else stderr_lines.append(line)

    try:
        done, _ = await asyncio.wait_for(
            asyncio.gather(
                _read_stream(proc.stdout, "stdout"),  # type: ignore[arg-type]
                _read_stream(proc.stderr, "stderr"),  # type: ignore[arg-type]
            ),
            timeout=timeout,
        )
        await proc.wait()
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        yield "[TIMEOUT] Process killed."
        import json
        yield "__RESULT__:" + json.dumps({"status": "timeout", "exit_code": None})
        return

    for line in stdout_lines:
        yield f"[stdout] {line}"
    for line in stderr_lines:
        yield f"[stderr] {line}"

    exit_code = proc.returncode
    duration = asyncio.get_event_loop().time() - t0
    ts = datetime.now(timezone.utc).isoformat()
    status = "success" if exit_code == 0 else "error"
    snippet = _build_snippet(command, exit_code, stdout_lines, stderr_lines, status, ts)

    if inject_to_memory:
        try:
            save_memory(
                session_id=session_id,
                message=f"shell: {command}",
                response=snippet,
                action="shell_feedback",
            )
        except Exception as exc:
            log.warning("shell_feedback_async.memory_save_failed", error=str(exc))

    import json
    yield "__RESULT__:" + json.dumps(
        {
            "status": status,
            "exit_code": exit_code,
            "command": command,
            "timestamp": ts,
            "duration_s": round(duration, 2),
            "llm_context_snippet": snippet,
        }
    )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _build_snippet(
    command: str,
    exit_code: int | None,
    stdout_lines: List[str],
    stderr_lines: List[str],
    status: str,
    ts: str,
) -> str:
    """Build a compact LLM context snippet from execution results."""
    stdout_text = "\n".join(stdout_lines[-50:]) if stdout_lines else "(no output)"
    stderr_text = "\n".join(stderr_lines[-20:]) if stderr_lines else "(no errors)"
    return (
        f"[SHELL EXECUTION @ {ts}]\n"
        f"Command : {command}\n"
        f"Status  : {status.upper()} (exit={exit_code})\n"
        f"--- stdout ---\n{stdout_text}\n"
        f"--- stderr ---\n{stderr_text}\n"
        f"[END SHELL EXECUTION]"
    )
