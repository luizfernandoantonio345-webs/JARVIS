"""
Cockpit Routes — FASE 4: UI Cockpit

Provides lightweight read-only endpoints used by the JARVIS frontend
to display the active project state, workspace file tree, and
agent performance summary.

Endpoints
---------
  GET /cockpit/project/{session_id}      — active project status from context_memory
  GET /cockpit/workspace/{session_id}    — files in jobs/<session_id>/
  GET /cockpit/performance               — SelfImprover agent stats summary
  GET /cockpit/recent-intents/{session_id} — last 10 intents for the session
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter

router = APIRouter()

_JOBS_BASE = Path(os.getenv("JARVIS_JOBS_DIR", str(Path(__file__).parent.parent.parent / "jobs")))


# ── Project status ─────────────────────────────────────────────────────────────

@router.get("/project/{session_id}")
def get_project_status(session_id: str):
    """Return the active project state for *session_id*."""
    try:
        from core.context_memory import get_active_project, get_recent_intents
        project = get_active_project(session_id) or {}
        recent  = get_recent_intents(session_id, limit=5)
        goals   = [
            r["intent"].get("goal", "")
            for r in recent
            if r["intent"].get("domain") not in (None, "chat")
        ]
        return {
            "session_id": session_id,
            "project": project,
            "recent_goals": goals,
            "has_project": bool(project.get("goal")),
        }
    except Exception as exc:
        return {"session_id": session_id, "project": {}, "recent_goals": [], "has_project": False, "error": str(exc)}


# ── Workspace files ────────────────────────────────────────────────────────────

@router.get("/workspace/{session_id}")
def get_workspace_files(session_id: str):
    """Return the list of files written to jobs/<session_id>/."""
    workspace = _JOBS_BASE / session_id
    if not workspace.exists():
        return {"session_id": session_id, "workspace": str(workspace), "files": [], "exists": False}

    files: list[dict] = []
    for p in sorted(workspace.rglob("*")):
        if p.is_file():
            try:
                size = p.stat().st_size
            except OSError:
                size = 0
            files.append({
                "path": str(p.relative_to(workspace)).replace("\\", "/"),
                "size_bytes": size,
                "extension": p.suffix.lower(),
            })

    return {
        "session_id": session_id,
        "workspace": str(workspace),
        "files": files,
        "exists": True,
        "total_files": len(files),
    }


# ── Agent performance ──────────────────────────────────────────────────────────

@router.get("/performance")
def get_performance():
    """Return agent performance stats from SelfImprover."""
    try:
        from services.self_improver import get_improver
        imp = get_improver()
        stats = imp.agent_stats()
        return {
            "agents": [s.to_dict() for s in stats],
            "total_events": sum(s.total for s in stats),
        }
    except Exception as exc:
        return {"agents": [], "total_events": 0, "error": str(exc)}


# ── Recent intents ─────────────────────────────────────────────────────────────

@router.get("/recent-intents/{session_id}")
def get_recent_intents(session_id: str, limit: int = 10):
    """Return the last *limit* intents for *session_id*."""
    try:
        from core.context_memory import get_recent_intents as _get
        intents = _get(session_id, limit=limit)
        return {"session_id": session_id, "intents": intents}
    except Exception as exc:
        return {"session_id": session_id, "intents": [], "error": str(exc)}
