"""
routes/terminal.py — Persistent terminal session API.

Endpoints:
  POST   /terminal/sessions           → create a new terminal session
  GET    /terminal/sessions           → list active sessions
  POST   /terminal/{sid}/send         → send a command, get output
  GET    /terminal/{sid}/history      → get session output history
  DELETE /terminal/{sid}              → kill a session
  POST   /terminal/once               → run a one-shot command (no persistent session)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

router = APIRouter()


# ── Request / Response models ──────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    name: str = Field("default", min_length=1, max_length=64,
                      description="Human-readable session name")
    cwd: str = Field("", description="Working directory for the session")


class SendCommandRequest(BaseModel):
    command: str = Field(..., min_length=1, max_length=4096)
    timeout: float = Field(15.0, ge=1.0, le=120.0,
                           description="Max seconds to wait for output")


class RunOnceRequest(BaseModel):
    command: str = Field(..., min_length=1, max_length=4096)
    cwd: str = Field("", description="Working directory")
    timeout: float = Field(15.0, ge=1.0, le=60.0)


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/sessions")
async def create_session(req: CreateSessionRequest) -> dict:
    """Create a new persistent terminal session."""
    from services.terminal_manager import get_terminal_manager
    tm = get_terminal_manager()
    try:
        sid = tm.create_session(
            name=req.name,
            cwd=req.cwd or None,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"session_id": sid, "name": req.name, "cwd": req.cwd or "default"}


@router.get("/sessions")
async def list_sessions() -> dict:
    """List all active terminal sessions."""
    from services.terminal_manager import get_terminal_manager
    tm = get_terminal_manager()
    try:
        sessions = tm.list_sessions()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"sessions": sessions}


@router.post("/{sid}/send")
async def send_command(sid: str, req: SendCommandRequest) -> dict:
    """Send a command to an existing session and return its output."""
    from services.terminal_manager import get_terminal_manager
    tm = get_terminal_manager()
    try:
        output = tm.send_command(sid, req.command, timeout=req.timeout)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Session '{sid}' not found")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"session_id": sid, "command": req.command, "output": output}


@router.get("/{sid}/history")
async def get_history(sid: str) -> dict:
    """Get the full output history of a session."""
    from services.terminal_manager import get_terminal_manager
    tm = get_terminal_manager()
    try:
        history = tm.get_history(sid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Session '{sid}' not found")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"session_id": sid, "history": history}


@router.delete("/{sid}")
async def kill_session(sid: str) -> dict:
    """Kill (terminate) a terminal session."""
    from services.terminal_manager import get_terminal_manager
    tm = get_terminal_manager()
    try:
        tm.kill_session(sid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Session '{sid}' not found")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"success": True, "session_id": sid}


@router.post("/once")
async def run_once(req: RunOnceRequest) -> dict:
    """Run a one-shot command without a persistent session."""
    from services.terminal_manager import get_terminal_manager
    tm = get_terminal_manager()
    try:
        output = tm.run_once(req.command, cwd=req.cwd or None, timeout=req.timeout)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"command": req.command, "output": output}
