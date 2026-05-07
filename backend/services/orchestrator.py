"""
Orchestrator — central brain of JARVIS.

Receives a user intent, determines the execution mode, and dispatches to
the correct subsystem:

  Mode        → Subsystem
  ──────────────────────────────────────────────────
  chat        → LLM router + planner + executor
  dev         → DevAgent (single-agent code task)
  auto_dev    → AutoDev (autonomous build loop)
  security    → SecurityAgent + SecurityEngine
  automation  → AgentManager (multi-agent pipeline)
  task        → TaskManager (goal decomposition)
  shell       → ShellExec (controlled command)
  fs          → FSController (file operations)
  vscode      → VSCodeControl (editor interaction)

All actions pass through SecurityGuard before execution.
Max 5 steps enforced at every level.

Usage:
    from services.orchestrator import get_orchestrator
    orch = get_orchestrator()
    result = orch.dispatch(intent="dev", message="write a FastAPI app", session_id="abc")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from services.security_guard import get_guard

log = logging.getLogger(__name__)


# ── Execution modes ────────────────────────────────────────────────────────────

class Mode(str, Enum):
    CHAT       = "chat"
    DEV        = "dev"
    AUTO_DEV   = "auto_dev"
    SECURITY   = "security"
    AUTOMATION = "automation"
    TASK       = "task"
    SHELL      = "shell"
    FS         = "fs"
    VSCODE     = "vscode"


# ── Result ─────────────────────────────────────────────────────────────────────

@dataclass
class OrchestratorResult:
    mode: str
    output: str
    success: bool
    steps: list[dict] | None = None
    error: str | None = None
    blocked: bool = False

    def to_dict(self) -> dict:
        return {
            "mode":    self.mode,
            "output":  self.output,
            "success": self.success,
            "steps":   self.steps,
            "error":   self.error,
            "blocked": self.blocked,
        }


# ── Mode detection ─────────────────────────────────────────────────────────────

_MODE_KEYWORDS: list[tuple[Mode, list[str]]] = [
    (Mode.AUTO_DEV,   ["build", "create a", "make a", "cria um", "desenvolva", "auto_dev", "/autodev"]),
    (Mode.SECURITY,   ["/security", "/scan", "scan for vuln", "security analysis", "owasp", "analise segurança"]),
    (Mode.AUTOMATION, ["/multi", "/agents", "/agent", "multi-agent", "use agents", "/plan"]),
    (Mode.SHELL,      ["/shell", "/exec", "/run ", "execute command"]),
    (Mode.FS,         ["/fs", "/file", "/read ", "/write ", "/list "]),
    (Mode.VSCODE,     ["/vscode", "/open ", "/create file", "/reveal"]),
    (Mode.DEV,        ["/dev", "/code", "/coder", "write code", "implement", "escreva o código"]),
    (Mode.TASK,       ["/task", "/goal", "autonomous task", "tarefa autônoma"]),
]


def detect_mode(message: str) -> Mode:
    """Detect execution mode from the message. Returns Mode enum."""
    lower = message.lower().strip()
    for mode, keywords in _MODE_KEYWORDS:
        for kw in keywords:
            if kw in lower:
                return mode
    return Mode.CHAT


# ── Orchestrator ───────────────────────────────────────────────────────────────

class Orchestrator:
    """
    Central dispatcher for all JARVIS execution modes.

    All calls are guarded by SecurityGuard before dispatch.
    """

    def dispatch(
        self,
        message: str,
        session_id: str = "default",
        mode: str | Mode | None = None,
        history: list[dict] | None = None,
        agent_mode: bool = False,
    ) -> OrchestratorResult:
        """
        Main entry point — receives intent + message, dispatches to subsystem.

        Args:
            message:    Raw user message.
            session_id: Session identifier for memory + logging.
            mode:       Override auto-detected mode.
            history:    Prior conversation turns.
            agent_mode: Force multi-agent pipeline if True.

        Returns:
            OrchestratorResult — always populated, never raises.
        """
        # ── Security pre-check ─────────────────────────────────────────────
        guard = get_guard()
        guard_result = guard.check("llm", message)
        if not guard_result.allowed:
            log.warning("Orchestrator: BLOCKED session=%s reason=%s", session_id, guard_result.reason)
            return OrchestratorResult(
                mode="blocked",
                output=f"🚫 Request blocked: {guard_result.reason}",
                success=False,
                blocked=True,
            )

        # ── Mode detection ─────────────────────────────────────────────────
        exec_mode: Mode = Mode(mode) if mode else detect_mode(message)
        if agent_mode:
            exec_mode = Mode.AUTOMATION

        log.info("Orchestrator: session=%s mode=%s msg=%r", session_id, exec_mode.value, message[:80])

        # ── Dispatch ───────────────────────────────────────────────────────
        try:
            if exec_mode == Mode.CHAT:
                return self._dispatch_chat(message, session_id, history)
            if exec_mode == Mode.DEV:
                return self._dispatch_dev(message, session_id, history)
            if exec_mode == Mode.AUTO_DEV:
                return self._dispatch_auto_dev(message, session_id, history)
            if exec_mode == Mode.SECURITY:
                return self._dispatch_security(message, session_id, history)
            if exec_mode == Mode.AUTOMATION:
                return self._dispatch_automation(message, session_id, history)
            if exec_mode == Mode.TASK:
                return self._dispatch_task(message, session_id)
            if exec_mode == Mode.SHELL:
                return self._dispatch_shell(message, guard)
            if exec_mode == Mode.FS:
                return self._dispatch_fs(message)
            if exec_mode == Mode.VSCODE:
                return self._dispatch_vscode(message)
            # Default: chat
            return self._dispatch_chat(message, session_id, history)

        except Exception as exc:
            log.exception("Orchestrator: unhandled error in mode=%s", exec_mode.value)
            return OrchestratorResult(
                mode=exec_mode.value,
                output=f"❌ Orchestrator error: {exc}",
                success=False,
                error=str(exc),
            )

    # ── Private dispatchers ────────────────────────────────────────────────────

    def _dispatch_chat(self, message: str, session_id: str, history: list[dict] | None) -> OrchestratorResult:
        """Standard chat via existing chat_service."""
        from services.chat_service import process_message
        response = process_message(message, session_id)
        return OrchestratorResult(mode="chat", output=response, success=True)

    def _dispatch_dev(self, message: str, session_id: str, history: list[dict] | None) -> OrchestratorResult:
        """Route to DevAgent for code tasks."""
        from services.agent_registry import get_agent
        agent = get_agent("dev")
        result = agent.run(message, history)
        return OrchestratorResult(mode="dev", output=result.response, success=True)

    def _dispatch_auto_dev(self, message: str, session_id: str, history: list[dict] | None) -> OrchestratorResult:
        """Autonomous development loop."""
        from services.auto_dev import get_auto_dev
        auto = get_auto_dev()
        result = auto.build(message, history=history)
        steps = [it.to_dict() for it in result.iterations]
        return OrchestratorResult(
            mode="auto_dev",
            output=result.to_text(),
            success=result.success,
            steps=steps,
            error=result.error,
        )

    def _dispatch_security(self, message: str, session_id: str, history: list[dict] | None) -> OrchestratorResult:
        """Security analysis via SecurityAgent."""
        from services.agent_registry import get_agent
        agent = get_agent("security")
        result = agent.run(message, history)
        return OrchestratorResult(mode="security", output=result.response, success=True)

    def _dispatch_automation(self, message: str, session_id: str, history: list[dict] | None) -> OrchestratorResult:
        """Multi-agent pipeline via AgentManager."""
        from services.agent_manager import get_manager
        manager = get_manager()
        result = manager.run(goal=message, history=history, agent_mode=True)
        steps = [s.to_dict() for s in result.steps_executed]
        return OrchestratorResult(
            mode="automation",
            output=result.to_text(),
            success=result.success,
            steps=steps,
            error=result.error,
        )

    def _dispatch_task(self, message: str, session_id: str) -> OrchestratorResult:
        """Goal-based task decomposition via TaskManager."""
        from services.task_manager import create_task, run_task, build_task_report
        task = create_task(session_id, message)
        task = run_task(task.id)
        report = build_task_report(task)
        return OrchestratorResult(
            mode="task",
            output=report,
            success=task.state.value == "completed",
        )

    def _dispatch_shell(self, message: str, guard) -> OrchestratorResult:
        """Safe shell execution with guard pre-check."""
        # Strip command prefix if present
        cmd = message.strip()
        for prefix in ("/shell ", "/exec ", "/run "):
            if cmd.lower().startswith(prefix):
                cmd = cmd[len(prefix):]
                break

        shell_guard = guard.check("shell", cmd)
        if not shell_guard.allowed:
            return OrchestratorResult(
                mode="shell",
                output=f"🚫 Shell blocked: {shell_guard.reason}",
                success=False,
                blocked=True,
            )

        from actions.shell_exec import run_process
        proc = run_process(cmd)
        return OrchestratorResult(
            mode="shell",
            output=proc.to_text(),
            success=proc.success,
        )

    def _dispatch_fs(self, message: str) -> OrchestratorResult:
        """File system operations."""
        from actions.vscode_control import execute as vs_execute
        # Strip /fs prefix
        cmd = message.strip()
        if cmd.lower().startswith("/fs "):
            cmd = cmd[4:]
        elif cmd.lower().startswith("/file "):
            cmd = cmd[6:]

        from services.fs_controller import get_fs
        fs = get_fs()
        parts = cmd.strip().split(maxsplit=2)
        if not parts:
            return OrchestratorResult(mode="fs", output="❌ No fs command", success=False)

        op = parts[0].lower()
        path = parts[1] if len(parts) > 1 else ""
        content = parts[2] if len(parts) > 2 else ""

        if op == "read":
            r = fs.read_file(path)
        elif op == "write":
            r = fs.write_file(path, content)
        elif op in ("list", "ls"):
            r = fs.list_dir(path or ".")
        elif op == "delete":
            r = fs.delete_file(path)
        elif op == "mkdir":
            r = fs.make_dir(path)
        else:
            return OrchestratorResult(mode="fs", output=f"❌ Unknown fs op: {op}", success=False)

        if r.success:
            data = r.data
            out = "\n".join(data) if isinstance(data, list) else str(data)
            return OrchestratorResult(mode="fs", output=out, success=True)
        return OrchestratorResult(mode="fs", output=f"❌ {r.error}", success=False, error=r.error)

    def _dispatch_vscode(self, message: str) -> OrchestratorResult:
        """VS Code editor control."""
        from actions.vscode_control import execute as vscode_exec
        cmd = message.strip()
        for prefix in ("/vscode ", "/open "):
            if cmd.lower().startswith(prefix):
                cmd = cmd[len(prefix):]
                break
        output = vscode_exec(cmd)
        return OrchestratorResult(
            mode="vscode",
            output=output,
            success=not output.startswith("❌"),
        )


# ── Singleton ──────────────────────────────────────────────────────────────────

_orchestrator: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    """Return the global Orchestrator singleton."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator
