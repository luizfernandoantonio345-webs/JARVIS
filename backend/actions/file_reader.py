"""
file_reader action — safely reads local files within an allowed base directory.

Security controls:
  - Path traversal prevention (resolve + is_relative_to check)
  - Configurable ALLOWED_BASE_DIR (default: user home / jarvis_workspace)
  - Hard file size cap (MAX_FILE_BYTES)
  - Blocked extensions list (binaries, executables)
  - No symlink following outside the allowed tree

Defines execute(input) so the executor calls it directly.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

ACTION_NAME = "file_reader"

# ── Security config ────────────────────────────────────────────────────────────

# Override via env var: JARVIS_WORKSPACE=/path/to/dir
_DEFAULT_WORKSPACE = Path.home() / "jarvis_workspace"
ALLOWED_BASE_DIR   = Path(os.getenv("JARVIS_WORKSPACE", str(_DEFAULT_WORKSPACE))).resolve()

MAX_FILE_BYTES = 100_000  # 100 KB hard cap

_BLOCKED_EXTENSIONS = frozenset({
    ".exe", ".dll", ".so", ".dylib", ".bin", ".com",
    ".bat", ".cmd", ".sh", ".bash", ".ps1",
    ".pyc", ".pyo", ".class",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".ico",
    ".mp3", ".mp4", ".avi", ".mov",
    ".zip", ".tar", ".gz", ".rar", ".7z",
    ".db", ".sqlite", ".sqlite3",
})

SYSTEM_PROMPT = (
    "You are a file analysis assistant. You have been given the contents of a file. "
    "Answer the user's question based on this content. "
    "Quote relevant sections when helpful."
)


def preprocess(content: str) -> str:
    return content


# ── Security helpers ───────────────────────────────────────────────────────────

def _safe_resolve(raw_path: str) -> Path | str:
    """
    Resolve path relative to ALLOWED_BASE_DIR.
    Returns a safe Path or an error string.
    """
    # Ensure workspace exists
    ALLOWED_BASE_DIR.mkdir(parents=True, exist_ok=True)

    # Interpret relative paths as relative to workspace
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = ALLOWED_BASE_DIR / candidate

    try:
        resolved = candidate.resolve()
    except OSError as exc:
        return f"❌ Cannot resolve path: {exc}"

    # Reject symlinks that escape the allowed tree
    try:
        resolved.relative_to(ALLOWED_BASE_DIR)
    except ValueError:
        return f"❌ Access denied: path is outside the allowed workspace ({ALLOWED_BASE_DIR})"

    if resolved.suffix.lower() in _BLOCKED_EXTENSIONS:
        return f"❌ File type `{resolved.suffix}` is not allowed."

    return resolved


# ── Execution ──────────────────────────────────────────────────────────────────

def execute(input_str: str) -> str:
    """
    Read a file and return its contents (truncated if over the size cap).

    Input format (flexible):
      "path/to/file.py"
      "read path/to/file.py"
      "show contents of config.json"
    """
    # Extract file path — last quoted token or last whitespace-separated token
    import re
    quoted = re.search(r'["\']([^"\']+)["\']', input_str)
    if quoted:
        raw_path = quoted.group(1)
    else:
        # Take the last token that looks like a file path (contains . or /)
        tokens = input_str.strip().split()
        path_tokens = [t for t in tokens if ("." in t or "/" in t or "\\" in t)]
        raw_path = path_tokens[-1] if path_tokens else tokens[-1] if tokens else ""

    if not raw_path:
        return "❌ No file path found in the request."

    result = _safe_resolve(raw_path)
    if isinstance(result, str):  # error message
        return result
    resolved = result

    if not resolved.exists():
        return f"❌ File not found: `{resolved.name}` (looked in `{ALLOWED_BASE_DIR}`)"

    if not resolved.is_file():
        # List directory contents instead
        try:
            entries = sorted(resolved.iterdir(), key=lambda p: (p.is_file(), p.name))
            lines   = [f"📁 `{resolved.name}/`", ""]
            for e in entries[:50]:
                icon = "📄" if e.is_file() else "📁"
                lines.append(f"  {icon} {e.name}")
            if len(list(resolved.iterdir())) > 50:
                lines.append("  ... (truncated)")
            return "\n".join(lines)
        except PermissionError:
            return f"❌ Permission denied reading directory: `{resolved}`"

    file_size = resolved.stat().st_size
    if file_size > MAX_FILE_BYTES:
        return (
            f"❌ File too large ({file_size:,} bytes). "
            f"Maximum allowed: {MAX_FILE_BYTES:,} bytes."
        )

    try:
        content = resolved.read_text(encoding="utf-8", errors="replace")
    except PermissionError:
        return f"❌ Permission denied reading: `{resolved.name}`"
    except Exception as exc:
        return f"❌ Error reading file: {exc}"

    truncated = ""
    if len(content) > MAX_FILE_BYTES:
        content   = content[:MAX_FILE_BYTES]
        truncated = f"\n\n⚠️ *Content truncated at {MAX_FILE_BYTES:,} characters.*"

    lang = resolved.suffix.lstrip(".") or "text"
    return (
        f"**File:** `{resolved.relative_to(ALLOWED_BASE_DIR)}`  "
        f"({file_size:,} bytes)\n\n"
        f"```{lang}\n{content}\n```{truncated}"
    )
