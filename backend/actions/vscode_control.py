"""
vscode_control action — interact with VS Code via CLI and file-based fallback.

Capabilities:
  - open_file(path)         → code <path>
  - focus_project(dir)      → code <dir>
  - create_file(path, text) → write file then open it
  - reveal_in_explorer(path)→ code --reveal <path> (if supported)

Security:
  - Paths restricted to WORKSPACE_DIR
  - No arbitrary command injection
  - CLI args always passed as list (no shell=True with user data)

Input format (natural language routing):
  "open main.py"
  "create utils/helpers.py with content ..."
  "focus project /path/to/dir"
  "reveal backend/main.py"
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from services.fs_controller import get_fs, WORKSPACE_DIR, _safe_path, FSResult

log = logging.getLogger(__name__)

ACTION_NAME = "vscode_control"
SYSTEM_PROMPT = (
    "You are a VS Code integration assistant. "
    "Help users open, create, and navigate files in their editor."
)

# ── Helpers ────────────────────────────────────────────────────────────────────

def _code_available() -> bool:
    return shutil.which("code") is not None


def _run_code(*args: str) -> tuple[bool, str]:
    """Run `code <args>` safely without shell=True."""
    if not _code_available():
        return False, "VS Code CLI ('code') not found in PATH."
    try:
        result = subprocess.run(
            ["code"] + list(args),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return True, result.stdout.strip() or "OK"
        return False, result.stderr.strip() or f"Exit code {result.returncode}"
    except subprocess.TimeoutExpired:
        return False, "VS Code CLI timed out."
    except OSError as exc:
        return False, str(exc)


# ── Operations ─────────────────────────────────────────────────────────────────

def open_file(path: str) -> str:
    """Open a file in VS Code."""
    resolved = _safe_path(path)
    if isinstance(resolved, FSResult):
        return f"❌ {resolved.error}"

    if not resolved.exists():
        return f"❌ File not found: {path}"

    ok, msg = _run_code(str(resolved))
    if ok:
        return f"✅ Opened in VS Code: {resolved.name}"
    # fallback: at least confirm the file exists
    return f"⚠️ VS Code CLI unavailable. File exists at: {resolved}"


def focus_project(directory: str) -> str:
    """Open a directory/project in VS Code."""
    resolved = _safe_path(directory)
    if isinstance(resolved, FSResult):
        return f"❌ {resolved.error}"

    if not resolved.is_dir():
        return f"❌ Not a directory: {directory}"

    ok, msg = _run_code(str(resolved))
    if ok:
        return f"✅ Opened project in VS Code: {resolved}"
    return f"⚠️ VS Code CLI unavailable. Project path: {resolved}"


def create_file(path: str, content: str = "") -> str:
    """Create a new file and open it in VS Code."""
    fs = get_fs()
    result = fs.write_file(path, content)
    if not result.success:
        return f"❌ {result.error}"

    resolved = _safe_path(path)
    if not isinstance(resolved, FSResult):
        _run_code(str(resolved))  # best-effort open

    return f"✅ Created: {path}" + (" and opened in VS Code." if _code_available() else ".")


def reveal_in_explorer(path: str) -> str:
    """Reveal a file/folder in VS Code Explorer sidebar."""
    resolved = _safe_path(path)
    if isinstance(resolved, FSResult):
        return f"❌ {resolved.error}"

    # --reveal flag may not be available on all VS Code versions
    ok, msg = _run_code("--reveal", str(resolved))
    if ok:
        return f"✅ Revealed in explorer: {resolved.name}"
    # Fallback: just open
    ok2, _ = _run_code(str(resolved))
    return f"✅ Opened: {resolved.name}" if ok2 else f"⚠️ {msg}"


# ── Action entry point ─────────────────────────────────────────────────────────

def execute(input_str: str) -> str:
    """
    Route natural-language commands to VS Code operations.

    Patterns:
      open <path>
      focus <dir>
      create <path> [content ...]
      reveal <path>
    """
    text = input_str.strip()
    lower = text.lower()

    if lower.startswith("open "):
        return open_file(text[5:].strip())

    if lower.startswith("focus "):
        return focus_project(text[6:].strip())

    if lower.startswith("reveal "):
        return reveal_in_explorer(text[7:].strip())

    if lower.startswith("create "):
        rest = text[7:].strip()
        # Expect: "path/to/file.py [optional content]"
        parts = rest.split(maxsplit=1)
        path = parts[0]
        content = parts[1] if len(parts) > 1 else ""
        return create_file(path, content)

    # Default: try to open as path
    if text:
        return open_file(text)

    return "❌ No command provided. Use: open/focus/create/reveal <path>"
