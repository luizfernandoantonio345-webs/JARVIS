"""
routes/workspace.py — Project lifecycle API.

Endpoints:
  POST  /workspace/scaffold         → scaffold a new project from template
  GET   /workspace/detect/{path}    → detect project type at path
  POST  /workspace/install          → install deps for a project
  POST  /workspace/run              → run a project and return output
  GET   /workspace/files            → list files in a workspace project
  POST  /workspace/files/write      → write a file
  GET   /workspace/files/read       → read a file
  POST  /workspace/scan             → dependency security scan
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

router = APIRouter()


# ── Request / Response models ──────────────────────────────────────────────────

class ScaffoldRequest(BaseModel):
    project_name: str = Field(..., min_length=1, max_length=64,
                              description="Project directory name")
    template: str = Field("script",
                          description="One of: fastapi, cli, library, script, node-api, react")
    base_dir: str = Field("", description="Base directory (empty = jarvis_workspace default)")


class RunRequest(BaseModel):
    project_path: str = Field(..., description="Workspace-relative path to the project")
    timeout: float = Field(20.0, ge=1.0, le=120.0)
    command_override: str = Field("", description="Optional command override")


class InstallRequest(BaseModel):
    project_path: str = Field(..., description="Workspace-relative path to the project")


class WriteFileRequest(BaseModel):
    project_path: str = Field(...)
    file_name: str = Field(..., description="Relative filename within the project")
    content: str = Field(...)


class ReadFileRequest(BaseModel):
    project_path: str = Field(...)
    file_name: str = Field(...)


class ScanRequest(BaseModel):
    project_path: str = Field(...)


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/scaffold")
async def scaffold_project(req: ScaffoldRequest) -> dict:
    """Scaffold a new project from a built-in template."""
    from services.workspace_manager import get_workspace_manager
    wm = get_workspace_manager()
    try:
        result = await asyncio.to_thread(
            lambda: wm.scaffold(
                project_name=req.project_name,
                template=req.template,
                base_dir=req.base_dir or None,
            )
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if not result.success:
        raise HTTPException(status_code=422, detail=result.error)

    return {
        "success":      True,
        "project_path": result.project_path,
        "files":        result.files_created,
        "template":     req.template,
    }


@router.get("/detect/{project_path:path}")
async def detect_project(project_path: str) -> dict:
    """Detect the project type and run command at the given path."""
    from services.workspace_manager import get_workspace_manager
    wm = get_workspace_manager()
    try:
        meta = await asyncio.to_thread(wm.detect_project, project_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if meta is None:
        raise HTTPException(status_code=404, detail=f"No recognizable project at '{project_path}'")

    return {
        "project_path":  project_path,
        "project_type":  meta.project_type,
        "entry_point":   meta.entry_point,
        "run_command":   meta.run_command,
        "has_deps_file": meta.has_deps_file,
    }


@router.post("/install")
async def install_deps(req: InstallRequest) -> dict:
    """Install dependencies for the project at the given path."""
    from services.workspace_manager import get_workspace_manager
    wm = get_workspace_manager()
    try:
        stdout, stderr, code = await asyncio.to_thread(wm.install_deps, req.project_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "success":      code == 0,
        "returncode":   code,
        "stdout":       stdout[:3000],
        "stderr":       stderr[:1000],
    }


@router.post("/run")
async def run_project(req: RunRequest) -> dict:
    """Run the project at the given path and return captured output."""
    from services.workspace_manager import get_workspace_manager
    wm = get_workspace_manager()
    try:
        result = await asyncio.to_thread(
            lambda: wm.run_project(
                path=req.project_path,
                timeout=req.timeout,
                command_override=req.command_override or None,
            )
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return result.to_dict()


@router.get("/files")
async def list_files(
    project_path: Annotated[str, Query(description="Workspace-relative project path")],
) -> dict:
    """List files within a workspace project."""
    from services.workspace_manager import get_workspace_manager
    wm = get_workspace_manager()
    try:
        files = wm.list_project_files(project_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"project_path": project_path, "files": files}


@router.post("/files/write")
async def write_file(req: WriteFileRequest) -> dict:
    """Write (create or overwrite) a file within a workspace project."""
    from services.workspace_manager import get_workspace_manager
    wm = get_workspace_manager()
    try:
        result = wm.write_project_file(req.project_path, req.file_name, req.content)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if not result.success:
        raise HTTPException(status_code=422, detail=result.error)

    return {"success": True, "path": result.path}


@router.post("/files/read")
async def read_file(req: ReadFileRequest) -> dict:
    """Read a file from within a workspace project."""
    from services.workspace_manager import get_workspace_manager
    wm = get_workspace_manager()
    try:
        result = wm.read_project_file(req.project_path, req.file_name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if not result.success:
        raise HTTPException(status_code=404, detail=result.error)

    return {"success": True, "content": result.content, "path": result.path}


@router.post("/scan")
async def scan_dependencies(req: ScanRequest) -> dict:
    """Run a security scan on the project's dependency files."""
    from services.dependency_scanner import get_scanner
    scanner = get_scanner()
    try:
        report = scanner.scan_project(req.project_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return report.to_dict()
