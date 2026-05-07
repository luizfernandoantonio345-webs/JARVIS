"""
scaffolder — FASE 10 AutoDev Engine, Component 1

Analyses a high-level goal and generates the project directory structure,
technology stack, and dependency manifest files.

Responsibilities
----------------
  1. Call the LLM to infer the tech stack from the goal string.
  2. Produce a ``ProjectBlueprint`` (list of files + their purposes).
  3. Write the scaffold skeleton (empty files + requirements/package.json).
  4. Return a machine-readable representation for the code generator.

Role in the system
------------------
First stage in the AutoDev pipeline:
  scaffolder → code_generator → validator → auto_fixer → done

Usage example
-------------
>>> from backend.autodev.scaffolder import Scaffolder
>>> sc = Scaffolder(job_id="abc123", workspace="/workspace/jobs/abc123")
>>> blueprint = await sc.scaffold("crie uma API REST de lista de tarefas com FastAPI")
>>> for f in blueprint.files:
...     print(f.path, "-", f.purpose)
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from services.llm_service import call_llm

log = structlog.get_logger(__name__)

# ── Models ─────────────────────────────────────────────────────────────────────

@dataclass
class FileSpec:
    path: str        # relative path inside the job workspace
    purpose: str     # one-line description (passed to CodeGenerator)
    language: str    # "python" | "typescript" | "json" | "toml" | etc.
    content: str = ""  # pre-populated content (boilerplate or empty)


@dataclass
class ProjectBlueprint:
    job_id: str
    goal: str
    stack: str              # e.g. "FastAPI, SQLite, Pydantic"
    files: list[FileSpec] = field(default_factory=list)
    workspace: str = ""


# ── Prompts ────────────────────────────────────────────────────────────────────

_SCAFFOLD_SYSTEM = """\
You are a senior software architect. Given a project goal, produce a JSON
project blueprint. Reply ONLY with valid JSON — no prose, no markdown fences.

Schema:
{
  "stack": "comma-separated tech stack",
  "files": [
    {"path": "relative/path.ext", "purpose": "one sentence", "language": "python|typescript|json|..."}
  ],
  "requirements": ["dep1", "dep2"]
}

Rules:
- Maximum 12 files.
- Always include a requirements.txt (Python) or package.json (Node.js).
- Include a README.md.
- Group logically: models, routes, services, etc.
- Paths are relative to project root.
"""


# ── Scaffolder ─────────────────────────────────────────────────────────────────

class Scaffolder:
    """
    Analyses a goal and generates the project skeleton.

    Parameters
    ----------
    job_id:    Unique AutoDev job identifier.
    workspace: Absolute path to the isolated job directory.
    """

    def __init__(self, job_id: str, workspace: str | Path) -> None:
        self.job_id = job_id
        self.workspace = Path(workspace)

    async def scaffold(self, goal: str) -> ProjectBlueprint:
        """
        Call the LLM to produce a blueprint, then write the skeleton to disk.

        Returns a ProjectBlueprint with all FileSpec entries populated.

        Usage example
        -------------
        >>> bp = await scaffolder.scaffold("create a REST API for a todo list")
        >>> print(bp.stack)
        >>> print([f.path for f in bp.files])
        """
        log.info("scaffolder.start", job_id=self.job_id, goal=goal[:80])
        raw = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: call_llm(
                [
                    {"role": "system", "content": _SCAFFOLD_SYSTEM},
                    {"role": "user",   "content": f"Goal: {goal}"},
                ],
                force_api=False,
            ),
        )
        blueprint = self._parse_blueprint(goal, raw or "{}")
        self._write_skeleton(blueprint)
        log.info("scaffolder.done", job_id=self.job_id, files=len(blueprint.files))
        return blueprint

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _parse_blueprint(self, goal: str, raw: str) -> ProjectBlueprint:
        try:
            data: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]+\}", raw)
            data = json.loads(match.group()) if match else {}

        stack = data.get("stack", "Python, FastAPI")
        requirements: list[str] = data.get("requirements", [])
        raw_files: list[dict] = data.get("files", [])

        files: list[FileSpec] = []
        has_requirements = False

        for rf in raw_files:
            path = rf.get("path", "")
            lang = rf.get("language", _infer_language(path))
            purpose = rf.get("purpose", "")
            content = rf.get("content", "")
            files.append(FileSpec(path=path, purpose=purpose, language=lang, content=content))
            if "requirements.txt" in path or "package.json" in path:
                has_requirements = True

        # Ensure a dependency manifest exists
        if not has_requirements:
            if "node" in stack.lower() or "typescript" in stack.lower():
                files.append(FileSpec(
                    path="package.json",
                    purpose="Node.js dependencies",
                    language="json",
                    content=json.dumps({"name": "project", "version": "1.0.0", "dependencies": {}}, indent=2),
                ))
            else:
                reqs_content = "\n".join(requirements) if requirements else "fastapi\nuvicorn"
                files.append(FileSpec(
                    path="requirements.txt",
                    purpose="Python dependencies",
                    language="text",
                    content=reqs_content,
                ))

        return ProjectBlueprint(
            job_id=self.job_id,
            goal=goal,
            stack=stack,
            files=files,
            workspace=str(self.workspace),
        )

    def _write_skeleton(self, blueprint: ProjectBlueprint) -> None:
        """Create all directories and empty/pre-populated files."""
        self.workspace.mkdir(parents=True, exist_ok=True)
        for spec in blueprint.files:
            full_path = self.workspace / spec.path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            if not full_path.exists():
                full_path.write_text(spec.content, encoding="utf-8")
                log.debug("scaffolder.created", path=spec.path)


def _infer_language(path: str) -> str:
    ext = Path(path).suffix.lower()
    return {
        ".py": "python", ".ts": "typescript", ".js": "javascript",
        ".json": "json", ".toml": "toml", ".md": "markdown",
        ".txt": "text", ".yaml": "yaml", ".yml": "yaml",
    }.get(ext, "text")
