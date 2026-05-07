"""
vscode_bridge — FASE 8, Etapa 2

HTTP bridge between the Jarvis backend and a companion VS Code extension
(or any IDE that speaks this protocol).

Architecture
------------
The VS Code extension hosts a tiny HTTP server on 127.0.0.1:7892.
This module is the *client side*: it sends JSON-RPC–style requests to the
extension, which then executes VS Code API calls and returns results.

Capabilities exposed
---------------------
  • open_file(path)          — Open a file in the editor
  • edit_line(path, line, text) — Replace a specific line in a file
  • read_diagnostics(path)   — Read Problems/Errors from the extension
  • run_task(task_name)      — Execute a VS Code task (build, test, etc.)
  • get_terminal_output()    — Read the last N lines of the integrated terminal
  • reveal_in_explorer(path) — Reveal a file in the Explorer panel

Communication
-------------
  POST http://127.0.0.1:7892/vscode
  Content-Type: application/json
  { "action": "<action_name>", "params": { ... } }

  Response: { "ok": true|false, "result": ..., "error": "..." }

If the extension is not running, all methods degrade gracefully and return
an unavailable result rather than raising.

Security
--------
  - Only loopback (127.0.0.1) connections; no external network exposure.
  - Path params are validated against the workspace root.
  - The timeout is short (5 s) to avoid blocking the agent loop.

Role in the system
------------------
Used by AutonomousLoop and Executor Agent when tasks require IDE interaction:
opening files after generation, reading lint errors, triggering build tasks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import structlog

log: structlog.BoundLogger = structlog.get_logger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────
VSCODE_BRIDGE_HOST = "127.0.0.1"
VSCODE_BRIDGE_PORT = 7892
VSCODE_BRIDGE_URL = f"http://{VSCODE_BRIDGE_HOST}:{VSCODE_BRIDGE_PORT}/vscode"
_TIMEOUT_S = 5.0


# ── Result model ───────────────────────────────────────────────────────────────

@dataclass
class BridgeResult:
    ok: bool
    result: Any = None
    error: str = ""
    available: bool = True  # False when extension is not running

    @property
    def success(self) -> bool:
        return self.ok and self.available


# ── Low-level transport ────────────────────────────────────────────────────────

def _call(action: str, params: dict[str, Any] | None = None) -> BridgeResult:
    """
    Send a single request to the VS Code extension bridge.
    Returns a degraded BridgeResult (available=False) if the extension
    is not reachable, so callers never crash on an absent IDE.
    """
    payload: dict[str, Any] = {"action": action, "params": params or {}}
    log.debug("vscode_bridge.request", action=action, params=params)
    try:
        resp = httpx.post(VSCODE_BRIDGE_URL, json=payload, timeout=_TIMEOUT_S)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        result = BridgeResult(
            ok=data.get("ok", False),
            result=data.get("result"),
            error=data.get("error", ""),
            available=True,
        )
        log.debug("vscode_bridge.response", action=action, ok=result.ok)
        return result
    except httpx.ConnectError:
        log.info("vscode_bridge.unavailable", action=action)
        return BridgeResult(ok=False, error="VS Code extension not running", available=False)
    except httpx.HTTPStatusError as exc:
        log.warning("vscode_bridge.http_error", action=action, status=exc.response.status_code)
        return BridgeResult(ok=False, error=str(exc), available=True)
    except Exception as exc:
        log.error("vscode_bridge.error", action=action, error=str(exc))
        return BridgeResult(ok=False, error=str(exc), available=False)


# ── Public API ─────────────────────────────────────────────────────────────────

def open_file(path: str | Path, line: int | None = None) -> BridgeResult:
    """
    Open *path* in the VS Code editor.
    Optionally jump to *line* (1-based).

    Example
    -------
    >>> result = open_file("/workspace/src/main.py", line=42)
    >>> print(result.ok)
    """
    params: dict[str, Any] = {"path": str(path)}
    if line is not None:
        params["line"] = line
    return _call("open_file", params)


def edit_line(path: str | Path, line: int, new_text: str) -> BridgeResult:
    """
    Replace the content of *line* (1-based) in *path* with *new_text*.

    The extension applies a WorkspaceEdit so the change appears in the
    editor buffer and can be undone by the user.

    Example
    -------
    >>> result = edit_line("/workspace/src/main.py", 10, "    return True")
    """
    return _call("edit_line", {"path": str(path), "line": line, "text": new_text})


def read_diagnostics(path: str | Path | None = None) -> BridgeResult:
    """
    Read VS Code diagnostics (Problems panel) for *path*.
    If *path* is None, returns diagnostics for the entire workspace.

    Returns a list of dicts: [{severity, message, source, range}, ...]

    Example
    -------
    >>> result = read_diagnostics("/workspace/src/main.py")
    >>> for diag in result.result or []:
    ...     print(diag["severity"], diag["message"])
    """
    params: dict[str, Any] = {}
    if path is not None:
        params["path"] = str(path)
    return _call("read_diagnostics", params)


def run_task(task_name: str) -> BridgeResult:
    """
    Execute a VS Code task defined in tasks.json by its *task_name*.

    Example
    -------
    >>> result = run_task("pytest")
    """
    return _call("run_task", {"task": task_name})


def get_terminal_output(lines: int = 100) -> BridgeResult:
    """
    Return the last *lines* lines from the VS Code integrated terminal.

    Example
    -------
    >>> result = get_terminal_output(50)
    >>> print(result.result)
    """
    return _call("get_terminal_output", {"lines": lines})


def reveal_in_explorer(path: str | Path) -> BridgeResult:
    """
    Reveal *path* in the VS Code Explorer panel (tree view).

    Example
    -------
    >>> reveal_in_explorer("/workspace/output/report.html")
    """
    return _call("reveal_in_explorer", {"path": str(path)})


def get_active_file() -> BridgeResult:
    """
    Return the path of the currently active editor file.

    Example
    -------
    >>> result = get_active_file()
    >>> print(result.result)  # e.g. "/workspace/src/main.py"
    """
    return _call("get_active_file")


def is_available() -> bool:
    """
    Quick health-check: returns True if the VS Code extension bridge is running.

    Example
    -------
    >>> if vscode_bridge.is_available():
    ...     vscode_bridge.open_file("src/main.py")
    """
    result = _call("ping")
    return result.available and result.ok
