"""
critic_agent — FASE 9, Agente 4

The CriticAgent evaluates the output of every execution step and decides
whether to approve it or request a correction.

Responsibilities
----------------
  1. Receives an RESULT message from the Orchestrator with the output of
     a completed task.
  2. Calls the LLM with a structured evaluation prompt to score the result.
  3. Returns FEEDBACK(approved=True/False, reason=str) to the Orchestrator.
  4. On rejection, supplies a concrete correction_hint so the executing agent
     can self-correct without restarting from scratch.

Evaluation criteria (applied via LLM)
--------------------------------------
  - Correctness: does the output satisfy the original goal?
  - Completeness: are all required parts present?
  - Safety: does the output contain dangerous code or operations?
  - Quality: is the code idiomatic, readable, and free of obvious bugs?

Role in the system
------------------
The Orchestrator calls ``critic.evaluate(task, output)`` after each Executor
result. If the critic rejects, the Orchestrator re-queues the task with the
correction hint injected into the context. Max 3 critique–correction cycles.

Usage example
-------------
>>> critic = CriticAgent(llm_fn=call_llm)
>>> feedback = await critic.evaluate(task, executor_output)
>>> if not feedback.payload["approved"]:
...     print("Rejected:", feedback.payload["reason"])
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Callable

import structlog

from services.llm_service import call_llm
from agents.agent_protocol import AgentMessage, MessageType, Task

log: structlog.BoundLogger = structlog.get_logger(__name__)

AGENT_NAME = "critic"

_CRITIC_SYSTEM = """\
You are a strict code and output quality reviewer.
Given a task goal and the agent's output, evaluate it and respond ONLY with valid JSON:
{
  "approved": true|false,
  "score": 0-10,
  "reason": "one sentence",
  "correction_hint": "specific fix needed (empty string if approved)"
}
Rules:
- approved=true only if score >= 7 AND no safety issues.
- correction_hint must be actionable (e.g. "add error handling for DB connection").
- Do NOT add prose outside the JSON object.
"""


class CriticAgent:
    """
    Evaluates agent outputs and approves or requests corrections.

    Parameters
    ----------
    llm_fn:         LLM call function, defaults to the standard ``call_llm``.
    inbox:          Optional queue for message-bus-style usage.
    outbox:         Optional queue for message-bus-style usage.
    """

    def __init__(
        self,
        llm_fn: Callable[..., str] | None = None,
        inbox: asyncio.Queue[AgentMessage] | None = None,
        outbox: asyncio.Queue[AgentMessage] | None = None,
    ) -> None:
        self._llm = llm_fn or call_llm
        self.inbox = inbox
        self.outbox = outbox

    # ── Direct evaluation API ──────────────────────────────────────────────────

    async def evaluate(self, task: Task, output: str) -> AgentMessage:
        """
        Evaluate *output* against the *task* goal.

        Returns an AgentMessage(type=FEEDBACK) with:
          payload["approved"]        : bool
          payload["score"]           : int (0-10)
          payload["reason"]          : str
          payload["correction_hint"] : str
          payload["task_id"]         : str

        Usage example
        -------------
        >>> fb = await critic.evaluate(task, "def add(a, b): return a+b")
        >>> print(fb.payload["approved"], fb.payload["reason"])
        """
        prompt = self._build_prompt(task.goal, output)
        messages = [
            {"role": "system", "content": _CRITIC_SYSTEM},
            {"role": "user",   "content": prompt},
        ]

        raw = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._llm(messages, force_local=True),
        )

        parsed = self._parse_response(raw or "{}")
        approved: bool = parsed.get("approved", False)
        reason:   str  = parsed.get("reason", "No reason provided.")
        hint:     str  = parsed.get("correction_hint", "")
        score:    int  = int(parsed.get("score", 0))

        log.info(
            "critic_agent.evaluated",
            task_id=task.id,
            approved=approved,
            score=score,
            reason=reason,
        )

        return AgentMessage.feedback(
            sender=AGENT_NAME,
            receiver="orchestrator",
            approved=approved,
            reason=reason,
            task_id=task.id,
        )

    # ── Message-bus loop ───────────────────────────────────────────────────────

    async def run(self) -> None:
        """
        Process incoming RESULT messages from the bus until sentinel None.
        Requires inbox and outbox to be set at construction.
        """
        if self.inbox is None or self.outbox is None:
            raise RuntimeError("inbox/outbox must be set for bus-mode operation.")
        log.info("critic_agent.start")
        while True:
            msg: AgentMessage | None = await self.inbox.get()
            if msg is None:
                break
            try:
                goal  = msg.payload.get("goal", "")
                out   = msg.payload.get("output", "")
                task  = Task(id=msg.task_id or "", goal=goal, assignee=msg.sender)
                fb    = await self.evaluate(task, out)
                fb.receiver = msg.sender
                await self.outbox.put(fb)
            except Exception as exc:
                log.error("critic_agent.error", error=str(exc))
                err = AgentMessage.error(
                    sender=AGENT_NAME,
                    receiver=msg.sender,
                    error=str(exc),
                    task_id=msg.task_id,
                )
                await self.outbox.put(err)
            finally:
                self.inbox.task_done()
        log.info("critic_agent.stop")

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _build_prompt(self, goal: str, output: str) -> str:
        return (
            f"Task goal: {goal}\n\n"
            f"Agent output:\n```\n{output[:3000]}\n```\n\n"
            "Evaluate and respond with JSON only."
        )

    def _parse_response(self, raw: str) -> dict[str, Any]:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]+\}", raw)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
        return {"approved": False, "score": 0, "reason": "Parse error", "correction_hint": ""}
