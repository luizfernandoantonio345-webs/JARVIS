"""
profiling route — Performance profiling endpoints  (FASE 13F)

GET  /profiling/report           — full performance report
GET  /profiling/llm              — LLM call stats
GET  /profiling/agents           — agent execution stats
GET  /profiling/requests         — HTTP request stats
GET  /profiling/slow-queries     — slowest SQLite queries
POST /profiling/flamegraph       — trigger py-spy flamegraph (async)
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, Query

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/report")
async def profiling_report(window_minutes: int = Query(default=60, ge=1, le=1440)) -> dict:
    from core.profiler import get_full_report
    return get_full_report(window_minutes)


@router.get("/llm")
async def llm_stats(window_minutes: int = Query(default=60, ge=1, le=1440)) -> dict:
    from core.profiler import get_llm_stats
    return get_llm_stats(window_minutes)


@router.get("/agents")
async def agent_stats(window_minutes: int = Query(default=60, ge=1, le=1440)) -> dict:
    from core.profiler import get_agent_stats
    return get_agent_stats(window_minutes)


@router.get("/requests")
async def request_stats(window_minutes: int = Query(default=60, ge=1, le=1440)) -> dict:
    from core.profiler import get_request_stats
    return get_request_stats(window_minutes)


@router.get("/slow-queries")
async def slow_queries(limit: int = Query(default=20, ge=1, le=100)) -> dict:
    from core.profiler import SQLiteProfiler
    return {"slow_queries": SQLiteProfiler.get_slow_queries(limit)}


@router.post("/flamegraph")
async def trigger_flamegraph(duration_s: int = Query(default=30, ge=5, le=120)) -> dict:
    """
    Trigger a py-spy flamegraph for the current process.
    Runs for duration_s seconds (5–120).  Returns path to the SVG file.
    """
    from core.profiler import generate_flamegraph
    return await generate_flamegraph(duration_s)
