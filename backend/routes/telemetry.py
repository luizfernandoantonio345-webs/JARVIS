from __future__ import annotations

from fastapi import APIRouter, Query

from core.telemetry import get_pipeline_summary, get_pipeline_traces

router = APIRouter()


@router.get("/traces")
async def telemetry_traces(limit: int = Query(default=100, ge=1, le=100)):
    return {"traces": get_pipeline_traces(limit)}


@router.get("/summary")
async def telemetry_summary():
    return get_pipeline_summary()
