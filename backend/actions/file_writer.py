"""
file_writer action — securely writes/creates files in the allowed workspace.

Security:
  - Same ALLOWED_BASE_DIR as file_reader
  - Validates content (no shell escapes, size cap)
  - Auto-backup existing files (.bak)
  - Modes: 'w' (overwrite), 'a' (append), 'x' (create only)

Input: \"write path/to/file.py CONTENT\" or \"create dir/new.py CONTENT\"
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from .file_reader import ALLOWED_BASE_DIR, MAX_FILE_BYTES, _safe_resolve  # Reuse reader security

log = logging.getLogger(__name__)

ACTION_NAME = "file_writer"

SYSTEM_PROMPT = (
    "You are a secure file writer assistant. "
    "Confirm the write operation details and any warnings before proceeding. "
    "NEVER write executable code or shell commands."
)

_BLOCKED_PATTERNS = [
    r"(\b(?:rm|del|mv|cp|chmod|sudo|pip|apt|brew)\b.*)",
    r"(exec|system|os\.(system|pop))[\s\(]",
    r"import\s+(subprocess|os\.popen)",
]

def preprocess(content: str) -> str:
    return content

def _content_safe(content: str) -> tuple[bool, str]:
    """Check content against security patterns and size."""
    if len(content) > MAX_FILE_BYTES:
        return False, f"Content too large ({len(content)} > {MAX_FILE_BYTES} bytes)"
    for pattern in _BLOCKED_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE | re.MULTILINE):
            return False, f"Blocked dangerous pattern: {pattern}"
    return True, ""

def _parse_input(input_str: str) -> tuple[str | None, str, str]:
    """Parse 'mode path CONTENT' or default to 'w'."""
    parts = input_str.strip().split(maxsplit=2)
    if len(parts) < 2:
        return None, "", ""
    
    mode = parts[0].lower() if parts[0] in ('w', 'a', 'x') else 'w'
    path_part = parts[0] if mode == 'w' else parts[1]
    content = parts[-1] if len(parts) > 2 else ""
    
    return mode, path_part, content

def execute(input_str: str) -> str:
    mode, raw_path, content = _parse_input(input_str)
    if not raw_path or not content:
        return "❌ Usage: 'write path/to/file.txt CONTENT' or 'append path.txt CONTENT'"

    resolved = _safe_resolve(raw_path)
    if isinstance(resolved, str):
        return resolved
    path = Path(resolved)

    # Dir must exist
    path.parent.mkdir(parents=True, exist_ok=True)

    is_safe, safe_msg = _content_safe(content)
    if not is_safe:
        return f"❌ Write rejected: {safe_msg}"

    try:
        if mode == 'x' and path.exists():
            return f"❌ File exists (exclusive mode): {path}"
        
        # Backup existing
        if path.exists():
            backup = path.with_suffix(path.suffix + '.bak')
            path.rename(backup)
            backup_msg = f"Backed up to {backup.relative_to(ALLOWED_BASE_DIR)}"
        else:
            backup_msg = "New file created"

        # Write
        path.write_text(content, encoding='utf-8')
        
        return (
            f"✅ Wrote {len(content)} bytes to `{path.relative_to(ALLOWED_BASE_DIR)}`\\n"
            f"{backup_msg}\\n\\nPreview:\\n```\\n{content[:200]}...\\n```"
        )
    except Exception as exc:
        return f"❌ Write failed: {exc}"


