"""
file_writer action — securely writes/creates/patches files in the allowed workspace.

Security:
  - Same ALLOWED_BASE_DIR as file_reader
  - Validates content (no shell escapes, size cap)
  - Auto-backup existing files (.bak)
  - Modes: 'write' (overwrite), 'append', 'patch' (apply unified diff)

Input format (PREFERRED — JSON structured):
  {
    "path": "relative/path/to/file.py",
    "mode": "write|append|patch",
    "content": "full file content or patch"
  }

Legacy format (deprecated but supported):
  "write path/to/file.py CONTENT" (breaks on multiline)

Modes:
  - write  → overwrite file completely, create if not exists
  - append → append content to end of file
  - patch  → apply unified diff (content is the patch text)

Returns:
  JSON with: {"success": bool, "message": str, "path": str}
"""

from __future__ import annotations

import json
import logging
import os
import re
from difflib import unified_diff
from pathlib import Path
from typing import Any

from .file_reader import ALLOWED_BASE_DIR, MAX_FILE_BYTES, _safe_resolve  # Reuse reader security

log = logging.getLogger(__name__)

ACTION_NAME = "file_writer"

SYSTEM_PROMPT = (
    "You are a secure file writer assistant. "
    "Use JSON format for all file writes. "
    "Always validate paths stay within project root. "
    "Confirm destructive operations (overwrite, patch) before proceeding. "
    "NEVER write executable code or shell commands."
)

# Dangerous patterns that must never be written
_BLOCKED_PATTERNS = [
    r"(\b(?:rm|del|mv|cp|chmod|sudo|pip|apt|brew|curl|wget)\b.*)",
    r"(exec|system|os\.(system|pop|popen))[\s\(]",
    r"import\s+(subprocess|os\.popen)",
    r"(__import__|eval|compile)[\s\(]",
]

# File extensions that should NEVER be written
_BLOCKED_EXTENSIONS = {".exe", ".dll", ".so", ".bin", ".sh", ".bat"}


def preprocess(content: str) -> str:
    """Preprocess input before parsing."""
    return content.strip()


def _content_safe(content: str) -> tuple[bool, str]:
    """Check content against security patterns and size."""
    if len(content) > MAX_FILE_BYTES:
        return False, f"Content too large ({len(content)} > {MAX_FILE_BYTES} bytes)"
    
    for pattern in _BLOCKED_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE | re.MULTILINE):
            msg = f"Blocked dangerous pattern: {pattern}"
            log.warning(f"_content_safe rejected: {msg}")
            return False, msg
    
    return True, ""


def _path_safe(path: Path) -> tuple[bool, str]:
    """Check path extensions and location."""
    if path.suffix.lower() in _BLOCKED_EXTENSIONS:
        return False, f"Blocked file type: {path.suffix}"
    return True, ""


def _parse_json_input(input_str: str) -> tuple[dict[str, Any] | None, str]:
    """Parse JSON input format.
    
    Returns: (parsed_dict, error_message)
    """
    try:
        data = json.loads(input_str)
        
        # Validate required fields
        if not isinstance(data, dict):
            return None, "Input must be JSON object"
        
        path_val = data.get("path")
        mode_val = data.get("mode", "write").lower()
        content_val = data.get("content", "")
        
        if not isinstance(path_val, str) or not path_val:
            return None, "Missing or invalid 'path' field"
        
        if mode_val not in ("write", "append", "patch"):
            return None, f"Invalid mode '{mode_val}'. Must be: write, append, patch"
        
        if not isinstance(content_val, str):
            return None, "Field 'content' must be string"
        
        return {"path": path_val, "mode": mode_val, "content": content_val}, ""
    except json.JSONDecodeError as e:
        return None, f"JSON parse error: {e}"


def _parse_legacy_input(input_str: str) -> tuple[dict[str, Any] | None, str]:
    """Parse legacy format: 'mode path CONTENT' (deprecated, fragile).
    
    Returns: (parsed_dict, error_message)
    """
    try:
        # Try to parse as JSON first
        data = json.loads(input_str)
        if isinstance(data, dict) and "path" in data:
            return data, ""
    except json.JSONDecodeError:
        pass
    
    # Fallback to legacy format
    parts = input_str.strip().split(None, 2)  # Split on first 2 whitespace
    if len(parts) < 2:
        return None, "Insufficient arguments. Use JSON format: {\"path\": \"...\", \"mode\": \"write\", \"content\": \"...\"}"
    
    mode_or_path = parts[0].lower()
    mode = "write"
    path_part = ""
    content = ""
    
    if mode_or_path in ("write", "append", "create", "a", "w"):
        mode = "append" if mode_or_path in ("append", "a") else "write"
        path_part = parts[1] if len(parts) > 1 else ""
        content = parts[2] if len(parts) > 2 else ""
    else:
        path_part = mode_or_path
        content = parts[1] if len(parts) > 1 else ""
    
    if not path_part:
        return None, "Path is required"
    
    return {"path": path_part, "mode": mode, "content": content}, ""


def _apply_patch(original: str, patch_text: str) -> tuple[str, str]:
    """Apply unified diff patch to original content.
    
    Returns: (patched_content, error_message)
    """
    try:
        # Parse patch lines
        patch_lines = patch_text.splitlines(keepends=True)
        original_lines = original.splitlines(keepends=True)
        
        # Try to apply using difflib-like logic
        result_lines = []
        orig_idx = 0
        
        for line in patch_lines:
            if line.startswith("@@"):
                # Parse hunk header: @@ -l,s +l,s @@
                # For now, just continue; this is simplified
                continue
            elif line.startswith("+") and not line.startswith("+++"):
                result_lines.append(line[1:])
            elif line.startswith("-") and not line.startswith("---"):
                if orig_idx < len(original_lines):
                    orig_idx += 1
            elif line.startswith(" "):
                if orig_idx < len(original_lines):
                    result_lines.append(original_lines[orig_idx])
                    orig_idx += 1
            # Skip --- and +++ lines
        
        return "".join(result_lines), ""
    except Exception as e:
        return "", f"Patch apply failed: {e}"


def execute(input_str: str) -> str:
    """Execute file write operation.
    
    Input: JSON structured or legacy format
    Output: JSON result {success, message, path}
    """
    log.info(f"{ACTION_NAME} called with input length: {len(input_str)}")
    
    # Try JSON parsing first
    parsed, json_error = _parse_json_input(input_str)
    
    # Fallback to legacy format if JSON parsing fails
    if parsed is None:
        parsed, legacy_error = _parse_legacy_input(input_str)
        if parsed is None:
            error_msg = json_error or legacy_error
            log.error(f"{ACTION_NAME} parse failed: {error_msg}")
            return json.dumps({
                "success": False,
                "message": f"Parse error: {error_msg}",
                "path": None
            })
    
    path_str = parsed["path"]
    mode = parsed["mode"]
    content = parsed["content"]
    
    log.info(f"{ACTION_NAME} mode={mode}, path={path_str}, content_len={len(content)}")
    
    # Resolve and validate path
    resolved = _safe_resolve(path_str)
    if isinstance(resolved, str):  # Error message returned
        log.error(f"{ACTION_NAME} path validation failed: {resolved}")
        return json.dumps({
            "success": False,
            "message": resolved,
            "path": path_str
        })
    
    path = Path(resolved)
    
    # Validate path safety (extension, location)
    is_safe, safe_msg = _path_safe(path)
    if not is_safe:
        log.error(f"{ACTION_NAME} path unsafe: {safe_msg}")
        return json.dumps({
            "success": False,
            "message": f"❌ {safe_msg}",
            "path": str(path)
        })
    
    # Validate content safety (only for write/append, not patch)
    if mode != "patch":
        is_safe, safe_msg = _content_safe(content)
        if not is_safe:
            log.error(f"{ACTION_NAME} content unsafe: {safe_msg}")
            return json.dumps({
                "success": False,
                "message": f"❌ Write rejected: {safe_msg}",
                "path": str(path)
            })
    
    try:
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        
        backup_info = ""
        
        # ─────────────────────────────────────────────────────────────
        # MODE: write — overwrite file
        # ─────────────────────────────────────────────────────────────
        if mode == "write":
            if path.exists():
                backup_path = path.with_suffix(path.suffix + ".bak")
                # Rotate old backups
                if backup_path.exists():
                    backup_path.unlink()
                path.rename(backup_path)
                backup_info = f"\nBacked up to: {backup_path.relative_to(ALLOWED_BASE_DIR)}"
            
            path.write_text(content, encoding="utf-8")
            
            result = {
                "success": True,
                "message": (
                    f"✅ Wrote {len(content)} bytes to `{path.relative_to(ALLOWED_BASE_DIR)}`"
                    + backup_info
                    + f"\n\nPreview:\n```\n{content[:300]}{'...' if len(content) > 300 else ''}\n```"
                ),
                "path": str(path.relative_to(ALLOWED_BASE_DIR))
            }
            log.info(f"{ACTION_NAME} write success: {path}")
            return json.dumps(result)
        
        # ─────────────────────────────────────────────────────────────
        # MODE: append — append to file
        # ─────────────────────────────────────────────────────────────
        elif mode == "append":
            if not path.exists():
                path.write_text(content, encoding="utf-8")
                msg = f"✅ Created and wrote {len(content)} bytes to `{path.relative_to(ALLOWED_BASE_DIR)}`"
            else:
                # Append to existing
                current = path.read_text(encoding="utf-8")
                new_content = current + content
                
                # Check size after append
                if len(new_content) > MAX_FILE_BYTES:
                    raise ValueError(f"File too large after append: {len(new_content)} bytes")
                
                path.write_text(new_content, encoding="utf-8")
                msg = f"✅ Appended {len(content)} bytes to `{path.relative_to(ALLOWED_BASE_DIR)}`"
            
            result = {"success": True, "message": msg, "path": str(path.relative_to(ALLOWED_BASE_DIR))}
            log.info(f"{ACTION_NAME} append success: {path}")
            return json.dumps(result)
        
        # ─────────────────────────────────────────────────────────────
        # MODE: patch — apply unified diff
        # ─────────────────────────────────────────────────────────────
        elif mode == "patch":
            if not path.exists():
                raise FileNotFoundError(f"Cannot patch non-existent file: {path}")
            
            original = path.read_text(encoding="utf-8")
            patched, patch_error = _apply_patch(original, content)
            
            if patch_error:
                raise ValueError(f"Patch failed: {patch_error}")
            
            # Validate patched content is safe
            is_safe, safe_msg = _content_safe(patched)
            if not is_safe:
                raise ValueError(f"Patched content unsafe: {safe_msg}")
            
            # Backup original
            backup_path = path.with_suffix(path.suffix + ".bak")
            if backup_path.exists():
                backup_path.unlink()
            path.rename(backup_path)
            
            path.write_text(patched, encoding="utf-8")
            
            result = {
                "success": True,
                "message": (
                    f"✅ Applied patch to `{path.relative_to(ALLOWED_BASE_DIR)}`\n"
                    f"Backed up to: {backup_path.relative_to(ALLOWED_BASE_DIR)}"
                ),
                "path": str(path.relative_to(ALLOWED_BASE_DIR))
            }
            log.info(f"{ACTION_NAME} patch success: {path}")
            return json.dumps(result)
        
        else:
            raise ValueError(f"Unknown mode: {mode}")
    
    except Exception as exc:
        log.error(f"{ACTION_NAME} execution failed: {exc}", exc_info=True)
        return json.dumps({
            "success": False,
            "message": f"❌ Operation failed: {exc}",
            "path": str(path) if 'path' in locals() else None
        })


# ──────────────────────────────────────────────────────────────────────
# Test entry point
# ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Test 1: JSON format write
    test1 = json.dumps({
        "path": "test_file.txt",
        "mode": "write",
        "content": "Hello, JARVIS!"
    })
    print("Test 1 (JSON write):")
    print(execute(test1))
    print()
    
    # Test 2: JSON format append
    test2 = json.dumps({
        "path": "test_file.txt",
        "mode": "append",
        "content": "\nLine 2"
    })
    print("Test 2 (JSON append):")
    print(execute(test2))
    print()
    
    # Test 3: Legacy format (fallback)
    test3 = "write test_legacy.txt This is legacy format"
    print("Test 3 (legacy write):")
    print(execute(test3))


