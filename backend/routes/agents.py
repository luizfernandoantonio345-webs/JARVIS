"""
/agents routes — multi-agent system API endpoints.

GET  /agents/             → list all registered agents
POST /agents/{role}/run   → invoke a specific agent synchronously
POST /agents/run          → run the full multi-agent pipeline (FASE 9)
"""

from __future__ import annotations

import asyncio
import logging

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


@router.post("/run", response_model=MultiAgentRunResponse, summary="Run multi-agent pipeline")
async def run_multi_agent(body: MultiAgentRunRequest):
    """
    Runs the full FASE 9 multi-agent pipeline for a high-level goal.

    Flow: Planner → Executor(s) → Critic → MemoryAgent → FinalResult.

    Example goal: "crie um CRUD em FastAPI"
    """
    log.info("[agents/run] goal=%d chars session=%s", len(body.goal), body.session_id)
    try:
        orch = get_multi_agent_orchestrator(session_id=body.session_id)
        result = await orch.run(body.goal)
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
