"""
JARVIS Simple WebSocket Server - Minimal version for testing Neural Core UI
"""

import asyncio
import logging
import json
from typing import List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import random

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("JARVIS_SIMPLE")

app = FastAPI(title="JARVIS Simple v1.0")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active_connections.append(ws)
        log.info(f"Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, ws: WebSocket):
        if ws in self.active_connections:
            self.active_connections.remove(ws)
        log.info(f"Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, msg: dict):
        for c in self.active_connections:
            try:
                await c.send_json(msg)
            except Exception as e:
                log.error(f"Broadcast error: {e}")

manager = ConnectionManager()

# WebSocket endpoint
@app.websocket("/ws/jarvis")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send welcome message
        await websocket.send_json({
            "status": "idle",
            "message": "JARVIS Neural Core Online"
        })

        while True:
            data = await websocket.receive_text()
            log.info(f"Received: {data}")

            # Parse command
            try:
                cmd = json.loads(data) if data.startswith('{') else {"cmd": data}
            except:
                cmd = {"cmd": data}

            # Simulate processing
            await manager.broadcast({
                "status": "thinking",
                "message": f"Processing: {cmd.get('cmd', data)}"
            })

            # Simulate some processing delay
            await asyncio.sleep(0.5)

            # Generate response
            responses = [
                "Entendido. Processando solicitação.",
                "Análise concluída. Sistema operacional.",
                "Comando executado com sucesso.",
                "Núcleo neural respondendo normalmente.",
            ]
            
            await manager.broadcast({
                "status": "speaking",
                "message": random.choice(responses)
            })

            await asyncio.sleep(1)

            # Return to idle
            await manager.broadcast({
                "status": "idle",
                "message": "Aguardando próximo comando"
            })

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        log.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

# Health check
@app.get("/health")
async def health():
    return {"status": "ok", "service": "JARVIS"}

if __name__ == "__main__":
    import uvicorn
    log.info("Starting JARVIS Simple server on 0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000, ws_ping_interval=20, ws_ping_timeout=20)
