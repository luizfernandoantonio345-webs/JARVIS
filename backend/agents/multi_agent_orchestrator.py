"""
multi_agent_orchestrator — FASE 9

Coordinates a team of specialised agents via an asyncio-based message bus.

Architecture
------------

  Orchestrator
      │
      ├─▶ PlannerAgent    — decompose goal → List[Task]
      ├─▶ ExecutorAgent   — execute a Task using tools
      ├─▶ CriticAgent     — evaluate ExecutorAgent output
      └─▶ MemoryAgent     — serialised read/write for all agents

Communication
-------------
Each agent owns an ``asyncio.Queue`` inbox.  The Orchestrator holds references
to all inboxes and dispatches ``AgentMessage`` objects.  Agents reply by
putting messages on a shared ``outbox`` queue that the Orchestrator monitors.

Stop criteria
-------------
  • All tasks in the plan reach status "done" → FinalResult(status="success")
  • A task exceeds MAX_CRITIC_ROUNDS without approval → status="failed"
  • A security BLOCK message is received → status="failed" immediately

Integration
-----------
The Orchestrator is wired into the FastAPI backend via
``routes/agents.py`` (endpoint POST /agents/run).

Usage example
-------------
>>> from backend.agents.multi_agent_orchestrator import MultiAgentOrchestrator
>>> orch = MultiAgentOrchestrator(session_id="sess-001")
>>> result = await orch.run("crie um CRUD em FastAPI")
>>> print(result.status, result.output)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from core.intent_engine import IntentModel

import structlog

from services.llm_service import call_llm
from agents.agent_protocol import AgentMessage, FinalResult, MessageType, Task
from agents.critic_agent import CriticAgent
from agents.memory_agent import MemoryAgent

log: structlog.BoundLogger = structlog.get_logger(__name__)

MAX_CRITIC_ROUNDS = 3   # max approve/reject cycles per task

# ── Inline Planner (avoids circular import with agents/planner_agent.py) ──────

_PLANNER_SYSTEM = """\
You are a precise multi-agent task planner. Decompose the user goal into
at most 5 subtasks, each assigned to one agent.
Valid assignees: coder, executor, reviewer, security.
Reply ONLY with valid JSON:
{
  "tasks": [
    {"goal": "...", "assignee": "coder",    "priority": 1, "dependencies": []},
    {"goal": "...", "assignee": "reviewer", "priority": 2, "dependencies": ["<id of coder task>"]},
    {"goal": "...", "assignee": "executor", "priority": 3, "dependencies": []}
  ]
}
"""


async def _plan(goal: str, session_id: str) -> list[Task]:
    """Call LLM planner and parse tasks. Falls back to a single executor task."""
    messages = [
        {"role": "system", "content": _PLANNER_SYSTEM},
        {"role": "user",   "content": f"Goal: {goal}"},
    ]
    raw = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: call_llm(messages, force_local=False),
    )
    try:
        data = json.loads(raw or "{}")
        tasks = []
        for t in data.get("tasks", []):
            tasks.append(
                Task(
                    goal=t.get("goal", goal),
                    assignee=t.get("assignee", "executor"),
                    priority=int(t.get("priority", 5)),
                    dependencies=t.get("dependencies", []),
                )
            )
        if tasks:
            return sorted(tasks, key=lambda t: t.priority)
    except Exception as exc:
        log.warning("multi_agent_orchestrator.plan_parse_error", error=str(exc))

    # Fallback: single executor task
    return [Task(goal=goal, assignee="executor", priority=1)]


# ── Inline Executor (delegates to existing executor agent via LLM) ─────────────

_EXECUTOR_SYSTEM = """\
You are an executor agent. Given a task goal, produce the result directly.
For code tasks: write complete, working code.
For shell tasks: describe the command and expected output.
Be concise and complete.
"""


async def _execute_task(task: Task, context: str = "") -> str:
    """Execute a task via LLM and return the result as a string."""
    prompt = f"Task: {task.goal}\n\nContext:\n{context}" if context else f"Task: {task.goal}"
    messages = [
        {"role": "system", "content": _EXECUTOR_SYSTEM},
        {"role": "user",   "content": prompt},
    ]
    result = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: call_llm(messages, force_local=False),
    )
    return result or "(no output)"


# ── Orchestrator ───────────────────────────────────────────────────────────────

class MultiAgentOrchestrator:
    """
    Coordinates planning, execution, critique, and memory across agents.

    Parameters
    ----------
    session_id:   Memory / session scoping key.
    on_event:     Optional real-time event callback (str → None).

    Usage example
    -------------
    >>> orch = MultiAgentOrchestrator(session_id="sess-001")
    >>> result = await orch.run("crie um CRUD em FastAPI")
    >>> print(result.status)
    >>> print(result.output)
    """

    def __init__(
        self,
        session_id: str = "multi-agent",
        on_event: Any = None,
    ) -> None:
        self.session_id = session_id
        self.on_event = on_event

        # Shared outbox: all agents reply here
        self._outbox: asyncio.Queue[AgentMessage] = asyncio.Queue()

        # Memory agent setup
        self._mem_inbox: asyncio.Queue[AgentMessage] = asyncio.Queue()
        self._memory_agent = MemoryAgent(
            inbox=self._mem_inbox,
            outbox=self._outbox,
        )

        # Critic agent setup
        self._critic_inbox: asyncio.Queue[AgentMessage] = asyncio.Queue()
        self._critic_agent = CriticAgent(
            inbox=self._critic_inbox,
            outbox=self._outbox,
        )

    def _emit(self, msg: str) -> None:
        log.info("orchestrator", msg=msg)
        if self.on_event:
            self.on_event(msg)

    async def run(self, goal: str) -> FinalResult:
        """
        Execute the full multi-agent pipeline for *goal*.

        Flow:
          1. Start background agents (memory, critic).
          2. Call LLM planner → List[Task].
          3. For each task (respecting dependencies):
             a. Execute via executor.
             b. Send result to critic for evaluation.
             c. On rejection: retry with correction hint (max 3 rounds).
          4. Compile FinalResult.

        Returns FinalResult with status, output, task list, and iteration count.
        """
        run_id = str(uuid4())[:8]
        t0 = time.monotonic()
        self._emit(f"🤖 Orchestrator starting | goal={goal} | run_id={run_id}")

        # Start background agents
        mem_task  = asyncio.create_task(self._memory_agent.run())
        crit_task = asyncio.create_task(self._critic_agent.run())

        try:
            result = await self._run_pipeline(goal, run_id)
        finally:
            await self._memory_agent.stop()
            await self._critic_agent.inbox.put(None)  # type: ignore[arg-type]
            try:
                await asyncio.wait_for(asyncio.gather(mem_task, crit_task), timeout=5)
            except asyncio.TimeoutError:
                pass

        duration = round(time.monotonic() - t0, 2)
        self._emit(f"✅ Orchestrator done | status={result.status} | {duration}s")
        return result

    async def run_with_intent(self, goal: str, intent: "IntentModel") -> FinalResult:
        """
        Run the multi-agent pipeline with an IntentModel for enriched planning.

        Injects intent subgoals, constraints, and expected outputs into the
        planner prompt so that the task decomposition aligns with the
        structured intent extracted by the Intent Engine (FASE 1).

        Parameters
        ----------
        goal:   Raw or enriched goal string (passed through to planner).
        intent: IntentModel from intent_engine.extract_intent().
        """
        # Build an enriched goal that incorporates structured intent data
        enriched_parts: list[str] = [goal]

        if intent.subgoals:
            steps = "; ".join(intent.subgoals)
            enriched_parts.append(f"Required steps: {steps}")

        if intent.constraints:
            enriched_parts.append(f"Constraints: {', '.join(intent.constraints)}")

        if intent.expected_outputs:
            enriched_parts.append(f"Expected outputs: {', '.join(intent.expected_outputs)}")

        enriched_goal = "\n".join(enriched_parts)
        self._emit(f"run_with_intent | domain={intent.domain} | subgoals={len(intent.subgoals)}")
        return await self.run(enriched_goal)

        # Start background agents
        mem_task  = asyncio.create_task(self._memory_agent.run())
        crit_task = asyncio.create_task(self._critic_agent.run())

        try:
            result = await self._run_pipeline(goal, run_id)
        finally:
            await self._memory_agent.stop()
            await self._critic_agent.inbox.put(None)  # type: ignore[arg-type]
            try:
                await asyncio.wait_for(asyncio.gather(mem_task, crit_task), timeout=5)
            except asyncio.TimeoutError:
                pass

        duration = round(time.monotonic() - t0, 2)
        self._emit(f"✅ Orchestrator done | status={result.status} | {duration}s")
        return result

    async def _run_pipeline(self, goal: str, run_id: str) -> FinalResult:
        # 1. Plan
        self._emit("Planning…")
        tasks = await _plan(goal, self.session_id)
        self._emit(f"Plan: {len(tasks)} task(s)")
        for t in tasks:
            self._emit(f"  [{t.assignee}] {t.goal}")

        # Track completed task ids → result string (for dependency context)
        completed: dict[str, str] = {}
        all_outputs: list[str] = []

        for task in tasks:
            # Wait for dependencies
            dep_context = ""
            for dep_id in task.dependencies:
                if dep_id in completed:
                    dep_context += f"\nPrevious result ({dep_id}):\n{completed[dep_id]}\n"

            self._emit(f"▶ Executing [{task.assignee}]: {task.goal}")
            task.status = "running"

            output = ""
            approved = False
            reason = ""

            for attempt in range(1, MAX_CRITIC_ROUNDS + 1):
                # Inject correction hint on retries
                context = dep_context
                if attempt > 1 and reason:
                    context += f"\nCorrection needed: {reason}\n"

                output = await _execute_task(task, context)
                self._emit(f"  Attempt {attempt}/{MAX_CRITIC_ROUNDS} — output length={len(output)}")

                # Critique
                critic_msg = AgentMessage(
                    sender="orchestrator",
                    receiver="critic",
                    type=MessageType.RESULT,
                    payload={"goal": task.goal, "output": output},
                    task_id=task.id,
                )
                await self._critic_inbox.put(critic_msg)
                feedback = await asyncio.wait_for(self._outbox.get(), timeout=30)

                approved = bool(feedback.payload.get("approved", False))
                reason   = feedback.payload.get("reason", "")
                hint     = feedback.payload.get("correction_hint", "")
                self._emit(f"  Critic: approved={approved} reason={reason}")

                if approved:
                    break
                # Re-queue with correction hint
                reason = hint or reason

            task.status = "done" if approved else "failed"
            task.result = output
            completed[task.id] = output
            all_outputs.append(f"[{task.assignee}] {task.goal}\n{output}")

            # Persist to memory
            await self._mem_inbox.put(AgentMessage(
                sender="orchestrator",
                receiver="memory",
                type=MessageType.MEMORY,
                payload={
                    "op": "write_episodic",
                    "session_id": self.session_id,
                    "message": f"task: {task.goal}",
                    "response": output[:1000],
                    "action": f"agent_{task.assignee}",
                },
                task_id=task.id,
            ))

        # Compile final result
        all_done = all(t.status == "done" for t in tasks)
        final_output = "\n\n---\n\n".join(all_outputs)

        return FinalResult(
            goal=goal,
            status="success" if all_done else "partial",
            output=final_output,
            tasks=tasks,
            iterations=len(tasks),
        )


# ── Module-level factory ───────────────────────────────────────────────────────

def get_multi_agent_orchestrator(session_id: str = "multi-agent") -> MultiAgentOrchestrator:
    """Return a fresh MultiAgentOrchestrator (not cached — each run is stateless)."""
    return MultiAgentOrchestrator(session_id=session_id)
