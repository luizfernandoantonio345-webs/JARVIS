"""
Orchestrator routes — central dispatch and autonomous loop API.

Endpoints:
  POST /orchestrate            → Orchestrator.dispatch()
  GET  /orchestrate/modes      → list available modes
  POST /orchestrate/autoloop   → AutoLoop.run()
  GET  /orchestrate/guard/stats→ SecurityGuard stats
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

from services.orchestrator import get_orchestrator
from services.auto_loop import get_loop

log = logging.getLogger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


# ── Request / Response schemas ─────────────────────────────────────────────────

class OrchestrateRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8192)
    session_id: str = Field(default="default", max_length=128)
    mode: str | None = Field(default=None, max_length=64)
    history: list[dict] = Field(default_factory=list)
    agent_mode: str | None = Field(default=None, max_length=64)


class AutoLoopRequest(BaseModel):
    objective: str = Field(..., min_length=1, max_length=4096)
    session_id: str = Field(default="default", max_length=128)
    mode: str = Field(default="auto_dev", max_length=64)
    history: list[dict] = Field(default_factory=list)


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("")
async def orchestrate(request: Request, body: OrchestrateRequest) -> dict:
    """
    Send a message to the Orchestrator.

    The Orchestrator detects intent, routes to the appropriate subsystem
    (chat, dev, auto_dev, security, automation, task, shell, fs, vscode),
    and returns the result.
    """
    orch = get_orchestrator()
    result = await asyncio.to_thread(
        lambda: orch.dispatch(
            message=body.message,
            session_id=body.session_id,
            mode=body.mode,
            history=body.history,
            agent_mode=body.agent_mode,
        )
    )
    return result.to_dict()


@router.get("/modes")
async def list_modes() -> dict:
    """Return all available orchestration modes with descriptions."""
    return {
        "modes": [
            {"name": "chat",        "description": "Plain conversation with memory context"},
            {"name": "dev",         "description": "Multi-agent development pipeline"},
            {"name": "auto_dev",    "description": "Autonomous build loop (max 5 iterations)"},
            {"name": "security",    "description": "Security analysis and vulnerability scan"},
            {"name": "automation",  "description": "AgentManager multi-step automation"},
            {"name": "task",        "description": "Task planner + executor pipeline"},
            {"name": "shell",       "description": "Safe shell command execution"},
            {"name": "fs",          "description": "Filesystem CRUD (workspace-scoped)"},
            {"name": "vscode",      "description": "VS Code editor control"},
        ]
    }


@router.post("/autoloop")
async def run_autoloop(request: Request, body: AutoLoopRequest) -> dict:
    """
    Run the autonomous loop for a given objective.

    The loop iterates up to 5 times, using plan→execute→validate→improve.
    Stops on: success, repeated failure, security block, or max iterations.
    """
    loop = get_loop()
    result = await asyncio.to_thread(
        lambda: loop.run(
            objective=body.objective,
            session_id=body.session_id,
            history=body.history,
            mode=body.mode,
        )
    )
    return result.to_dict()


@router.get("/guard/stats")
async def guard_stats() -> dict:
    """Return SecurityGuard cumulative stats."""
    from services.security_guard import get_guard
    return get_guard().stats()


# ── CoreOrchestrator v2 endpoints ──────────────────────────────────────────────

class ProcessRequest(BaseModel):
    input: str = Field(..., min_length=1, max_length=8192)
    session_id: str | None = Field(default=None, max_length=128)
    source: str = Field(default="api", max_length=32)
    history: list[dict] = Field(default_factory=list)
    force_chat: bool = False
    force_local: bool = False
    force_api: bool = False


@router.post("/v2/process")
async def process_v2(request: Request, body: ProcessRequest) -> dict:
    """
    JARVIS Core Orchestrator v2 — single unified entry point.

    Pipeline: Memory Injection → Intent/Chat → Risk Engine →
              Confirmation Gate → Tool Execution → Behavior Log →
              Memory Write → Autonomy Analysis → Output
    """
    from core.orchestrator import get_orchestrator as _get_core_orch
    result = await _get_core_orch().process(
        user_input=body.input,
        session_id=body.session_id,
        source=body.source,
        history=body.history,
        force_chat=body.force_chat,
        force_local=body.force_local,
        force_api=body.force_api,
    )
    return result.to_dict()


@router.get("/v2/autonomy/status")
async def autonomy_v2_status() -> dict:
    """Return autonomy_v2 manager status and pending suggestions."""
    from autonomy_v2.autonomy_manager import get_autonomy_manager
    return get_autonomy_manager().status()


@router.get("/v2/autonomy/suggestions")
async def autonomy_v2_suggestions() -> dict:
    """Return and consume pending proactive suggestions."""
    from autonomy_v2.autonomy_manager import get_autonomy_manager
    suggestions = get_autonomy_manager().get_suggestions()
    return {"suggestions": suggestions, "count": len(suggestions)}


class SetLevelRequest(BaseModel):
    level: int = Field(..., ge=0, le=2)


@router.post("/v2/autonomy/level")
async def set_autonomy_v2_level(body: SetLevelRequest) -> dict:
    """Set the autonomy_v2 level (0=reactive, 1=suggestions, 2=auto-safe)."""
    from autonomy_v2.autonomy_manager import get_autonomy_manager
    from autonomy_v2.autonomy_policy import AutonomyLevel
    get_autonomy_manager().set_level(AutonomyLevel(body.level))
    return {"level": body.level, "status": "updated"}

