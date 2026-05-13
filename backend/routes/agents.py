"""
/agents routes — multi-agent system API endpoints.

GET  /agents/             → list all registered agents
POST /agents/{role}/run   → invoke a specific agent synchronously
POST /agents/run          → run the full multi-agent pipeline (FASE 9)
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.agent_registry import get_agent, agent_info
from agents.multi_agent_orchestrator import get_multi_agent_orchestrator

log = logging.getLogger(__name__)
router = APIRouter()


# ── Request / Response models ──────────────────────────────────────────────────

class AgentRunRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=32_000)
    session_id: str = Field(default="default")
    history: list[dict] = Field(default_factory=list)
    force_local: bool = Field(default=False)
    force_api: bool = Field(default=False)


class AgentRunResponse(BaseModel):
    agent: str
    response: str
    metadata: dict = Field(default_factory=dict)


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/", summary="List all registered agents")
def list_agents_route():
    """Return metadata for all registered specialized agents."""
    return {"agents": agent_info()}


@router.post("/{role}/run", response_model=AgentRunResponse, summary="Invoke a specialized agent")
def run_agent(role: str, body: AgentRunRequest):
    """
    Invoke the specified agent with a message.

    - **role**: agent role (`dev`, `architect`, `security`, `debugger`)
    - **message**: the prompt or task for the agent
    - **history**: optional prior conversation turns
    """
    try:
        agent = get_agent(role)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    log.info("[agents/%s] message=%d chars session=%s", role, len(body.message), body.session_id)

    try:
        result = agent.run(
            message=body.message,
            history=body.history or None,
            force_local=body.force_local,
            force_api=body.force_api,
        )
    except Exception as exc:
        log.exception("[agents/%s] run failed", role)
        raise HTTPException(status_code=503, detail=f"Agent error: {exc}")

    return AgentRunResponse(
        agent=result.agent,
        response=result.response,
        metadata=result.metadata,
    )


# ── Multi-agent pipeline endpoint (FASE 9) ─────────────────────────────────────

class MultiAgentRunRequest(BaseModel):
    goal: str = Field(..., min_length=1, max_length=32_000, description="High-level objective for the agent team")
    session_id: str = Field(default="multi-agent")


class MultiAgentRunResponse(BaseModel):
    status: str
    output: str
    tasks: list[dict] = Field(default_factory=list)
    iterations: int = 0
    error: str | None = None


_FILE_ANALYSIS_RE = re.compile(r"(?:arquivo|file)\s+([^\s]+\.py)", re.IGNORECASE)
_DECORATOR_RE = re.compile(r"@(app|router)\.(get|post|put|delete|patch|options|head)\(\s*[\"']([^\"']+)[\"']")
_INCLUDE_ROUTER_RE = re.compile(r"include_router\([^\n]*prefix\s*=\s*[\"']([^\"']+)[\"']")
_WS_RE = re.compile(r"@(app|router)\.websocket\(\s*[\"']([^\"']+)[\"']")


def _extract_goal_file(goal: str) -> Path | None:
    match = _FILE_ANALYSIS_RE.search(goal)
    if not match:
        return None
    candidate = Path(match.group(1))
    if candidate.exists():
        return candidate
    repo_candidate = Path.cwd() / candidate
    if repo_candidate.exists():
        return repo_candidate
    return None


def _fallback_endpoint_analysis(goal: str) -> str | None:
    target = _extract_goal_file(goal)
    if not target:
        return None

    lower_goal = goal.lower()
    if "endpoint" not in lower_goal and "fastapi" not in lower_goal:
        return None

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    lines: list[str] = [f"Analise local de endpoints em {target.as_posix()}:"]
    found_any = False

    for _, method, path in _DECORATOR_RE.findall(content):
        lines.append(f"- {method.upper()} {path}")
        found_any = True

    for _, path in _WS_RE.findall(content):
        lines.append(f"- WebSocket {path}")
        found_any = True

    for prefix in _INCLUDE_ROUTER_RE.findall(content):
        lines.append(f"- Router prefix {prefix}")
        found_any = True

    if not found_any:
        return f"Nenhum endpoint FastAPI encontrado em {target.as_posix()}."

    return "\n".join(lines)


@router.post("/run", response_model=MultiAgentRunResponse, summary="Run multi-agent pipeline")
async def run_multi_agent(body: MultiAgentRunRequest):
    """
    Runs the full FASE 9 multi-agent pipeline for a high-level goal.

    Flow: Planner → Executor(s) → Critic → MemoryAgent → FinalResult.

    Example goal: "crie um CRUD em FastAPI"
    """
    log.info("[agents/run] goal=%d chars session=%s", len(body.goal), body.session_id)
    fallback_output = _fallback_endpoint_analysis(body.goal)
    if fallback_output:
        return MultiAgentRunResponse(
            status="success",
            output=fallback_output,
            tasks=[],
            iterations=1,
            error=None,
        )

    try:
        orch = get_multi_agent_orchestrator(session_id=body.session_id)
        result = await asyncio.wait_for(orch.run(body.goal), timeout=25)
    except asyncio.TimeoutError:
        fallback_output = _fallback_endpoint_analysis(body.goal)
        if fallback_output:
            return MultiAgentRunResponse(
                status="timeout_fallback",
                output=fallback_output,
                tasks=[],
                iterations=1,
                error=None,
            )
        raise HTTPException(status_code=504, detail="Multi-agent timeout")
    except Exception as exc:
        log.exception("[agents/run] pipeline failed")
        raise HTTPException(status_code=503, detail=f"Multi-agent error: {exc}")

    return MultiAgentRunResponse(
        status=result.status,
        output=result.output,
        tasks=[t.model_dump() for t in result.tasks],
        iterations=result.iterations,
        error=result.error,
    )
