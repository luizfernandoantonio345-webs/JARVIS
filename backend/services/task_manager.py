"""
Task Manager — goal-based autonomous execution engine.

Flow:
  1. User states a high-level goal ("Build a website for a mechanic")
  2. GoalDecomposer breaks it into ordered ActionSteps via LLM
  3. TaskRunner executes each step sequentially using the existing plan/executor pipeline
  4. State is persisted in SQLite (reuses the memory DB connection)
  5. Progress is reported after each step; the final summary is stored in project_context

TaskState machine:
  PENDING → IN_PROGRESS → COMPLETED
                        ↘ FAILED (after all retries exhausted)

Limits:
  - MAX_GOAL_STEPS = 8 (prevents runaway decomposition)
  - MAX_STEP_RETRIES = 2 (mirrors executor.py)
  - No infinite loops: a failed task stays FAILED; must be explicitly re-run
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable

from config import get_config

log = logging.getLogger(__name__)

_DB_PATH   = get_config().memory_db_path
_lock      = threading.Lock()
MAX_GOAL_STEPS   = 8
MAX_STEP_RETRIES = 2

# ── State ──────────────────────────────────────────────────────────────────────

class TaskState(str, Enum):
    PENDING     = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED   = "completed"
    FAILED      = "failed"


@dataclass
class ActionStep:
    description: str
    action:      str = "chat"    # maps to a registered action name
    result:      str = ""
    success:     bool = False
    attempts:    int  = 0


@dataclass
class Task:
    id:           str
    session_id:   str
    goal:         str
    steps:        list[ActionStep] = field(default_factory=list)
    current_step: int              = 0
    state:        TaskState        = TaskState.PENDING
    created_at:   str              = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at:   str              = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def is_done(self) -> bool:
        return self.state in (TaskState.COMPLETED, TaskState.FAILED)

    @property
    def progress_pct(self) -> int:
        if not self.steps:
            return 0
        done = sum(1 for s in self.steps if s.success)
        return int(done / len(self.steps) * 100)

    def to_dict(self) -> dict:
        return {
            "id":           self.id,
            "session_id":   self.session_id,
            "goal":         self.goal,
            "state":        self.state.value,
            "current_step": self.current_step,
            "total_steps":  len(self.steps),
            "progress_pct": self.progress_pct,
            "created_at":   self.created_at,
            "updated_at":   self.updated_at,
            "steps": [
                {
                    "index":       i,
                    "description": s.description,
                    "action":      s.action,
                    "success":     s.success,
                    "attempts":    s.attempts,
                    "result_preview": s.result[:200] if s.result else "",
                }
                for i, s in enumerate(self.steps)
            ],
        }


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id           TEXT PRIMARY KEY,
            session_id   TEXT NOT NULL,
            goal         TEXT NOT NULL,
            steps_json   TEXT NOT NULL DEFAULT '[]',
            current_step INTEGER DEFAULT 0,
            state        TEXT DEFAULT 'pending',
            created_at   TEXT,
            updated_at   TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_session ON tasks(session_id)")
    conn.commit()
    return conn


_conn = _get_conn()


def _persist(task: Task) -> None:
    task.updated_at = datetime.now(timezone.utc).isoformat()
    steps_json = json.dumps([
        {
            "description": s.description,
            "action":      s.action,
            "result":      s.result,
            "success":     s.success,
            "attempts":    s.attempts,
        }
        for s in task.steps
    ])
    with _lock:
        _conn.execute(
            """INSERT OR REPLACE INTO tasks
               (id, session_id, goal, steps_json, current_step, state, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task.id, task.session_id, task.goal, steps_json,
                task.current_step, task.state.value,
                task.created_at, task.updated_at,
            ),
        )
        _conn.commit()


def _load(row: tuple) -> Task:
    (task_id, session_id, goal, steps_json, current_step, state, created_at, updated_at) = row
    steps_data = json.loads(steps_json or "[]")
    steps = [
        ActionStep(
            description=s["description"],
            action=s.get("action", "chat"),
            result=s.get("result", ""),
            success=s.get("success", False),
            attempts=s.get("attempts", 0),
        )
        for s in steps_data
    ]
    return Task(
        id=task_id,
        session_id=session_id,
        goal=goal,
        steps=steps,
        current_step=current_step,
        state=TaskState(state),
        created_at=created_at or "",
        updated_at=updated_at or "",
    )


# ── Goal Decomposer ────────────────────────────────────────────────────────────

_DECOMPOSE_SYSTEM = f"""\
You are an autonomous task planner for an AI assistant called JARVIS.
The user has given you a high-level goal. Break it into concrete, sequential,
executable sub-tasks.

Rules:
- Reply with ONLY a valid JSON array — no prose, no markdown fences.
- Each element: {{"description": "<what to do>", "action": "<action>"}}
- Valid actions: analyze, arch, run, explain, refactor, web_search,
  github_analyze, file_reader, system_monitor, chat
- Use the most specific action. Default to "chat" only if nothing fits.
- Maximum {MAX_GOAL_STEPS} steps. Minimum 2 steps.
- Steps must be ordered: each step should logically follow the previous.
- Each description must be self-contained (no "do the previous step" references).

Example for goal "Build a FastAPI todo API":
[
  {{"description": "Design the REST API schema and endpoints for a todo app", "action": "arch"}},
  {{"description": "Write Python FastAPI code for the todo API with SQLite", "action": "run"}},
  {{"description": "Analyze the generated code for security and quality issues", "action": "analyze"}}
]\
"""


def decompose_goal(goal: str) -> list[ActionStep]:
    """
    Use the LLM to break a goal string into ordered ActionSteps.
    Falls back to a single chat step on any failure.
    """
    from services.llm_service import call_llm
    from actions.action_loader import list_actions

    messages = [
        {"role": "system", "content": _DECOMPOSE_SYSTEM},
        {"role": "user",   "content": f"Goal: {goal}"},
    ]
    try:
        raw     = call_llm(messages, force_api=True)
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
        data    = json.loads(cleaned)
        if not isinstance(data, list) or not data:
            raise ValueError("Empty or non-list response")

        valid_actions = set(list_actions())
        steps: list[ActionStep] = []
        for item in data[:MAX_GOAL_STEPS]:
            if not isinstance(item, dict):
                continue
            action = str(item.get("action", "chat")).strip().lower()
            if action not in valid_actions:
                action = "chat"
            desc = str(item.get("description", goal)).strip()
            if desc:
                steps.append(ActionStep(description=desc, action=action))

        return steps if steps else [ActionStep(description=goal, action="chat")]
    except Exception as exc:
        log.warning("Goal decomposition failed: %s — single-step fallback", exc)
        return [ActionStep(description=goal, action="chat")]


# ── Task CRUD ──────────────────────────────────────────────────────────────────

def create_task(session_id: str, goal: str) -> Task:
    """Decompose goal into steps and persist the task as PENDING."""
    task = Task(
        id=str(uuid.uuid4()),
        session_id=session_id,
        goal=goal,
        steps=decompose_goal(goal),
        state=TaskState.PENDING,
    )
    _persist(task)
    log.info("Task created [%s] %d steps for goal: %s", task.id[:8], len(task.steps), goal[:60])
    return task


def get_task(task_id: str) -> Task | None:
    row = _conn.execute(
        "SELECT id, session_id, goal, steps_json, current_step, state, created_at, updated_at "
        "FROM tasks WHERE id = ?",
        (task_id,),
    ).fetchone()
    return _load(row) if row else None


def list_tasks(session_id: str, limit: int = 20) -> list[Task]:
    rows = _conn.execute(
        "SELECT id, session_id, goal, steps_json, current_step, state, created_at, updated_at "
        "FROM tasks WHERE session_id = ? ORDER BY updated_at DESC LIMIT ?",
        (session_id, limit),
    ).fetchall()
    return [_load(r) for r in rows]


def delete_task(task_id: str) -> bool:
    with _lock:
        cur = _conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        _conn.commit()
    return cur.rowcount > 0


# ── Step runner ────────────────────────────────────────────────────────────────

def _run_one_step(task: Task, step: ActionStep, session_id: str) -> bool:
    """
    Execute a single ActionStep. Updates step.result/success/attempts in-place.
    Returns True on success.
    """
    from services.planner import Step as PlanStep, Plan
    from services.executor import execute_plan
    from services.session_store import get_history

    plan_step = PlanStep(action=step.action, input=step.description)
    plan      = Plan(steps=[plan_step])
    session_messages = list(get_history(session_id))

    for attempt in range(1, MAX_STEP_RETRIES + 1):
        step.attempts = attempt
        try:
            result = execute_plan(plan, session_messages, session_id=session_id)
            step.result  = result.final_response
            step.success = True
            log.debug("Task step OK [attempt %d]: %s", attempt, step.description[:60])
            return True
        except Exception as exc:
            log.warning("Task step attempt %d failed: %s — %s", attempt, step.description[:60], exc)
            step.result = f"❌ Attempt {attempt} failed: {exc}"
            if attempt == MAX_STEP_RETRIES:
                step.success = False
                return False

    return False


def run_task(
    task_id: str,
    progress_callback: Callable[[Task, int, str], None] | None = None,
) -> Task:
    """
    Execute all remaining steps of a task sequentially.

    progress_callback(task, step_index, step_result) is called after each step.
    The task is persisted after every step so state is never lost on crash.

    Returns the updated Task object.
    """
    task = get_task(task_id)
    if task is None:
        raise ValueError(f"Task {task_id!r} not found")
    if task.is_done:
        log.info("Task %s already %s — skipping", task_id[:8], task.state)
        return task

    task.state = TaskState.IN_PROGRESS
    _persist(task)

    for i in range(task.current_step, len(task.steps)):
        step = task.steps[i]
        log.info(
            "Task [%s] step %d/%d [%s]: %s",
            task.id[:8], i + 1, len(task.steps), step.action, step.description[:60],
        )

        success = _run_one_step(task, step, task.session_id)
        task.current_step = i + 1

        if progress_callback:
            try:
                progress_callback(task, i, step.result)
            except Exception as exc:
                log.debug("[services.task_manager] suppressed exception", exc_info=exc)
                pass

        _persist(task)

        if not success:
            log.error(
                "Task [%s] step %d failed — marking task FAILED", task.id[:8], i + 1
            )
            task.state = TaskState.FAILED
            _persist(task)
            return task

    # All steps completed
    task.state = TaskState.COMPLETED
    _persist(task)

    # Store a summary in project_context memory
    _store_task_summary(task)

    log.info("Task [%s] COMPLETED (%d steps)", task.id[:8], len(task.steps))
    return task


def _store_task_summary(task: Task) -> None:
    """Write the completed task's outcome into project_context memory."""
    try:
        from services.memory_service import set_project_context
        results_text = "\n".join(
            f"Step {i+1} ({s.action}): {s.description[:80]} → "
            + ("✅" if s.success else "❌")
            for i, s in enumerate(task.steps)
        )
        set_project_context(
            task.session_id,
            f"completed_task_{task.id[:8]}",
            f"Goal: {task.goal}\n{results_text}",
        )
    except Exception as exc:
        log.warning("Failed to store task summary in memory: %s", exc)


def build_task_report(task: Task) -> str:
    """Format a human-readable progress/completion report for the chat UI."""
    if task.state == TaskState.PENDING:
        steps_list = "\n".join(
            f"  {i+1}. [{s.action}] {s.description}"
            for i, s in enumerate(task.steps)
        )
        return (
            f"## 📋 Task Created\n\n"
            f"**Goal:** {task.goal}\n\n"
            f"**Steps planned ({len(task.steps)}):**\n{steps_list}\n\n"
            f"Task ID: `{task.id[:8]}`\n"
            f"Use the Tasks panel to run this task, or it will run automatically."
        )

    if task.state == TaskState.IN_PROGRESS:
        done  = sum(1 for s in task.steps if s.success)
        total = len(task.steps)
        bar   = "█" * done + "░" * (total - done)
        return (
            f"## ⚙️ Task In Progress\n\n"
            f"**Goal:** {task.goal}\n\n"
            f"Progress: [{bar}] {done}/{total} steps ({task.progress_pct}%)"
        )

    if task.state == TaskState.COMPLETED:
        parts = [f"## ✅ Task Completed\n\n**Goal:** {task.goal}\n"]
        for i, s in enumerate(task.steps):
            status = "✅" if s.success else "❌"
            parts.append(f"### Step {i+1}: {s.description}\n")
            parts.append(f"**Action:** `{s.action}` {status}\n")
            if s.result:
                preview = s.result[:400] + ("..." if len(s.result) > 400 else "")
                parts.append(f"{preview}\n")
        return "\n".join(parts)

    # FAILED
    failed_step = next((s for s in task.steps if not s.success), None)
    reason = failed_step.result if failed_step else "Unknown error"
    return (
        f"## ❌ Task Failed\n\n"
        f"**Goal:** {task.goal}\n\n"
        f"**Failed at:** step {task.current_step}/{len(task.steps)}\n\n"
        f"**Reason:** {reason[:300]}"
    )


# ── Goal detection heuristic ───────────────────────────────────────────────────

_GOAL_PATTERNS = re.compile(
    r"\b(build|create|make|develop|implement|design and build|set up|"
    r"generate|write a complete|deploy|automate)\b",
    re.IGNORECASE,
)

_MIN_GOAL_LEN = 20  # short messages are usually questions, not goals


def is_autonomous_goal(message: str) -> bool:
    """
    Heuristic: True when the message looks like a multi-step goal
    rather than a single question or task.
    """
    if len(message.strip()) < _MIN_GOAL_LEN:
        return False
    return bool(_GOAL_PATTERNS.search(message))
