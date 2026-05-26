"""
memory_agent — FASE 9, Agente 3

The MemoryAgent centralises all read/write operations for the multi-agent
system.  Other agents never touch the MemoryService directly — they send
``AgentMessage(type=MessageType.MEMORY)`` requests and receive
``AgentMessage(type=MessageType.CONTEXT)`` responses.

Benefits
--------
  • Single writer → no concurrent-write conflicts on the SQLite store.
  • Centralised logging of every read/write (audit trail).
  • Future: swappable backend (vector DB, Redis) without touching agents.

Supported payload operations
-----------------------------
  read_episodic  : {"op": "read_episodic",  "session_id": str, "query": str}
  write_episodic : {"op": "write_episodic", "session_id": str, "message": str, "response": str, "action": str}
  read_prefs     : {"op": "read_prefs",     "session_id": str, "query": str}
  write_pref     : {"op": "write_pref",     "session_id": str, "key": str, "value": str, "confidence": float}
  read_project   : {"op": "read_project",   "session_id": str, "name": str}
  write_project  : {"op": "write_project",  "session_id": str, "name": str, "value": str}
  get_context    : {"op": "get_context",    "session_id": str, "action_type": str}

Role in the system
------------------
Started as a coroutine by the multi-agent Orchestrator.
All agents send to "memory" receiver; this agent processes the queue and
sends context back.

Usage example
-------------
>>> # The orchestrator wires the memory agent into the bus automatically.
>>> # Agents use it like this:
>>> request = AgentMessage.memory_read("planner", "sess-1", "what stack does the user prefer?")
>>> await bus.publish(request)
>>> response = await bus.consume_one("planner", MessageType.CONTEXT)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import structlog

from backend.services import memory_service as mem
from backend.services.memory_service import (
    save_memory,
    get_relevant_memory,
    set_preference,
    get_preferences,
    get_relevant_preferences,
    set_project_context,
    get_project_context,
    build_context_for_task,
)
from agents.agent_protocol import AgentMessage, MessageType

log: structlog.BoundLogger = structlog.get_logger(__name__)

AGENT_NAME = "memory"


class MemoryAgent:
    """
    Async coroutine-based agent that serialises all memory I/O.

    Parameters
    ----------
    inbox:   asyncio.Queue receiving AgentMessage objects addressed to "memory".
    outbox:  asyncio.Queue the agent pushes context responses onto.
    """

    def __init__(
        self,
        inbox: asyncio.Queue[AgentMessage],
        outbox: asyncio.Queue[AgentMessage],
    ) -> None:
        self.inbox = inbox
        self.outbox = outbox
        self._running = False

    async def run(self) -> None:
        """
        Process incoming memory requests until the inbox receives a sentinel
        ``None``.  Runs as a long-lived coroutine inside the Orchestrator.
        """
        self._running = True
        log.info("memory_agent.start")
        while self._running:
            msg: AgentMessage | None = await self.inbox.get()
            if msg is None:
                break
            try:
                response = await self._handle(msg)
                if response:
                    await self.outbox.put(response)
            except Exception as exc:
                log.error("memory_agent.error", error=str(exc), msg_id=msg.id)
                err_resp = AgentMessage.error(
                    sender=AGENT_NAME,
                    receiver=msg.sender,
                    error=str(exc),
                    task_id=msg.task_id,
                )
                await self.outbox.put(err_resp)
            finally:
                self.inbox.task_done()
        log.info("memory_agent.stop")

    async def stop(self) -> None:
        self._running = False
        await self.inbox.put(None)  # type: ignore[arg-type]

    # ── Internal handlers ──────────────────────────────────────────────────────

    async def _handle(self, msg: AgentMessage) -> AgentMessage | None:
        op = msg.payload.get("op", "")
        session_id: str = msg.payload.get("session_id", "default")

        log.debug("memory_agent.op", op=op, sender=msg.sender, session_id=session_id)

        if op == "write_episodic":
            save_memory(
                session_id=session_id,
                message=msg.payload.get("message", ""),
                response=msg.payload.get("response", ""),
                action=msg.payload.get("action", "agent"),
            )
            return None  # fire-and-forget

        if op == "read_episodic":
            query: str = msg.payload.get("query", "")
            results = get_relevant_memory(session_id, query)
            return AgentMessage(
                sender=AGENT_NAME,
                receiver=msg.sender,
                type=MessageType.CONTEXT,
                payload={"results": list(results), "op": "read_episodic"},
                task_id=msg.task_id,
            )

        if op == "write_pref":
            set_preference(
                session_id=session_id,
                key=msg.payload.get("key", ""),
                value=msg.payload.get("value", ""),
                confidence=float(msg.payload.get("confidence", 0.85)),
            )
            return None

        if op == "read_prefs":
            query_str = msg.payload.get("query", "")
            results = (
                get_relevant_preferences(session_id, query_str)
                if query_str
                else get_preferences(session_id)
            )
            return AgentMessage(
                sender=AGENT_NAME,
                receiver=msg.sender,
                type=MessageType.CONTEXT,
                payload={"results": results, "op": "read_prefs"},
                task_id=msg.task_id,
            )

        if op == "write_project":
            set_project_context(
                session_id=session_id,
                name=msg.payload.get("name", ""),
                content=msg.payload.get("value", ""),
            )
            return None

        if op == "read_project":
            all_ctx = get_project_context(session_id)
            name = msg.payload.get("name", "")
            value = all_ctx.get(name) if name else all_ctx
            return AgentMessage(
                sender=AGENT_NAME,
                receiver=msg.sender,
                type=MessageType.CONTEXT,
                payload={"value": value, "op": "read_project"},
                task_id=msg.task_id,
            )

        if op == "get_context":
            action_type = msg.payload.get("action_type", "chat")
            query_str = msg.payload.get("query", action_type)
            ctx = build_context_for_task(session_id, query_str, task_type=action_type)
            return AgentMessage(
                sender=AGENT_NAME,
                receiver=msg.sender,
                type=MessageType.CONTEXT,
                payload={"context": ctx, "op": "get_context"},
                task_id=msg.task_id,
            )

        log.warning("memory_agent.unknown_op", op=op)
        return AgentMessage.error(
            sender=AGENT_NAME,
            receiver=msg.sender,
            error=f"Unknown memory op: {op}",
            task_id=msg.task_id,
        )
