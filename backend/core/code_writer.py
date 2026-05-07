"""
code_writer — FASE 3: Execution Engine

Extracts real source files from LLM/agent text output and writes them to
the workspace on disk.  Bridges the gap between an agent that *describes*
code and JARVIS actually *having* that code on the filesystem.

## Extraction patterns supported

  Pattern 1 — explicit header (most reliable):
    # File: path/to/file.py
    ```python
    <code>
    ```

  Pattern 2 — bold markdown header:
    **File: path/to/file.py**
    ```python
    <code>
    ```

  Pattern 3 — filename inside fence (common in GPT outputs):
    ```python main.py
    <code>
    ```

  Pattern 4 — JARVIS [AGENT] section + filename in code comment:
    **[DEV]**
    # main.py
    <code>

After extraction every file is:
  1. Validated for path traversal attempts (security)
  2. Written to  jobs/<session_id>/<filename>  via direct pathlib (no shell)
  3. Registered in context_memory via ProjectManagerAgent

Usage
-----
>>> from core.code_writer import extract_and_write, CodeWriteResult
>>> result = extract_and_write("sess-001", agent_output_text)
>>> print(result.files_written)   # ["main.py", "requirements.txt"]
>>> print(result.workspace_dir)   # d:/JAVIS/jobs/sess-001
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────

JOBS_BASE_DIR: Path = Path(
    os.getenv("JARVIS_JOBS_DIR", str(Path(__file__).parent.parent.parent / "jobs"))
).resolve()

MAX_FILE_SIZE_BYTES = 512 * 1024   # 512 KB per file — safety cap
_SAFE_EXTENSIONS = frozenset({
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".scss",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env",
    ".txt", ".md", ".rst", ".sh", ".sql", ".graphql",
    ".Dockerfile", "",  # no extension (Makefile, Dockerfile, etc.)
})

# File patterns to look for in LLM output
# Order matters — most specific patterns first
_FILE_PATTERNS: list[re.Pattern] = [
    # Pattern 1: "# File: path.py" or "# file: path.py" followed by code fence
    re.compile(
        r"#\s*[Ff]ile:\s*([\w/.\-]+\.\w+)\s*\n```(?:\w+)?\n(.*?)```",
        re.DOTALL,
    ),
    # Pattern 2: "**File: path.py**" or "**filename: path.py**"
    re.compile(
        r"\*\*(?:[Ff]ile|[Ff]ilename):\s*([\w/.\-]+\.\w+)\*\*\s*\n```(?:\w+)?\n(.*?)```",
        re.DOTALL,
    ),
    # Pattern 3: code fence with filename "```python main.py"
    re.compile(
        r"```(?:\w+)\s+([\w/.\-]+\.\w+)\s*\n(.*?)```",
        re.DOTALL,
    ),
    # Pattern 4: line comment with just the filename at the start of a fence
    re.compile(
        r"```(?:\w+)?\n#\s*([\w/.\-]+\.\w+)\s*\n(.*?)```",
        re.DOTALL,
    ),
    # Pattern 5: "=== path.py ===" style (common in some prompts)
    re.compile(
        r"={3,}\s*([\w/.\-]+\.\w+)\s*={3,}\s*\n```(?:\w+)?\n(.*?)```",
        re.DOTALL,
    ),
]


# ── Models ─────────────────────────────────────────────────────────────────────

@dataclass
class ExtractedFile:
    path: str     # relative path as declared in agent output
    content: str  # file contents


@dataclass
class CodeWriteResult:
    session_id: str
    workspace_dir: str          # absolute path to the job directory
    files_written: list[str] = field(default_factory=list)
    files_skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return bool(self.files_written) and not self.errors

    def summary(self) -> str:
        if not self.files_written and not self.errors:
            return "Nenhum arquivo encontrado no output do agente."
        lines: list[str] = []
        if self.files_written:
            files_str = ", ".join(f"`{f}`" for f in self.files_written)
            lines.append(f"✅ **{len(self.files_written)} arquivo(s) criado(s)** em `{self.workspace_dir}`:\n{files_str}")
        if self.files_skipped:
            lines.append(f"⚠️ Ignorados (tipo não permitido): {', '.join(self.files_skipped)}")
        if self.errors:
            lines.append(f"❌ Erros: {'; '.join(self.errors)}")
        return "\n".join(lines)


# ── Core functions ─────────────────────────────────────────────────────────────

def extract_files(text: str) -> list[ExtractedFile]:
    """
    Parse *text* (agent LLM output) and return all embedded file blocks.

    Deduplicates by path — last occurrence wins (agents sometimes re-output
    an improved version of the same file).
    """
    seen: dict[str, str] = {}   # path → content (last wins)

    for pattern in _FILE_PATTERNS:
        for match in pattern.finditer(text):
            raw_path = match.group(1).strip()
            content  = match.group(2)

            # Normalise path separators and strip leading ./
            raw_path = raw_path.replace("\\", "/").lstrip("./")
            if raw_path:
                seen[raw_path] = content

    return [ExtractedFile(path=p, content=c) for p, c in seen.items()]


def _is_safe_path(rel_path: str) -> bool:
    """Reject path-traversal attempts and blocked file types."""
    # Absolute paths and traversal
    if rel_path.startswith("/") or ".." in rel_path.split("/"):
        return False
    # Blocked extensions
    suffix = Path(rel_path).suffix.lower()
    if suffix not in _SAFE_EXTENSIONS:
        return False
    return True


def write_to_workspace(
    session_id: str,
    files: list[ExtractedFile],
) -> CodeWriteResult:
    """
    Write *files* to  JOBS_BASE_DIR/<session_id>/  on disk.

    Creates parent directories as needed.  Never raises — errors are
    collected in CodeWriteResult.errors.

    Returns
    -------
    CodeWriteResult with paths of written, skipped, and errored files.
    """
    workspace = JOBS_BASE_DIR / session_id
    result = CodeWriteResult(
        session_id=session_id,
        workspace_dir=str(workspace),
    )

    if not files:
        return result

    try:
        workspace.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        result.errors.append(f"Cannot create workspace dir: {exc}")
        return result

    for ef in files:
        if not _is_safe_path(ef.path):
            result.files_skipped.append(ef.path)
            log.warning("code_writer: skipped unsafe path %r", ef.path)
            continue

        content = ef.content
        if len(content.encode()) > MAX_FILE_SIZE_BYTES:
            result.errors.append(f"{ef.path}: content too large (>{MAX_FILE_SIZE_BYTES} bytes)")
            continue

        target = workspace / ef.path
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            result.files_written.append(ef.path)
            log.info("code_writer: wrote %s (%d chars)", ef.path, len(content))
        except Exception as exc:
            result.errors.append(f"{ef.path}: {exc}")
            log.warning("code_writer: failed to write %r: %s", ef.path, exc)

    return result


def extract_and_write(session_id: str, text: str) -> CodeWriteResult:
    """
    Convenience wrapper: extract files from *text* then write them.

    Also calls ProjectManagerAgent.register_files() to keep context_memory
    in sync — silently ignores any error there.
    """
    files = extract_files(text)
    result = write_to_workspace(session_id, files)

    if result.files_written:
        _register_files(session_id, result.files_written)

    return result


def _register_files(session_id: str, file_paths: list[str]) -> None:
    """Notify ProjectManagerAgent about newly written files (best-effort)."""
    try:
        from agents.project_manager_agent import get_project_manager
        get_project_manager().register_files(session_id, file_paths)
    except Exception as exc:
        log.debug("code_writer._register_files skipped: %s", exc)
