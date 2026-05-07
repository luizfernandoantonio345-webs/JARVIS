"""
Shell tool — isolated, stateless.
Executes shell commands with security whitelist enforcement.
Delegates to existing shell_feedback module for full feedback loop.
"""
from __future__ import annotations

import asyncio
from typing import Any

from core.logger import log_execution, log_security

# Commands that are never allowed regardless of risk level
_NEVER_ALLOW = {
    "rm -rf /", "format", "mkfs", "dd if=", ":(){:|:&};:",
    "chmod -R 777 /", "sudo rm",
}


def _is_blocked(command: str) -> bool:
    cmd_lower = command.lower()
    return any(blocked in cmd_lower for blocked in _NEVER_ALLOW)


async def run_shell(parameters: dict[str, Any]) -> dict[str, Any]:
    command = parameters.get("command", "")
    if not command:
        raise ValueError("'command' parameter is required")

    if _is_blocked(command):
        log_security("blocked_shell_command", command=command[:200])
        raise PermissionError(f"Command blocked by security policy: {command[:100]}")

    log_execution("shell_run", command=command[:200])

    try:
        # Prefer the existing shell_feedback module for feedback-loop support
        from tools.shell_feedback import run_with_feedback  # type: ignore
        result = await asyncio.to_thread(run_with_feedback, command)
        return {
            "message": f"Exit code: {result.exit_code}",
            "output": result.output[:4096],
            "exit_code": result.exit_code,
        }
    except ImportError:
        # Fallback: plain asyncio subprocess
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode(errors="replace") + stderr.decode(errors="replace")
        return {
            "message": f"Exit code: {proc.returncode}",
            "output": output[:4096],
            "exit_code": proc.returncode,
        }
