"""
agent_protocol — FASE 9

Pydantic schemas for inter-agent communication.

All messages exchanged between agents and the Orchestrator use
``AgentMessage``.  Serialising with Pydantic ensures type safety and makes
the bus payload inspectable (logging, replay, audit).

Role in the system
------------------
Imported by every agent and by the message bus / orchestrator.
Kept in a single file to act as the source-of-truth for the protocol.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict


class MessageType(str, Enum):
    TASK     = "task"      # Orchestrator → Agent: here is your task
    RESULT   = "result"    # Agent → Orchestrator: here is my output
    ERROR    = "error"     # Agent → Orchestrator: something went wrong
    FEEDBACK = "feedback"  # Critic → Orchestrator: approve / reject
    STATUS   = "status"    # Any → Any: informational status update
    MEMORY   = "memory"    # Any → MemoryAgent: read/write request
    CONTEXT  = "context"   # MemoryAgent → Any: requested memory payload


class AgentMessage(BaseModel):
    """
    Universal message envelope for inter-agent communication.

    Fields
    ------
    id:        Unique message ID (UUID4 auto-generated).
    sender:    Logical name of the sending agent or "orchestrator".
    receiver:  Logical name of the target agent or "orchestrator".
    type:      Semantic message type (MessageType enum).
    payload:   Arbitrary dict — structure depends on the message type.
    timestamp: ISO-8601 UTC creation time.
    task_id:   Optional ID linking messages to the same top-level task.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    sender: str
    receiver: str
    type: MessageType
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    task_id: str | None = None

    model_config = ConfigDict(use_enum_values=True)

    # ── Convenience constructors ───────────────────────────────────────────────

    @classmethod
    def task(
        cls,
        sender: str,
        receiver: str,
        goal: str,
        context: dict[str, Any] | None = None,
        task_id: str | None = None,
    ) -> "AgentMessage":
        return cls(
            sender=sender,
            receiver=receiver,
            type=MessageType.TASK,
            payload={"goal": goal, "context": context or {}},
            task_id=task_id,
        )

    @classmethod
    def result(
        cls,
        sender: str,
        receiver: str,
        output: str,
        metadata: dict[str, Any] | None = None,
        task_id: str | None = None,
    ) -> "AgentMessage":
        return cls(
            sender=sender,
            receiver=receiver,
            type=MessageType.RESULT,
            payload={"output": output, "metadata": metadata or {}},
            task_id=task_id,
        )

    @classmethod
    def error(
        cls,
        sender: str,
        receiver: str,
        error: str,
        task_id: str | None = None,
    ) -> "AgentMessage":
        return cls(
            sender=sender,
            receiver=receiver,
            type=MessageType.ERROR,
            payload={"error": error},
            task_id=task_id,
        )

    @classmethod
    def feedback(
        cls,
        sender: str,
        receiver: str,
        approved: bool,
        reason: str,
        task_id: str | None = None,
    ) -> "AgentMessage":
        return cls(
            sender=sender,
            receiver=receiver,
            type=MessageType.FEEDBACK,
            payload={"approved": approved, "reason": reason},
            task_id=task_id,
        )


class Task(BaseModel):
    """A decomposed sub-task assigned to a specific agent."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    goal: str
    assignee: str           # agent role name
    priority: int = 5       # 1=highest, 10=lowest
    dependencies: list[str] = Field(default_factory=list)  # list of Task.id
    context: dict[str, Any] = Field(default_factory=dict)
    status: str = "pending" # pending | running | done | failed
    result: str | None = None


class FinalResult(BaseModel):
    """Top-level result returned by Orchestrator.run()."""

    goal: str
    status: str            # "success" | "failed" | "partial"
    output: str
    tasks: list[Task] = Field(default_factory=list)
    iterations: int = 0
    error: str | None = None
