"""
file_reader action — safely reads local files within an allowed base directory.

Security controls (HARDENED):
  - Path traversal prevention (resolve + is_relative_to check)
  - Configurable ALLOWED_BASE_DIR (default: user home / jarvis_workspace)
  - Hard file size cap (MAX_FILE_BYTES)
  - Blocked extensions list (binaries, executables, media)
  - BLOCKED FILENAMES (secrets): .env, id_rsa, *.pem, *.key, authorized_keys, *.ppk, etc.
  - BLOCKED PATHS: .ssh/, .git/, .aws/, .azure/, node_modules/ (traversal protection)
  - No symlink following outside the allowed tree
  - Case-insensitive security checks

Defines execute(input) so the executor calls it directly.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

ACTION_NAME = "file_reader"

# ── Security config ────────────────────────────────────────────────────────────

# Override via env var: JARVIS_WORKSPACE=/path/to/dir
_DEFAULT_WORKSPACE = Path.home() / "jarvis_workspace"
ALLOWED_BASE_DIR = Path(os.getenv("JARVIS_WORKSPACE", str(_DEFAULT_WORKSPACE))).resolve()

MAX_FILE_BYTES = 100_000  # 100 KB hard cap

# File extensions that should NEVER be read (binaries, executables, media)
_BLOCKED_EXTENSIONS = frozenset({
    ".exe", ".dll", ".so", ".dylib", ".bin", ".com",
    ".bat", ".cmd", ".sh", ".bash", ".ps1",
    ".pyc", ".pyo", ".class",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".ico",
    ".mp3", ".mp4", ".avi", ".mov",
    ".zip", ".tar", ".gz", ".rar", ".7z",
    ".db", ".sqlite", ".sqlite3",
})

# SENSITIVE FILENAMES (exact match, case-insensitive)
_BLOCKED_FILENAMES = frozenset({
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".env.test",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "authorized_keys",
    "known_hosts",
    ".aws/credentials",
    ".aws/config",
    ".azure/config",
    ".docker/config.json",
    ".git/config",
    ".gitconfig",
    ".ssh/config",
    ".ssh/known_hosts",
    ".vault-token",
    "credentials.json",
    "token.json",
    "config.json",
    "secrets.json",
})

# SENSITIVE FILENAME PATTERNS (regex, case-insensitive)
_BLOCKED_PATTERNS = frozenset({
    r".*\.pem$",
    r".*\.key$",
    r".*\.ppk$",
    r".*\.p12$",
    r".*\.pfx$",
    r".*\.cert$",
    r".*\.crt$",
    r".*\.priv$",
    r".*secret.*",
    r".*password.*",
    r".*token.*",
    r".*credential.*",
    r".*apikey.*",
    r".*api_key.*",
    r".*oauth.*",
})

# SENSITIVE DIRECTORY PATHS (substring match, prevent traversal)
_BLOCKED_PATHS = frozenset({
    ".git",
    ".ssh",
    ".aws",
    ".azure",
    ".docker",
    "node_modules",
    ".venv",
    "venv",
    ".env",
    "secrets",
    "credentials",
    ".kube",
})

# ALLOWED EXTENSIONS (whitelist for extra-safe mode)
# If set, ONLY these extensions are allowed
_ALLOWED_EXTENSIONS_STRICT = frozenset({
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".txt", ".md", ".markdown",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".conf", ".config",
    ".html", ".css", ".scss",
    ".sql",
    ".log",
}) or None  # None = off (use blocklist instead)

SYSTEM_PROMPT = (
    "You are a file analysis assistant. You have been given the contents of a file. "
    "Answer the user's question based on this content. "
    "Quote relevant sections when helpful. "
    "Never attempt to read or access sensitive files (.env, .ssh, credentials, etc.)."
)


def preprocess(content: str) -> str:
    """Preprocess input before parsing."""
    return content.strip()


# ── Security helpers ───────────────────────────────────────────────────────────


def _is_sensitive_filename(filename: str) -> bool:
    """Check if filename matches sensitive patterns."""
    filename_lower = filename.lower()
    
    # Exact match check
    if filename_lower in _BLOCKED_FILENAMES:
        return True
    
    # Pattern match check
    for pattern in _BLOCKED_PATTERNS:
        if re.match(pattern, filename_lower, re.IGNORECASE):
            return True
    
    return False


def _is_sensitive_path(path: Path) -> bool:
    """Check if path contains sensitive directories."""
    # Check all parts of the path
    path_parts = path.parts
    for part in path_parts:
        part_lower = part.lower()
        if part_lower in _BLOCKED_PATHS:
            return True
    
    return False


def _safe_resolve(raw_path: str) -> Path | str:
    """
    Resolve path relative to ALLOWED_BASE_DIR.
    Returns a safe Path or an error string.
    
    Security checks:
    1. Path traversal prevention
    2. Extension blocklist
    3. Filename sensitivity blocklist
    4. Directory sensitivity blocklist
    5. Symlink validation
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
        log.error(f"Path resolution failed: {exc}")
        return f"❌ Cannot resolve path: {exc}"

    # CHECK 1: Path traversal — resolved must be under ALLOWED_BASE_DIR
    try:
        resolved.relative_to(ALLOWED_BASE_DIR)
    except ValueError:
        log.warning(f"Path traversal attempt blocked: {resolved}")
        return f"❌ Access denied: path is outside the allowed workspace ({ALLOWED_BASE_DIR})"

    # CHECK 2: Extension blocklist
    if resolved.suffix.lower() in _BLOCKED_EXTENSIONS:
        log.warning(f"Blocked file extension: {resolved.suffix}")
        return f"❌ File type `{resolved.suffix}` is not allowed (binary/media/archive)."

    # CHECK 3: Filename sensitivity
    if _is_sensitive_filename(resolved.name):
        log.warning(f"Blocked sensitive filename: {resolved.name}")
        return f"❌ Cannot read sensitive file: `{resolved.name}`. Access denied."

    # CHECK 4: Path sensitivity (directory names)
    if _is_sensitive_path(resolved):
        log.warning(f"Blocked sensitive path: {resolved}")
        return f"❌ Cannot read from sensitive directory path. Access denied."

    # CHECK 5: Symlink validation (reject symlinks pointing outside workspace)
    if resolved.is_symlink():
        try:
            real = resolved.resolve()
            real.relative_to(ALLOWED_BASE_DIR)
        except ValueError:
            log.warning(f"Symlink escape blocked: {resolved} -> {real}")
            return f"❌ Symlink points outside allowed workspace. Access denied."

    return resolved


# ── Execution ──────────────────────────────────────────────────────────────────


def execute(input_str: str) -> str:
    """
    Read a file and return its contents (truncated if over the size cap).

    Input format (flexible):
      "path/to/file.py"
      "read path/to/file.py"
      "show contents of config.json"
    
    Output: Markdown-formatted file content or error message
    """
    log.info(f"{ACTION_NAME} execute called")
    
    # Extract file path — last quoted token or last whitespace-separated token
    quoted = re.search(r'["\']([^"\']+)["\']', input_str)
    if quoted:
        raw_path = quoted.group(1)
    else:
        # Take the last token that looks like a file path (contains . or /)
        tokens = input_str.strip().split()
        path_tokens = [t for t in tokens if ("." in t or "/" in t or "\\" in t)]
        raw_path = path_tokens[-1] if path_tokens else tokens[-1] if tokens else ""

    if not raw_path:
        log.error("No file path found in request")
        return "❌ No file path found in the request."

    log.info(f"Reading path: {raw_path}")
    
    result = _safe_resolve(raw_path)
    if isinstance(result, str):  # error message
        return result
    resolved = result

    if not resolved.exists():
        log.warning(f"File not found: {resolved}")
        return f"❌ File not found: `{resolved.name}` (looked in `{ALLOWED_BASE_DIR}`)"

    if not resolved.is_file():
        # List directory contents instead
        try:
            entries = sorted(resolved.iterdir(), key=lambda p: (p.is_file(), p.name))
            lines = [f"📁 `{resolved.name}/`", ""]
            for e in entries[:50]:
                icon = "📄" if e.is_file() else "📁"
                lines.append(f"  {icon} {e.name}")
            if len(list(resolved.iterdir())) > 50:
                lines.append("  ... (truncated)")
            log.info(f"Listed directory: {resolved}")
            return "\n".join(lines)
        except PermissionError:
            log.error(f"Permission denied reading directory: {resolved}")
            return f"❌ Permission denied reading directory: `{resolved}`"

    file_size = resolved.stat().st_size
    if file_size > MAX_FILE_BYTES:
        log.warning(f"File too large: {file_size} bytes > {MAX_FILE_BYTES}")
        return (
            f"❌ File too large ({file_size:,} bytes). "
            f"Maximum allowed: {MAX_FILE_BYTES:,} bytes."
        )

    try:
        content = resolved.read_text(encoding="utf-8", errors="replace")
        log.info(f"Successfully read file: {resolved} ({len(content)} chars)")
    except PermissionError:
        log.error(f"Permission denied reading file: {resolved}")
        return f"❌ Permission denied reading: `{resolved.name}`"
    except Exception as exc:
        log.error(f"Error reading file: {exc}", exc_info=True)
        return f"❌ Error reading file: {exc}"

    truncated = ""
    if len(content) > MAX_FILE_BYTES:
        content = content[:MAX_FILE_BYTES]
        truncated = f"\n\n⚠️ *Content truncated at {MAX_FILE_BYTES:,} characters.*"

    lang = resolved.suffix.lstrip(".") or "text"
    return (
        f"**File:** `{resolved.relative_to(ALLOWED_BASE_DIR)}`  "
        f"({file_size:,} bytes)\n\n"
        f"```{lang}\n{content}\n```{truncated}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Test entry point
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    print("Test 1: Attempting to read .env (should be blocked)")
    print(execute(".env"))
    print()
    
    print("Test 2: Attempting to read id_rsa (should be blocked)")
    print(execute(".ssh/id_rsa"))
    print()
    
    print("Test 3: Attempting to read normal file")
    print(execute("README.md"))

