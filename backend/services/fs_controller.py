"""
FSController — safe filesystem operations for JARVIS.

Security model:
  - All operations restricted to WORKSPACE_DIR
  - Path traversal ("../") fully blocked via resolve() + is_relative_to()
  - Max file size: 1 MB read / write
  - Auto-backup on overwrite (.bak)
  - No symlink escape
  - No execution of any file

Usage:
    from services.fs_controller import FSController
    fs = FSController()
    result = fs.read_file("main.py")
"""

from __future__ import annotations

import logging
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────

_DEFAULT_WORKSPACE = Path.home() / "jarvis_workspace"
WORKSPACE_DIR: Path = Path(
    os.getenv("JARVIS_WORKSPACE", str(_DEFAULT_WORKSPACE))
).resolve()

MAX_FILE_BYTES = 1 * 1024 * 1024  # 1 MB

_BLOCKED_EXTENSIONS = frozenset({
    ".exe", ".dll", ".so", ".dylib", ".bin", ".com",
    ".bat", ".cmd", ".ps1",
    ".pyc", ".pyo", ".class",
})


# ── Result type ────────────────────────────────────────────────────────────────

@dataclass
class FSResult:
    success: bool
    data: str | list | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {"success": self.success, "data": self.data, "error": self.error}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ensure_workspace() -> None:
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)


def _safe_path(raw: str) -> Path | FSResult:
    """Resolve path safely within WORKSPACE_DIR. Returns Path or FSResult error."""
    _ensure_workspace()
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = WORKSPACE_DIR / candidate
    try:
        resolved = candidate.resolve()
    except OSError as exc:
        return FSResult(success=False, error=f"Cannot resolve path: {exc}")

    try:
        resolved.relative_to(WORKSPACE_DIR)
    except ValueError:
        return FSResult(
            success=False,
            error=f"Access denied: '{raw}' is outside workspace ({WORKSPACE_DIR})",
        )

    if resolved.suffix.lower() in _BLOCKED_EXTENSIONS:
        return FSResult(
            success=False,
            error=f"File type '{resolved.suffix}' is not allowed.",
        )

    return resolved


# ── FSController ───────────────────────────────────────────────────────────────

class FSController:
    """
    Provides safe file-system operations restricted to WORKSPACE_DIR.
    All methods return FSResult — they never raise.
    """

    # ── Read ───────────────────────────────────────────────────────────────────

    def read_file(self, path: str) -> FSResult:
        """Read and return file contents (up to MAX_FILE_BYTES)."""
        resolved = _safe_path(path)
        if isinstance(resolved, FSResult):
            return resolved

        if not resolved.exists():
            return FSResult(success=False, error=f"File not found: {resolved.name}")
        if not resolved.is_file():
            return FSResult(success=False, error=f"Not a file: {resolved.name}")

        size = resolved.stat().st_size
        if size > MAX_FILE_BYTES:
            return FSResult(
                success=False,
                error=f"File too large ({size} bytes > {MAX_FILE_BYTES} limit)",
            )

        try:
            text = resolved.read_text(encoding="utf-8", errors="replace")
            log.info("FSController.read_file: %s (%d bytes)", resolved, len(text))
            return FSResult(success=True, data=text)
        except OSError as exc:
            return FSResult(success=False, error=str(exc))

    # ── Write ──────────────────────────────────────────────────────────────────

    def write_file(self, path: str, content: str) -> FSResult:
        """Overwrite or create a file. Auto-backs up existing file as .bak."""
        resolved = _safe_path(path)
        if isinstance(resolved, FSResult):
            return resolved

        if len(content.encode("utf-8")) > MAX_FILE_BYTES:
            return FSResult(
                success=False,
                error=f"Content too large (>{MAX_FILE_BYTES} bytes)",
            )

        resolved.parent.mkdir(parents=True, exist_ok=True)

        # Auto backup
        if resolved.exists():
            bak = resolved.with_suffix(resolved.suffix + ".bak")
            try:
                shutil.copy2(resolved, bak)
                log.info("FSController: backed up %s → %s", resolved.name, bak.name)
            except OSError as exc:
                log.warning("FSController: backup failed: %s", exc)

        try:
            resolved.write_text(content, encoding="utf-8")
            log.info("FSController.write_file: %s (%d chars)", resolved, len(content))
            return FSResult(success=True, data=f"Written: {resolved}")
        except OSError as exc:
            return FSResult(success=False, error=str(exc))

    # ── Append ─────────────────────────────────────────────────────────────────

    def append_file(self, path: str, content: str) -> FSResult:
        """Append content to a file (creates if not exists)."""
        resolved = _safe_path(path)
        if isinstance(resolved, FSResult):
            return resolved

        resolved.parent.mkdir(parents=True, exist_ok=True)

        # Check combined size
        existing_size = resolved.stat().st_size if resolved.exists() else 0
        new_size = existing_size + len(content.encode("utf-8"))
        if new_size > MAX_FILE_BYTES:
            return FSResult(
                success=False,
                error=f"Resulting file would exceed {MAX_FILE_BYTES} bytes",
            )

        try:
            with resolved.open("a", encoding="utf-8") as fh:
                fh.write(content)
            log.info("FSController.append_file: %s (+%d chars)", resolved, len(content))
            return FSResult(success=True, data=f"Appended to: {resolved}")
        except OSError as exc:
            return FSResult(success=False, error=str(exc))

    # ── List dir ───────────────────────────────────────────────────────────────

    def list_dir(self, path: str = ".") -> FSResult:
        """List directory contents (names only, not recursive)."""
        resolved = _safe_path(path)
        if isinstance(resolved, FSResult):
            return resolved

        if not resolved.exists():
            return FSResult(success=False, error=f"Directory not found: {path}")
        if not resolved.is_dir():
            return FSResult(success=False, error=f"Not a directory: {path}")

        try:
            entries = []
            for item in sorted(resolved.iterdir()):
                tag = "📁 " if item.is_dir() else "📄 "
                entries.append(tag + item.name)
            return FSResult(success=True, data=entries)
        except OSError as exc:
            return FSResult(success=False, error=str(exc))

    # ── Delete ─────────────────────────────────────────────────────────────────

    def delete_file(self, path: str) -> FSResult:
        """Delete a file. Directories are NOT deleted for safety."""
        resolved = _safe_path(path)
        if isinstance(resolved, FSResult):
            return resolved

        if not resolved.exists():
            return FSResult(success=False, error=f"File not found: {resolved.name}")
        if not resolved.is_file():
            return FSResult(
                success=False,
                error="Only files can be deleted. Use shell for directories.",
            )

        # Keep backup before delete
        bak = resolved.with_suffix(resolved.suffix + f".deleted_{int(time.time())}")
        try:
            shutil.copy2(resolved, bak)
        except OSError:
            pass  # best-effort backup

        try:
            resolved.unlink()
            log.info("FSController.delete_file: %s", resolved)
            return FSResult(success=True, data=f"Deleted: {resolved.name}")
        except OSError as exc:
            return FSResult(success=False, error=str(exc))

    # ── Make dir ───────────────────────────────────────────────────────────────

    def make_dir(self, path: str) -> FSResult:
        """Create a directory (and parents) inside workspace."""
        resolved = _safe_path(path)
        if isinstance(resolved, FSResult):
            return resolved

        try:
            resolved.mkdir(parents=True, exist_ok=True)
            return FSResult(success=True, data=f"Created dir: {resolved}")
        except OSError as exc:
            return FSResult(success=False, error=str(exc))


# ── Singleton ──────────────────────────────────────────────────────────────────

_fs = FSController()


def get_fs() -> FSController:
    """Return the global FSController singleton."""
    return _fs
