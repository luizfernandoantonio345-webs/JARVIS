"""
file_editor action — precise edits via exact string replacement.

Security:
  - Read-only preview first
  - Exact match required (no regex)
  - Preserves indentation
  - Backup + diff shown

Input: \"edit path/to/file.py REPLACE_THIS with NEW_TEXT\"
"""

from __future__ import annotations

import difflib
import logging
from pathlib import Path

from .file_reader import ALLOWED_BASE_DIR, _safe_resolve, MAX_FILE_BYTES

log = logging.getLogger(__name__)

ACTION_NAME = "file_editor"

SYSTEM_PROMPT = (
    "You are a precise file editor. "
    "Propose exact string replacements (old -> new). "
    "Use diff preview. Confirm before applying."
)

def execute(input_str: str) -> str:
    if ' with ' not in input_str:
        return '❌ Usage: "edit path/to/file.py OLD_STRING with NEW_STRING"'

    # Parse: path after 'edit', then old/new split by ' with '
    parts = input_str.split(' with ', 1)
    if len(parts) != 2:
        return '❌ Missing "with" separator'

    path_part_old = parts[0].split(' ', 1)[1] if ' ' in parts[0] else parts[0]
    # path_part_old = "path/to/file.py OLD_STRING" — split into path and old_str
    path_str, old_str = (path_part_old.split(' ', 1) if ' ' in path_part_old
                         else (path_part_old, ""))
    new_str = parts[1].strip()

    if not old_str:
        return '❌ Missing OLD_STRING to replace'

    resolved = _safe_resolve(path_str)
    if isinstance(resolved, str):
        return resolved
    path = Path(resolved)

    if not path.exists():
        return f"❌ File not found: {path}"

    try:
        content = path.read_text(encoding='utf-8')
        if len(content) > MAX_FILE_BYTES:
            return f"❌ File too large"

        if old_str not in content:
            return f"❌ '{old_str}' not found in file (exact match required)"

        # Diff preview
        lines_old = content.splitlines(keepends=True)
        lines_new = content.replace(old_str, new_str, 1).splitlines(keepends=True)
        diff = ''.join(difflib.unified_diff(lines_old, lines_new, lineterm=''))

        return (
            f"**Preview Edit** `{path.relative_to(ALLOWED_BASE_DIR)}`\\n"
            f"Replace: `{old_str}` → `{new_str}` (1 occurrence)\\n\\n"
            f"```{diff}```\n\n"
            f"Safe to apply? Use file_writer if needed."
        )
    except Exception as exc:
        return f"❌ Edit preview failed: {exc}"

