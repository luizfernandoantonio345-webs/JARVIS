"""
JARVIS Core v5.2 — Voice-Centric Autonomous System
"""

import asyncio
import logging
import os
import sys
from typing import List

# Ensure backend directory is on sys.path so sibling imports like `from config import get_config`
# and `from schemas.ws_messages import ...` resolve correctly when starting from the repo root.
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from schemas.ws_messages import idle_msg, speaking_msg, thinking_msg, error_msg
from config import get_config

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("JARVIS_CORE")

app = FastAPI(title="JARVIS v5.2")

# =========================
# CONNECTION MANAGER
# =========================

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active_connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active_connections:
            self.active_connections.remove(ws)

    async def broadcast(self, msg: dict):
        for c in self.active_connections:
            try:
                await c.send_json(msg)
            except:
                pass

manager = ConnectionManager()

# =========================
# VOICE SYSTEM START/STOP
# =========================
async def start_voice_system() -> None:
    cfg = get_config()

    if not cfg.voice_enabled:
        log.warning("Voice desativado.")
        return

    from voice_v2.voice_loop import voice_loop_background
    from voice_v2.output import speak
    from voice_v2.voice_state import VoiceState

    # speaking guard is owned by voice_v2
    voice_state = VoiceState()

    async def _speak_boot() -> None:
        try:
            await speak("Sistemas online. Estou ouvindo.")
        except Exception:
            log.exception("boot TTS failed")

    asyncio.create_task(_speak_boot())
    asyncio.create_task(
        voice_loop_background(
            session_id="jarvis_core",
            voice_state=voice_state,
            config=None,
            stop_event=asyncio.Event(),
        )
    )


# =========================
# STARTUP
# =========================
@app.on_event("startup")
async def startup():
    log.info("Inicializando JARVIS...")

    # Start voice FIRST (prioridade máxima)
    asyncio.create_task(start_voice_system())

    # Autonomia
    try:
        from autonomy.controller import get_autonomy_controller
        asyncio.create_task(get_autonomy_controller().start())
    except:
        pass

    await manager.broadcast(idle_msg("JARVIS ONLINE"))

# =========================
# WEBSOCKET
# =========================
@app.websocket("/ws/jarvis")
async def websocket(ws: WebSocket):
    await manager.connect(ws)

    try:
        await ws.send_json(idle_msg("Conectado ao núcleo JARVIS"))

        while True:
            data = await ws.receive_text()

            from voice_v2.pipeline import run_jarvis_pipeline

            await manager.broadcast(thinking_msg("Processando..."))

            result = await run_jarvis_pipeline(
                input_text=data,
                source="api"
            )


            await manager.broadcast(speaking_msg(result.response))

    except WebSocketDisconnect:
        manager.disconnect(ws)

# =========================
# COMMAND ENDPOINT
# =========================
@app.post("/process")
async def process(cmd: str):
    from routes.jarvis import jarvis_pipeline

    try:
        res = await jarvis_pipeline(cmd)
        return res
    except Exception as e:
        return {"error": str(e)}

# =========================
# RUN
# =========================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)