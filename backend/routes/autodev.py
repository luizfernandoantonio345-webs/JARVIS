"""
/autodev routes — FASE 10 AutoDev Engine API

POST /autodev/start            → start or resume an AutoDev job
GET  /autodev/status/{job_id}  → poll job status
WS   /autodev/stream/{job_id}  → real-time progress via WebSocket

WebSocket event schema:
  { "event": str, "data": {...}, "ts": float, "job_id": str }

Events emitted:
  stage_start      — pipeline stage began
  file_generated   — a source file was written
  validation_error — a specific error was detected in a file
  fix_attempt      — one LLM fix attempt for a file
  done             — job completed successfully
  escalated        — job completed but some errors could not be fixed
  error            — job failed with an unhandled exception
  heartbeat        — keepalive (no-op for clients)
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from autodev.loop import (
    create_job,
    find_in_progress_job,
    get_job,
    AutoDevLoop,
    JobStatus,
)

log = logging.getLogger(__name__)
router = APIRouter()


# ── Request / Response models ──────────────────────────────────────────────────

class StartJobRequest(BaseModel):
    goal: str = Field(..., min_length=1, max_length=4000,
                      description="High-level project goal")
    constraints: dict = Field(default_factory=dict,
                              description="Optional constraints (language, framework, etc.)")


class StartJobResponse(BaseModel):
    job_id: str
    status: str
    workspace: str
    resumed: bool = False


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    stack: str = ""
    files_generated: int = 0
    files_completed: list = Field(default_factory=list)
    errors_found: int = 0
    errors_fixed: int = 0
    escalation_count: int = 0
    unresolved_errors: list = Field(default_factory=list)
    final_output_dir: str = ""
    error: str = ""
    resumed: bool = False


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/start", response_model=StartJobResponse, summary="Start or resume AutoDev job")
async def start_autodev(body: StartJobRequest):
    """
    Start a new AutoDev job, or resume an in-progress one with the same goal.

    If a job with the same goal is currently in progress (not completed/failed),
    returns that job's id with ``resumed: true`` instead of creating a new one.

    The pipeline runs asynchronously. Use:
    - ``GET /autodev/status/{job_id}`` to poll progress
    - ``WS  /autodev/stream/{job_id}`` for real-time events
    """
    # ── Resume check ──────────────────────────────────────────────────────────
    existing = find_in_progress_job(body.goal)
    if existing is not None:
        log.info("[autodev/start] resuming job_id=%s", existing.job_id)
        # Restart the pipeline in background (it will detect the existing state)
        asyncio.create_task(existing.run(body.goal, body.constraints))
        return StartJobResponse(
            job_id=existing.job_id,
            status="resuming",
            workspace=str(existing.workspace),
            resumed=True,
        )

    # ── New job ───────────────────────────────────────────────────────────────
    job = create_job()
    log.info("[autodev/start] new job_id=%s goal=%d chars", job.job_id, len(body.goal))
    asyncio.create_task(job.run(body.goal, body.constraints))

    return StartJobResponse(
        job_id=job.job_id,
        status="pending",
        workspace=str(job.workspace),
        resumed=False,
    )


@router.get("/status/{job_id}", response_model=JobStatusResponse,
            summary="Get AutoDev job status")
def get_autodev_status(job_id: str):
    """
    Return the current status of an AutoDev job.

    Reads the persisted ``state.json`` from the job workspace.
    Works for completed jobs too (state is persisted to disk).
    """
    from autodev.loop import JOBS_BASE_DIR, JobState

    job = get_job(job_id)
    if job is not None:
        state_dict = job.get_status()
    else:
        workspace = JOBS_BASE_DIR / job_id
        state = JobState.load(workspace)
        if state is None:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
        from dataclasses import asdict
        state_dict = asdict(state)

    valid_keys = set(JobStatusResponse.model_fields)
    return JobStatusResponse(**{k: state_dict.get(k, "") for k in valid_keys})


@router.websocket("/stream/{job_id}")
async def stream_autodev(websocket: WebSocket, job_id: str):
    """
    WebSocket endpoint: streams real-time progress events for an AutoDev job.

    Each message is a JSON object:
      { "event": str, "data": {...}, "ts": float, "job_id": str }

    Terminal events: "done", "escalated", "error" — stream closes after these.

    Example client (JavaScript):
    ```js
    const ws = new WebSocket(`ws://localhost:8000/autodev/stream/${jobId}`);
    ws.onmessage = (e) => console.log(JSON.parse(e.data));
    ```
    """
    await websocket.accept()
    log.info("[autodev/stream] job_id=%s connected", job_id)

    job = get_job(job_id)
    if job is None:
        await websocket.send_json({"error": f"Job '{job_id}' not found or not active."})
        await websocket.close()
        return

    _TERMINAL = {"done", "escalated", "error"}

    try:
        while True:
            try:
                evt: dict = await asyncio.wait_for(job._events.get(), timeout=30)
            except asyncio.TimeoutError:
                await websocket.send_json({
                    "event": "heartbeat", "job_id": job_id, "ts": 0
                })
                continue

            # Sentinel from loop.stream()
            if evt.get("event") == "__DONE__":
                break

            await websocket.send_json(evt)

            if evt.get("event") in _TERMINAL:
                break

    except WebSocketDisconnect:
        log.info("[autodev/stream] job_id=%s disconnected", job_id)

