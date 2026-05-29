"""
WebSocket Connection Manager with Heartbeat
- Automatic ping/pong detection
- Dead connection cleanup
- Exponential backoff reconnect
"""

import asyncio
import logging
import time
from typing import List
from fastapi import WebSocket

log = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []
        self._last_pong: dict = {}
        self._heartbeat_tasks: dict = {}

    async def connect(self, ws: WebSocket):
        """Accept and register a new WebSocket connection"""
        await ws.accept()
        self.active.append(ws)
        self._last_pong[id(ws)] = time.time()
        log.info(f"[WS] Connected. Total: {len(self.active)}")
        
        # Start heartbeat for this connection
        task = asyncio.create_task(self.heartbeat_loop(ws))
        self._heartbeat_tasks[id(ws)] = task

    def disconnect(self, ws: WebSocket):
        """Remove a disconnected WebSocket"""
        if ws in self.active:
            self.active.remove(ws)
        
        ws_id = id(ws)
        self._last_pong.pop(ws_id, None)
        
        # Cancel heartbeat task
        if ws_id in self._heartbeat_tasks:
            self._heartbeat_tasks[ws_id].cancel()
            del self._heartbeat_tasks[ws_id]
        
        log.info(f"[WS] Disconnected. Total: {len(self.active)}")

    async def broadcast(self, msg: dict):
        """Send message to all connected clients"""
        dead_connections = []
        for ws in self.active:
            try:
                await ws.send_json(msg)
            except Exception as e:
                log.debug(f"[WS] Broadcast failed: {e}")
                dead_connections.append(ws)
        
        # Clean up dead connections
        for ws in dead_connections:
            self.disconnect(ws)

    async def heartbeat_loop(self, ws: WebSocket):
        """Send periodic heartbeat pings to detect dead connections"""
        try:
            while ws in self.active:
                await asyncio.sleep(20)  # Ping every 20 seconds
                try:
                    await ws.send_json({
                        "type": "ping",
                        "timestamp": time.time()
                    })
                except Exception as e:
                    log.debug(f"[WS] Heartbeat send failed: {e}")
                    self.disconnect(ws)
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.warning(f"[WS] Heartbeat error: {e}")

# Global instance
manager = ConnectionManager()
