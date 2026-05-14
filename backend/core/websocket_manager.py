"""
Enhanced WebSocket manager for JARVIS.
Provides heartbeat, message queue, and connection management.
"""
import asyncio
import json
import logging
from collections import deque
from datetime import datetime
from typing import Any, Callable, Deque, List, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect

log = logging.getLogger(__name__)

# Message types for protocol
class MessageType:
    TEXT = "text"
    HEARTBEAT = "heartbeat"
    PONG = "pong"
    ERROR = "error"
    SYSTEM = "system"


class Message:
    """Structured WebSocket message."""

    def __init__(
        self,
        type: str,
        content: str,
        timestamp: Optional[datetime] = None,
        meta: Optional[dict] = None,
    ):
        self.type = type
        self.content = content
        self.timestamp = timestamp or datetime.now()
        self.meta = meta or {}

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "meta": self.meta,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class ConnectionManager:
    """
    Manages WebSocket connections with:
    - Multiple client tracking
    - Message queue per client
    - Heartbeat mechanism
    - Broadcasting capability
    """

    def __init__(self, heartbeat_interval: float = 30.0, queue_max_size: int = 100):
        self.active_connections: Set[WebSocket] = set()
        self.message_queues: dict[WebSocket, Deque[Message]] = {}
        self.heartbeat_interval = heartbeat_interval
        self.queue_max_size = queue_max_size
        self.heartbeat_tasks: dict[WebSocket, asyncio.Task] = {}

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new connection."""
        await websocket.accept()
        self.active_connections.add(websocket)
        self.message_queues[websocket] = deque(maxlen=self.queue_max_size)

        # Start heartbeat for this connection
        task = asyncio.create_task(self._heartbeat_loop(websocket))
        self.heartbeat_tasks[websocket] = task

        log.info(f"Client connected. Active connections: {len(self.active_connections)}")

        # Send welcome message
        welcome = Message(
            type=MessageType.SYSTEM,
            content="Connected to JARVIS. Heartbeat enabled.",
            meta={"connection_count": len(self.active_connections)},
        )
        await self._send_safe(websocket, welcome)

    def disconnect(self, websocket: WebSocket) -> None:
        """Unregister and close a connection."""
        self.active_connections.discard(websocket)

        # Cancel heartbeat task
        if websocket in self.heartbeat_tasks:
            task = self.heartbeat_tasks.pop(websocket)
            if not task.done():
                task.cancel()

        # Clean up message queue
        self.message_queues.pop(websocket, None)

        log.info(f"Client disconnected. Active connections: {len(self.active_connections)}")

    async def broadcast(self, message: Message, exclude: Optional[WebSocket] = None) -> None:
        """Send message to all connected clients."""
        disconnected = []

        for connection in self.active_connections:
            if connection == exclude:
                continue

            if await self._send_safe(connection, message):
                self.message_queues[connection].append(message)
            else:
                disconnected.append(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)

    async def send_personal(self, websocket: WebSocket, message: Message) -> bool:
        """Send message to specific client."""
        success = await self._send_safe(websocket, message)
        if success:
            self.message_queues[websocket].append(message)
        else:
            self.disconnect(websocket)
        return success

    async def _send_safe(self, websocket: WebSocket, message: Message) -> bool:
        """Safely send message, handling disconnections."""
        try:
            await websocket.send_text(message.to_json())
            return True
        except WebSocketDisconnect:
            log.debug("Client already disconnected")
            return False
        except Exception as e:
            log.error(f"Error sending message: {e}")
            return False

    async def _heartbeat_loop(self, websocket: WebSocket) -> None:
        """Send periodic heartbeat to keep connection alive."""
        try:
            while websocket in self.active_connections:
                await asyncio.sleep(self.heartbeat_interval)

                heartbeat = Message(
                    type=MessageType.HEARTBEAT,
                    content="ping",
                    meta={"timestamp_unix": datetime.now().timestamp()},
                )

                if not await self._send_safe(websocket, heartbeat):
                    self.disconnect(websocket)
                    break

        except asyncio.CancelledError:
            log.debug(f"Heartbeat cancelled for client")
        except Exception as e:
            log.error(f"Heartbeat error: {e}")
            self.disconnect(websocket)

    def get_connection_count(self) -> int:
        """Get number of active connections."""
        return len(self.active_connections)

    def get_queue_status(self) -> dict:
        """Get status of all message queues."""
        return {
            "connections": len(self.active_connections),
            "queues": {
                i: {
                    "size": len(queue),
                    "max_size": self.queue_max_size,
                }
                for i, queue in enumerate(self.message_queues.values())
            },
        }


# Global instance
manager = ConnectionManager(heartbeat_interval=30.0, queue_max_size=100)
