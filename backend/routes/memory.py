"""
Memory admin routes — inspect and manage the three memory tiers.

GET  /memory/{session_id}            — all memory for a session
GET  /memory/{session_id}/preferences — tier 2: user preferences
GET  /memory/{session_id}/project     — tier 3: project context
POST /memory/{session_id}/project     — upsert a project context entry
DELETE /memory/{session_id}          — clear all tiers for a session
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.memory_service import (
    get_memory,
    get_preferences,
    get_project_context,
    set_project_context,
    clear_memory,
    get_session_list,
    get_recent_failures,
    resolve_failure,
)
from memory.semantic_engine import SemanticMemory
from expertise.domain_memory import DomainMemory

router = APIRouter()


class ProjectContextRequest(BaseModel):
    name: str
    content: str


class SemanticAddRequest(BaseModel):
    content: str
    metadata: dict = {}


@router.get("")
def list_sessions():
    return {"sessions": get_session_list()}


@router.get("/search")
async def semantic_search(q: str, top_k: int = 5):
    results = await SemanticMemory().search(q, top_k=top_k)
    return {"query": q, "results": results}


@router.post("/semantic")
async def add_semantic_memory(body: SemanticAddRequest):
    memory_id = await SemanticMemory().add(body.content, body.metadata)
    return {"status": "ok", "id": memory_id}


@router.get("/domains")
async def memory_domains():
    return {"domains": await DomainMemory().list_known_domains(), "stats": await DomainMemory().get_stats()}


@router.get("/stats")
async def memory_stats():
    return await SemanticMemory().stats()


@router.post("/consolidate")
async def consolidate_memory():
    return await MemoryLifecycle().consolidate()


@router.get("/{session_id}")
def get_session_memory(session_id: str, limit: int = 20):
    return {
        "session_id":      session_id,
        "episodic":        [{"message": m, "response": r} for m, r in get_memory(session_id, limit)],
        "preferences":     get_preferences(session_id),
        "project_context": get_project_context(session_id),
    }


@router.get("/{session_id}/preferences")
def get_session_preferences(session_id: str):
    return {"session_id": session_id, "preferences": get_preferences(session_id)}


@router.get("/{session_id}/project")
def get_session_project(session_id: str):
    return {"session_id": session_id, "project_context": get_project_context(session_id)}


@router.post("/{session_id}/project")
def upsert_project_context(session_id: str, body: ProjectContextRequest):
    set_project_context(session_id, body.name, body.content)
    return {"status": "ok", "name": body.name}


@router.delete("/{session_id}")
async def delete_session_memory(session_id: str):
    if await SemanticMemory().delete(session_id):
        return {"status": "ok", "deleted": session_id, "type": "semantic_memory"}
    clear_memory(session_id)
    return {"status": "ok", "session_id": session_id, "type": "session_memory"}


# ── Failure memory ─────────────────────────────────────────────────────────────

@router.get("/failures")
def list_failures(limit: int = 20):
    """Return the most recent unresolved (and resolved) failures across sessions."""
    return {"failures": get_recent_failures(limit)}


@router.post("/failures/{failure_id}/resolve")
def mark_failure_resolved(failure_id: int):
    """Manually mark a failure as resolved."""
    resolve_failure(failure_id)
    return {"status": "ok", "failure_id": failure_id}
