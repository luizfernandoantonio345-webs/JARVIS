"""
TerminalManager — persistent subprocess sessions with feedback loop.

Each session is a named subprocess that:
  - Keeps stdin/stdout/stderr streams open
  - Accepts commands over time (like a real terminal)
  - Streams output back via non-blocking reads
  - Tracks full output history per session
  - Auto-kills idle sessions after IDLE_TIMEOUT seconds

Architecture:
  TerminalSession   → one running shell process
  TerminalManager   → registry of all sessions (singleton)

Safety:
  - All commands validated through ShellExec whitelist before dispatch
  - Sessions restricted to WORKSPACE_DIR (cwd)
  - Max output per read capped at 64KB
  - Session lifetime capped at MAX_SESSION_AGE seconds

Usage:
    from services.terminal_manager import get_terminal_manager
    tm = get_terminal_manager()
    sid = tm.create_session("my-project")
    output = tm.send_command(sid, "python main.py")
    tm.kill_session(sid)
"""

from __future__ import annotations

import logging
import os
import queue
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from services.fs_controller import WORKSPACE_DIR

log = logging.getLogger(__name__)

IDLE_TIMEOUT      = 300   # seconds before auto-kill
MAX_SESSION_AGE   = 1800  # 30-minute hard cap
MAX_OUTPUT_BYTES  = 64 * 1024   # 64KB per capture
READ_TIMEOUT      = 10.0  # seconds to wait for command output
POLL_INTERVAL     = 0.05  # seconds between non-blocking reads

# Shell to use (Windows: cmd, POSIX: bash/sh)
_SHELL_BIN = "cmd.exe" if os.name == "nt" else (
    "/bin/bash" if Path("/bin/bash").exists() else "/bin/sh"
)
_SHELL_ARGS = ["/K"] if os.name == "nt" else ["--norc", "--noprofile"]


# ── Session ────────────────────────────────────────────────────────────────────

@dataclass
class SessionInfo:
    """Metadata snapshot (no live process reference — safe to serialize)."""
    session_id: str
    name: str
    cwd: str
    created_at: float
    last_used: float
    alive: bool
    output_lines: int


class TerminalSession:
    """
    A single persistent shell session.

    The subprocess runs continuously; commands are written to stdin.
    Output is read by a background daemon thread and pushed onto a queue.
    """

    def __init__(self, session_id: str, name: str, cwd: Path) -> None:
        self.session_id = session_id
        self.name       = name
        self.cwd        = cwd
        self.created_at = time.monotonic()
        self.last_used  = time.monotonic()

        self._output_history: list[str] = []
        self._q: queue.Queue[str] = queue.Queue()
        self._lock = threading.Lock()
        self._alive = False

        self._proc: subprocess.Popen | None = None
        self._reader_thread: threading.Thread | None = None

        self._start()

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def _start(self) -> None:
        try:
            self._proc = subprocess.Popen(
                [_SHELL_BIN] + _SHELL_ARGS,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(self.cwd),
                text=True,
                bufsize=1,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            self._alive = True
            self._reader_thread = threading.Thread(
                target=self._read_loop,
                daemon=True,
                name=f"term-reader-{self.session_id[:8]}",
            )
            self._reader_thread.start()
            log.info("TerminalSession %s started (pid=%d)", self.session_id[:8], self._proc.pid)
        except Exception as exc:
            log.error("TerminalSession start failed: %s", exc)
            self._alive = False

    def _read_loop(self) -> None:
        """Daemon thread: continuously drains stdout into the queue."""
        assert self._proc and self._proc.stdout
        try:
            for line in self._proc.stdout:
                with self._lock:
                    self._output_history.append(line)
                self._q.put(line)
        except Exception as exc:
            log.debug("TerminalSession reader exited: %s", exc)
        finally:
            self._alive = False
            self._q.put(None)  # sentinel

    def is_alive(self) -> bool:
        if not self._alive:
            return False
        if self._proc and self._proc.poll() is not None:
            self._alive = False
        return self._alive

    def kill(self) -> None:
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except Exception:
                try:
                    self._proc.kill()
                except Exception as exc:
                    log.debug("[services.terminal_manager] suppressed exception", exc_info=exc)
                    pass
        self._alive = False
        log.info("TerminalSession %s killed", self.session_id[:8])

    # ── Command execution ──────────────────────────────────────────────────────

    def send_command(self, command: str, timeout: float = READ_TIMEOUT) -> str:
        """
        Write a command to stdin and collect output until quiet.

        Returns captured output (stripped, max MAX_OUTPUT_BYTES).
        """
        if not self.is_alive():
            return "❌ Session is not alive."

        # Drain any leftover output
        self._drain_queue()

        # Add a sentinel echo so we know when the command output ends
        sentinel = f"__JARVIS_DONE_{uuid.uuid4().hex[:8]}__"
        if os.name == "nt":
            full_cmd = f"{command}\necho {sentinel}\n"
        else:
            full_cmd = f"{command}\necho {sentinel}\n"

        try:
            assert self._proc and self._proc.stdin
            self._proc.stdin.write(full_cmd)
            self._proc.stdin.flush()
        except Exception as exc:
            return f"❌ Failed to write to terminal: {exc}"

        self.last_used = time.monotonic()

        # Collect output until sentinel appears or timeout
        output_parts: list[str] = []
        deadline = time.monotonic() + timeout
        total_bytes = 0

        while time.monotonic() < deadline:
            try:
                line = self._q.get(timeout=POLL_INTERVAL)
                if line is None:
                    break  # process died
                if sentinel in line:
                    break  # command complete
                output_parts.append(line)
                total_bytes += len(line.encode())
                if total_bytes >= MAX_OUTPUT_BYTES:
                    output_parts.append("[output truncated]\n")
                    break
            except queue.Empty:
                # No output — check if process is still running
                if not self.is_alive():
                    break

        return "".join(output_parts).strip()

    def _drain_queue(self) -> None:
        """Clear any pending output from the queue."""
        while True:
            try:
                self._q.get_nowait()
            except queue.Empty:
                break

    def stream_command(self, command: str, timeout: float = READ_TIMEOUT) -> Iterator[str]:
        """Generator that yields lines as they arrive from a command."""
        if not self.is_alive():
            yield "❌ Session is not alive."
            return

        self._drain_queue()
        sentinel = f"__JARVIS_DONE_{uuid.uuid4().hex[:8]}__"
        full_cmd = f"{command}\necho {sentinel}\n"

        try:
            assert self._proc and self._proc.stdin
            self._proc.stdin.write(full_cmd)
            self._proc.stdin.flush()
        except Exception as exc:
            yield f"❌ Write failed: {exc}"
            return

        self.last_used = time.monotonic()
        deadline = time.monotonic() + timeout
        total_bytes = 0

        while time.monotonic() < deadline:
            try:
                line = self._q.get(timeout=POLL_INTERVAL)
                if line is None:
                    break
                if sentinel in line:
                    break
                yield line
                total_bytes += len(line.encode())
                if total_bytes >= MAX_OUTPUT_BYTES:
                    yield "[output truncated]\n"
                    break
            except queue.Empty:
                if not self.is_alive():
                    break

    def get_history(self, last_n: int = 100) -> str:
        with self._lock:
            return "".join(self._output_history[-last_n:])

    def info(self) -> SessionInfo:
        return SessionInfo(
            session_id=self.session_id,
            name=self.name,
            cwd=str(self.cwd),
            created_at=self.created_at,
            last_used=self.last_used,
            alive=self.is_alive(),
            output_lines=len(self._output_history),
        )


# ── TerminalManager ────────────────────────────────────────────────────────────

class TerminalManager:
    """
    Registry of all active terminal sessions.

    Thread-safe. Background reaper removes idle/dead sessions.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, TerminalSession] = {}
        self._lock = threading.Lock()
        self._start_reaper()

    # ── Session lifecycle ──────────────────────────────────────────────────────

    def create_session(self, name: str, cwd: str | None = None) -> str:
        """
        Create a new persistent terminal session.

        Args:
            name: Human-readable label (e.g. project name).
            cwd:  Working directory (must be inside WORKSPACE_DIR).

        Returns:
            session_id (UUID string)
        """
        session_id = str(uuid.uuid4())

        # Validate/resolve cwd
        if cwd:
            resolved = Path(cwd).resolve()
            # Ensure within workspace
            try:
                resolved.relative_to(WORKSPACE_DIR)
            except ValueError:
                resolved = WORKSPACE_DIR
        else:
            resolved = WORKSPACE_DIR

        resolved.mkdir(parents=True, exist_ok=True)

        session = TerminalSession(session_id=session_id, name=name, cwd=resolved)

        with self._lock:
            self._sessions[session_id] = session

        log.info("Created terminal session %s (name=%r cwd=%s)", session_id[:8], name, resolved)
        return session_id

    def get_session(self, session_id: str) -> TerminalSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def kill_session(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session:
            session.kill()
            return True
        return False

    def list_sessions(self) -> list[SessionInfo]:
        with self._lock:
            sessions = list(self._sessions.values())
        return [s.info() for s in sessions]

    # ── Command execution ──────────────────────────────────────────────────────

    def send_command(
        self,
        session_id: str,
        command: str,
        timeout: float = READ_TIMEOUT,
    ) -> str:
        """
        Send a command to a session and return its output.

        Validates the command through the shell whitelist first.
        """
        # Security: validate via shell_exec whitelist
        validation = self._validate_command(command)
        if not validation["ok"]:
            return f"❌ Blocked: {validation['reason']}"

        session = self.get_session(session_id)
        if not session:
            return f"❌ No session with id {session_id!r}. Call create_session() first."

        return session.send_command(command, timeout=timeout)

    def stream_command(
        self,
        session_id: str,
        command: str,
        timeout: float = READ_TIMEOUT,
    ) -> Iterator[str]:
        """Stream command output line by line."""
        validation = self._validate_command(command)
        if not validation["ok"]:
            yield f"❌ Blocked: {validation['reason']}"
            return

        session = self.get_session(session_id)
        if not session:
            yield f"❌ No session {session_id!r}"
            return

        yield from session.stream_command(command, timeout=timeout)

    def get_history(self, session_id: str, last_n: int = 100) -> str:
        session = self.get_session(session_id)
        if not session:
            return f"❌ No session {session_id!r}"
        return session.get_history(last_n=last_n)

    # ── Convenience: run in temp session ──────────────────────────────────────

    def run_once(self, command: str, cwd: str | None = None, timeout: float = 30.0) -> str:
        """
        Create a temp session, run one command, kill session, return output.
        Convenience wrapper for one-shot execution.
        """
        sid = self.create_session("__tmp__", cwd=cwd)
        try:
            output = self.send_command(sid, command, timeout=timeout)
        finally:
            self.kill_session(sid)
        return output

    # ── Private ────────────────────────────────────────────────────────────────

    @staticmethod
    def _validate_command(command: str) -> dict:
        """Validate command against shell_exec whitelist and blocked patterns."""
        import re
        from actions.shell_exec import ALLOWED_COMMANDS, _BLOCKED_PATTERNS

        stripped = command.strip()
        if not stripped:
            return {"ok": False, "reason": "empty command"}

        # Check blocked patterns first
        for pattern in _BLOCKED_PATTERNS:
            if pattern.search(stripped):
                return {"ok": False, "reason": f"blocked pattern: {pattern.pattern}"}

        # Extract base command
        base = re.split(r"[\s|;&]", stripped)[0].lower()
        base_name = Path(base).name  # handle paths like /usr/bin/python

        if base_name not in ALLOWED_COMMANDS:
            return {"ok": False, "reason": f"'{base_name}' not in allowed commands whitelist"}

        return {"ok": True, "reason": ""}

    def _start_reaper(self) -> None:
        """Background thread that removes dead/idle sessions."""
        def reap():
            while True:
                time.sleep(30)
                now = time.monotonic()
                to_kill: list[str] = []
                with self._lock:
                    for sid, sess in list(self._sessions.items()):
                        idle_secs = now - sess.last_used
                        age_secs  = now - sess.created_at
                        if not sess.is_alive():
                            to_kill.append(sid)
                        elif idle_secs > IDLE_TIMEOUT:
                            to_kill.append(sid)
                        elif age_secs > MAX_SESSION_AGE:
                            to_kill.append(sid)

                for sid in to_kill:
                    self.kill_session(sid)
                    log.info("Reaped terminal session %s", sid[:8])

        t = threading.Thread(target=reap, daemon=True, name="terminal-reaper")
        t.start()


# ── Singleton ──────────────────────────────────────────────────────────────────

_manager: TerminalManager | None = None


def get_terminal_manager() -> TerminalManager:
    """Return the global TerminalManager singleton."""
    global _manager
    if _manager is None:
        _manager = TerminalManager()
    return _manager
