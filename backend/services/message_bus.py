"""
MessageBus — typed inter-agent communication for JARVIS.

Architecture:
  Every agent task runs in a named "channel" (= session/task ID).
  Agents publish AgentMessage objects to the bus.
  Other agents (or the coordinator) consume those messages.

Message types:
  TASK     → assign work to an agent
  RESULT   → agent publishing its output
  ERROR    → agent reporting a failure
  APPROVE  → reviewer approving code
  REJECT   → reviewer rejecting code
  BLOCK    → security agent blocking execution
  STATUS   → status/progress update
  CONTEXT  → shared context update

Thread-safe. In-memory only (no persistence — use memory_service for that).

Usage:
    from services.message_bus import get_bus, MsgType
    bus = get_bus()
    channel = bus.create_channel("task-abc")
    bus.publish(channel, AgentMessage(from_agent="planner", to_agent="dev",
        msg_type=MsgType.TASK, payload={"task": "write main.py"}))
    messages = bus.consume(channel, consumer="dev")
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque

log = logging.getLogger(__name__)

MAX_CHANNEL_MESSAGES = 500    # per channel
MAX_CHANNELS         = 100    # total active channels
CHANNEL_TTL          = 3600   # seconds before auto-cleanup


# ── Message types ──────────────────────────────────────────────────────────────

class MsgType(str, Enum):
    TASK    = "task"    # assign work
    RESULT  = "result"  # publish output
    ERROR   = "error"   # report failure
    APPROVE = "approve" # reviewer: accept
    REJECT  = "reject"  # reviewer: request changes
    BLOCK   = "block"   # security: block action
    STATUS  = "status"  # progress update
    CONTEXT = "context" # shared context broadcast


# ── AgentMessage ───────────────────────────────────────────────────────────────

@dataclass
class BusMessage:
    """
    A typed message between agents.

    Fields:
        msg_id      : unique UUID for deduplication
        from_agent  : sender role (e.g. "planner", "dev", "security")
        to_agent    : target role, or "*" for broadcast
        msg_type    : MsgType
        payload     : arbitrary data dict
        timestamp   : monotonic time of creation
        ref_msg_id  : optional: ID of message being replied to
    """
    from_agent: str
    to_agent:   str
    msg_type:   MsgType
    payload:    dict

    msg_id:     str   = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp:  float = field(default_factory=time.monotonic)
    ref_msg_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "msg_id":     self.msg_id,
            "from_agent": self.from_agent,
            "to_agent":   self.to_agent,
            "msg_type":   self.msg_type.value,
            "payload":    self.payload,
            "timestamp":  self.timestamp,
            "ref_msg_id": self.ref_msg_id,
        }

    @classmethod
    def task(cls, from_agent: str, to_agent: str, task: str, context: str = "") -> "BusMessage":
        return cls(from_agent=from_agent, to_agent=to_agent,
                   msg_type=MsgType.TASK, payload={"task": task, "context": context})

    @classmethod
    def result(cls, from_agent: str, to_agent: str, output: str, success: bool = True) -> "BusMessage":
        return cls(from_agent=from_agent, to_agent=to_agent,
                   msg_type=MsgType.RESULT, payload={"output": output, "success": success})

    @classmethod
    def error(cls, from_agent: str, to_agent: str, error: str) -> "BusMessage":
        return cls(from_agent=from_agent, to_agent=to_agent,
                   msg_type=MsgType.ERROR, payload={"error": error})

    @classmethod
    def approve(cls, from_agent: str, to_agent: str, summary: str = "") -> "BusMessage":
        return cls(from_agent=from_agent, to_agent=to_agent,
                   msg_type=MsgType.APPROVE, payload={"summary": summary})

    @classmethod
    def reject(cls, from_agent: str, to_agent: str, issues: list[str]) -> "BusMessage":
        return cls(from_agent=from_agent, to_agent=to_agent,
                   msg_type=MsgType.REJECT, payload={"issues": issues})

    @classmethod
    def block(cls, from_agent: str, reason: str) -> "BusMessage":
        return cls(from_agent=from_agent, to_agent="*",
                   msg_type=MsgType.BLOCK, payload={"reason": reason})

    @classmethod
    def context_update(cls, from_agent: str, key: str, value: object) -> "BusMessage":
        return cls(from_agent=from_agent, to_agent="*",
                   msg_type=MsgType.CONTEXT, payload={"key": key, "value": value})


# ── Channel ────────────────────────────────────────────────────────────────────

class Channel:
    """
    A named message queue for one agent collaboration session.

    Thread-safe. Messages are stored in insertion order.
    Consumers can read all messages or filter by recipient.
    """

    def __init__(self, channel_id: str) -> None:
        self.channel_id   = channel_id
        self.created_at   = time.monotonic()
        self.last_active  = time.monotonic()
        self._messages:   Deque[BusMessage] = deque(maxlen=MAX_CHANNEL_MESSAGES)
        self._shared_ctx: dict = {}   # shared key-value context for all agents
        self._lock        = threading.Lock()

    def publish(self, message: BusMessage) -> None:
        with self._lock:
            self._messages.append(message)
            self.last_active = time.monotonic()

            # Auto-update shared context on CONTEXT messages
            if message.msg_type == MsgType.CONTEXT:
                key = message.payload.get("key", "")
                val = message.payload.get("value")
                if key:
                    self._shared_ctx[key] = val

        log.debug(
            "Channel %s: %s → %s [%s]",
            self.channel_id[:8], message.from_agent,
            message.to_agent, message.msg_type.value,
        )

    def consume(
        self,
        consumer: str,
        msg_types: list[MsgType] | None = None,
        since_id: str | None = None,
    ) -> list[BusMessage]:
        """
        Return messages addressed to this consumer (or broadcast "*").

        Args:
            consumer:  Agent role consuming messages.
            msg_types: Optional filter by message type.
            since_id:  Only return messages after this message ID.

        Returns:
            Filtered list of AgentMessage objects.
        """
        with self._lock:
            all_msgs = list(self._messages)

        # Apply since_id cursor
        if since_id:
            idx = next((i for i, m in enumerate(all_msgs) if m.msg_id == since_id), -1)
            all_msgs = all_msgs[idx + 1:] if idx >= 0 else all_msgs

        # Filter by recipient
        result = [
            m for m in all_msgs
            if m.to_agent in (consumer, "*")
        ]

        # Filter by type
        if msg_types:
            result = [m for m in result if m.msg_type in msg_types]

        return result

    def get_all(self) -> list[BusMessage]:
        with self._lock:
            return list(self._messages)

    def get_context(self) -> dict:
        with self._lock:
            return dict(self._shared_ctx)

    def set_context(self, key: str, value: object) -> None:
        with self._lock:
            self._shared_ctx[key] = value

    def last_result_from(self, agent: str) -> BusMessage | None:
        """Get the latest RESULT message from a specific agent."""
        with self._lock:
            msgs = list(self._messages)
        for m in reversed(msgs):
            if m.from_agent == agent and m.msg_type == MsgType.RESULT:
                return m
        return None

    def is_blocked(self) -> bool:
        """Check if a BLOCK message was published (security halt)."""
        with self._lock:
            return any(m.msg_type == MsgType.BLOCK for m in self._messages)

    def summary(self) -> dict:
        with self._lock:
            msgs = list(self._messages)
        type_counts: dict[str, int] = {}
        for m in msgs:
            type_counts[m.msg_type.value] = type_counts.get(m.msg_type.value, 0) + 1
        return {
            "channel_id":   self.channel_id,
            "message_count": len(msgs),
            "type_counts":   type_counts,
            "shared_context_keys": list(self._shared_ctx.keys()),
            "blocked":       self.is_blocked(),
        }


# ── MessageBus ─────────────────────────────────────────────────────────────────

class MessageBus:
    """
    Central message router for all agent channels.

    Creates, manages, and auto-reaps channels.
    """

    def __init__(self) -> None:
        self._channels: dict[str, Channel] = {}
        self._lock = threading.Lock()
        self._start_reaper()

    # ── Channel management ─────────────────────────────────────────────────────

    def create_channel(self, channel_id: str | None = None) -> str:
        """Create a new channel and return its ID."""
        cid = channel_id or str(uuid.uuid4())
        with self._lock:
            if len(self._channels) >= MAX_CHANNELS:
                self._evict_oldest()
            if cid not in self._channels:
                self._channels[cid] = Channel(cid)
        log.info("MessageBus: created channel %s", cid[:8])
        return cid

    def get_channel(self, channel_id: str) -> Channel | None:
        with self._lock:
            return self._channels.get(channel_id)

    def close_channel(self, channel_id: str) -> bool:
        with self._lock:
            removed = self._channels.pop(channel_id, None)
        if removed:
            log.info("MessageBus: closed channel %s", channel_id[:8])
        return removed is not None

    # ── Messaging ─────────────────────────────────────────────────────────────

    def publish(self, channel_id: str, message: BusMessage) -> bool:
        """Publish a message to a channel. Returns False if channel not found."""
        channel = self.get_channel(channel_id)
        if not channel:
            log.warning("MessageBus.publish: channel %r not found", channel_id)
            return False
        channel.publish(message)
        return True

    def consume(
        self,
        channel_id: str,
        consumer: str,
        msg_types: list[MsgType] | None = None,
        since_id: str | None = None,
    ) -> list[BusMessage]:
        """Consume messages from a channel for a specific agent."""
        channel = self.get_channel(channel_id)
        if not channel:
            return []
        return channel.consume(consumer=consumer, msg_types=msg_types, since_id=since_id)

    def get_context(self, channel_id: str) -> dict:
        channel = self.get_channel(channel_id)
        return channel.get_context() if channel else {}

    def is_blocked(self, channel_id: str) -> bool:
        channel = self.get_channel(channel_id)
        return channel.is_blocked() if channel else False

    def channel_summary(self, channel_id: str) -> dict:
        channel = self.get_channel(channel_id)
        return channel.summary() if channel else {}

    # ── Private ────────────────────────────────────────────────────────────────

    def _evict_oldest(self) -> None:
        """Remove the channel with the oldest last_active timestamp."""
        oldest_id = min(self._channels, key=lambda k: self._channels[k].last_active)
        del self._channels[oldest_id]
        log.info("MessageBus: evicted channel %s (at capacity)", oldest_id[:8])

    def _start_reaper(self) -> None:
        import threading

        def reap():
            while True:
                time.sleep(60)
                now = time.monotonic()
                to_close = []
                with self._lock:
                    for cid, ch in list(self._channels.items()):
                        if now - ch.last_active > CHANNEL_TTL:
                            to_close.append(cid)
                for cid in to_close:
                    self.close_channel(cid)
                    log.debug("MessageBus: reaped channel %s (TTL expired)", cid[:8])

        t = threading.Thread(target=reap, daemon=True, name="msgbus-reaper")
        t.start()

    def stats(self) -> dict:
        with self._lock:
            channels = list(self._channels.values())
        return {
            "active_channels": len(channels),
            "total_messages":  sum(len(ch._messages) for ch in channels),
        }


# ── Singleton ──────────────────────────────────────────────────────────────────

_bus: MessageBus | None = None


def get_bus() -> MessageBus:
    """Return the global MessageBus singleton."""
    global _bus
    if _bus is None:
        _bus = MessageBus()
    return _bus
