"""
context_tracker — FASE 10 AutoDev Engine, Component 2.5

Maintains an accumulating ProjectContext across all file-generation calls so
the LLM always knows what has already been generated.

What is stored per file
-----------------------
  - path + language
  - purpose (from FileSpec)
  - public interface summary: top-level defs/classes/exports (not full code)
  - first 300 chars of the file as a "preview"

The context is persisted to jobs/{job_id}/context.json after every update so
a resumed job can reload it without re-generating already completed files.

Usage
-----
>>> ctx = ProjectContext(job_id="abc", workspace=Path("jobs/abc"))
>>> ctx.add(generated_file)
>>> summary = ctx.render_for_prompt(max_chars=3000)
>>> ctx.save()
>>> ctx2 = ProjectContext.load_or_create(job_id="abc", workspace=Path("jobs/abc"))
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from .code_generator import GeneratedFile

log = structlog.get_logger(__name__)

_CONTEXT_FILENAME = "context.json"


# ── File summary ───────────────────────────────────────────────────────────────

def _extract_python_interface(code: str) -> str:
    """Return a compact interface listing for a Python source string."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return "(unparseable)"

    items: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            # Only top-level or class methods at depth 1
            args = [a.arg for a in node.args.args]
            items.append(f"def {node.name}({', '.join(args)})")
        elif isinstance(node, ast.ClassDef):
            bases = [getattr(b, "id", "?") for b in node.bases]
            items.append(f"class {node.name}({', '.join(bases)})")

    return "; ".join(items[:20]) if items else "(no public interface)"


def _extract_ts_interface(code: str) -> str:
    """Rough interface extractor for TypeScript/JavaScript."""
    exports = re.findall(r"export\s+(?:default\s+)?(?:function|class|const|interface|type)\s+(\w+)", code)
    if exports:
        return "exports: " + ", ".join(exports[:20])
    return "(no exports detected)"


def _summarise(gf: GeneratedFile) -> str:
    lang = gf.language.lower()
    if lang in ("python", "py"):
        iface = _extract_python_interface(gf.code)
    elif lang in ("typescript", "ts", "javascript", "js"):
        iface = _extract_ts_interface(gf.code)
    else:
        iface = f"({gf.language} file)"

    preview = gf.code[:300].replace("\n", " ").strip()
    return f"[{gf.path}] {iface} | preview: {preview}"


# ── Models ─────────────────────────────────────────────────────────────────────

@dataclass
class FileSummary:
    path: str
    language: str
    purpose: str
    interface: str   # compact interface / exports
    preview: str     # first 300 chars

    @classmethod
    def from_generated(cls, gf: GeneratedFile) -> "FileSummary":
        lang = gf.language.lower()
        if lang in ("python", "py"):
            iface = _extract_python_interface(gf.code)
        elif lang in ("typescript", "ts", "javascript", "js"):
            iface = _extract_ts_interface(gf.code)
        else:
            iface = f"({gf.language} file)"

        return cls(
            path=gf.path,
            language=gf.language,
            purpose=gf.purpose,
            interface=iface,
            preview=gf.code[:300].replace("\n", " ").strip(),
        )


# ── ProjectContext ─────────────────────────────────────────────────────────────

class ProjectContext:
    """
    Accumulates summaries of generated files to provide coherent cross-file
    context for subsequent LLM code-generation calls.

    Parameters
    ----------
    job_id:    AutoDev job identifier.
    workspace: Absolute path to the job workspace directory.
    goal:      High-level project goal (included in every prompt).
    stack:     Tech stack string from the Scaffolder blueprint.
    """

    def __init__(
        self,
        job_id: str,
        workspace: Path,
        goal: str = "",
        stack: str = "",
    ) -> None:
        self.job_id = job_id
        self.workspace = workspace
        self.goal = goal
        self.stack = stack
        self._files: list[FileSummary] = []

    # ── Mutation ───────────────────────────────────────────────────────────────

    def add(self, gf: GeneratedFile) -> None:
        """Add a newly generated file to the context."""
        summary = FileSummary.from_generated(gf)
        # Replace if same path already exists (after a fix)
        self._files = [f for f in self._files if f.path != gf.path]
        self._files.append(summary)
        log.debug("context_tracker.add", job_id=self.job_id, path=gf.path)

    def update_after_fix(self, path: str, fixed_code: str, language: str = "python") -> None:
        """Refresh the stored summary for *path* after an auto-fix."""
        for i, fs in enumerate(self._files):
            if fs.path == path:
                lang = language.lower()
                if lang in ("python", "py"):
                    iface = _extract_python_interface(fixed_code)
                elif lang in ("typescript", "ts", "javascript", "js"):
                    iface = _extract_ts_interface(fixed_code)
                else:
                    iface = fs.interface
                self._files[i] = FileSummary(
                    path=fs.path,
                    language=fs.language,
                    purpose=fs.purpose,
                    interface=iface,
                    preview=fixed_code[:300].replace("\n", " ").strip(),
                )
                break

    # ── Query ──────────────────────────────────────────────────────────────────

    def render_for_prompt(self, max_chars: int = 3000) -> str:
        """
        Return a compact string suitable for injection into an LLM prompt.

        Format:
            Project: <goal>
            Stack: <stack>
            Already generated files:
              [path] interface | preview…
        """
        if not self._files:
            return f"Project: {self.goal}\nStack: {self.stack}\n(no files generated yet)"

        lines = [
            f"Project: {self.goal}",
            f"Stack: {self.stack}",
            "Already generated files:",
        ]
        for fs in self._files:
            lines.append(f"  [{fs.path}] {fs.purpose} | {fs.interface}")

        text = "\n".join(lines)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n...(truncated)"
        return text

    @property
    def generated_paths(self) -> list[str]:
        """Ordered list of file paths that have been generated."""
        return [f.path for f in self._files]

    # ── Persistence ────────────────────────────────────────────────────────────

    def save(self) -> None:
        """Persist context to jobs/{job_id}/context.json."""
        data: dict[str, Any] = {
            "job_id": self.job_id,
            "goal": self.goal,
            "stack": self.stack,
            "files": [asdict(f) for f in self._files],
        }
        ctx_file = self.workspace / _CONTEXT_FILENAME
        ctx_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        log.debug("context_tracker.saved", job_id=self.job_id, files=len(self._files))

    @classmethod
    def load_or_create(
        cls,
        job_id: str,
        workspace: Path,
        goal: str = "",
        stack: str = "",
    ) -> "ProjectContext":
        """
        Load persisted context from disk, or create a fresh one if not found.

        Used when resuming an interrupted job.
        """
        ctx_file = workspace / _CONTEXT_FILENAME
        if ctx_file.exists():
            try:
                data = json.loads(ctx_file.read_text(encoding="utf-8"))
                obj = cls(
                    job_id=data.get("job_id", job_id),
                    workspace=workspace,
                    goal=data.get("goal", goal),
                    stack=data.get("stack", stack),
                )
                obj._files = [FileSummary(**f) for f in data.get("files", [])]
                log.info(
                    "context_tracker.loaded",
                    job_id=job_id,
                    files=len(obj._files),
                )
                return obj
            except Exception as exc:
                log.warning("context_tracker.load_failed", job_id=job_id, error=str(exc))

        return cls(job_id=job_id, workspace=workspace, goal=goal, stack=stack)
