"""
Tasks router — goal-based autonomous execution API.

Endpoints:
  POST   /tasks                       create a goal → decompose → run async
  GET    /tasks/{session_id}          list tasks for a session
  GET    /tasks/detail/{task_id}      get full task state
  DELETE /tasks/{task_id}             delete a task
  POST   /tasks/{task_id}/run         re-run a failed / pending task
"""

from __future__ import annotations

import logging
import threading

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from services.task_manager import (
    TaskState,
    create_task,
    get_task,
    list_tasks,
    delete_task,
    run_task,
    build_task_report,
    is_autonomous_goal,
)

log = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────────

class TaskCreateRequest(BaseModel):
    goal:       str = Field(..., min_length=5, max_length=2000)
    session_id: str = "default"
    run_now:    bool = True   # if False, just create (PENDING); if True, run in background


class TaskCreateResponse(BaseModel):
    task_id:    str
    session_id: str
    state:      str
    total_steps: int
    message:    str


# ── Background runner ──────────────────────────────────────────────────────────

def _run_in_background(task_id: str) -> None:
    """Execute all task steps in a daemon thread (non-blocking for the API)."""
    try:
        run_task(task_id)
    except Exception as exc:
        log.error("Background task runner failed for %s: %s", task_id[:8], exc)


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("", response_model=TaskCreateResponse)
def create(req: TaskCreateRequest, background_tasks: BackgroundTasks):
    """
    Decompose the goal into steps and optionally start execution in the background.
    Returns immediately with the task ID and initial state.
    """
    task = create_task(req.session_id, req.goal)

    if req.run_now:
        background_tasks.add_task(_run_in_background, task.id)
        msg = f"Task created with {len(task.steps)} steps and is running in the background."
    else:
        msg = f"Task created with {len(task.steps)} steps. Use POST /tasks/{task.id}/run to start."

    return TaskCreateResponse(
        task_id=task.id,
        session_id=task.session_id,
        state=task.state.value,
        total_steps=len(task.steps),
        message=msg,
    )


@router.get("/{session_id}")
def get_session_tasks(session_id: str, limit: int = 20):
    """List all tasks for a session, newest first."""
    tasks = list_tasks(session_id, limit=limit)
    return {
        "session_id": session_id,
        "total":      len(tasks),
        "tasks":      [t.to_dict() for t in tasks],
    }


@router.get("/detail/{task_id}")
def get_task_detail(task_id: str):
    """Full task state including step results."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id!r} not found")
    return task.to_dict()


@router.get("/report/{task_id}")
def get_task_report(task_id: str):
    """Human-readable markdown report for the task."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id!r} not found")
    return {"task_id": task_id, "state": task.state.value, "report": build_task_report(task)}


@router.post("/{task_id}/run")
def run(task_id: str, background_tasks: BackgroundTasks):
    """
    Start or resume a PENDING or FAILED task.
    Runs in the background; poll GET /tasks/detail/{task_id} for progress.
    """
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id!r} not found")
    if task.state == TaskState.IN_PROGRESS:
        return {"message": "Task is already running.", "state": task.state.value}
    if task.state == TaskState.COMPLETED:
        return {"message": "Task already completed.", "state": task.state.value}

    # Reset current_step to 0 for FAILED tasks so they restart from the top
    if task.state == TaskState.FAILED:
        task.current_step = 0
        from services.task_manager import _persist
        _persist(task)

    background_tasks.add_task(_run_in_background, task_id)
    return {"message": "Task started.", "task_id": task_id, "state": "in_progress"}


@router.delete("/{task_id}")
def delete(task_id: str):
    """Delete a task and its step data."""
    deleted = delete_task(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Task {task_id!r} not found")
    return {"deleted": task_id}
