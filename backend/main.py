"""
JARVIS Core v5.2 — Voice-Centric Autonomous System
"""

import asyncio
import logging
import os
import sys
import json
import requests
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
from backend.utils.env import env_flag

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("JARVIS_CORE")


def _cors_origins() -> list[str]:
    configured = os.getenv("JARVIS_FRONTEND_URL", "http://localhost:3000")
    default_origins = [
        configured,
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ]
    origins: list[str] = []
    for origin in default_origins:
        value = origin.strip()
        if value and value not in origins:
            origins.append(value)
    return origins


app = FastAPI(title="JARVIS v5.2")

# Configure CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Security headers
try:
    from middleware.security_headers import setup_security_headers
    setup_security_headers(app)
    log.info("✓ Security headers middleware carregado")
except Exception as e:
    log.warning("Security headers middleware falhou: %s", e)

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
        dead: List[WebSocket] = []
        for c in list(self.active_connections):
            try:
                await c.send_json(msg)
            except Exception:
                dead.append(c)
        for c in dead:
            self.disconnect(c)

manager = ConnectionManager()


def _voice_runtime_enabled() -> bool:
    return not (env_flag("JARVIS_TEST_MODE") or env_flag("JARVIS_DISABLE_VOICE"))

# =========================
# VOICE SYSTEM START/STOP
# =========================
async def start_voice_system() -> None:
    """
    Start voice system safely, adapting to available dependencies.
    Never crashes startup — always returns gracefully.
    """
    from voice.resilient_loader import load_voice_safe

    result = load_voice_safe()
    mode = result["mode"]
    missing = result["missing"]

    # Log what's missing
    if missing:
        log.warning("[VOZ] Dependências ausentes: %s", ", ".join(missing))
        log.warning("[VOZ] Instale com: pip install %s", " ".join(missing))

    if mode == "none":
        log.warning("[VOZ] Voz desativada — nenhuma dependência disponível")
        return

    log.info("[VOZ] Modo: %s", mode)

    # Helper for safe TTS
    async def _speak_safe(text: str) -> None:
        try:
            from voice.output import speak
            await speak(text)
        except Exception as e:
            log.warning("[VOZ] TTS falhou: %s", e)

    # TTS-only or Full: speak at startup
    if mode in ("tts_only", "full"):
        asyncio.create_task(_speak_safe("Sistemas online. Estou ouvindo."))

    # Full mode: start STT loop
    if mode == "full":
        try:
            from voice.voice_loop import voice_loop_background
            from voice.voice_state import VoiceState

            voice_state = VoiceState()
            asyncio.create_task(
                voice_loop_background(
                    session_id="jarvis_core",
                    voice_state=voice_state,
                    config=None,
                    stop_event=asyncio.Event(),
                )
            )
        except Exception as e:
            log.error("[VOZ] Falha ao iniciar voice_loop em modo full: %s", e)


def _mount_routers() -> None:
    # Health + core routes
    try:
        from routes.health import router as health_router  # type: ignore
        app.include_router(health_router, prefix="")
        log.info("✓ Health router carregado")
    except Exception as e:
        # fallback to unified health in core
        try:
            from core.health import router as core_health_router  # type: ignore
            app.include_router(core_health_router, prefix="")
            log.info("✓ Core health router carregado")
        except Exception as e2:
            log.warning("Health router falhou: %s | %s", e, e2)

    # Chat
    try:
        from routes.chat import router as chat_router  # type: ignore
        app.include_router(chat_router, prefix="/chat")
        log.info("✓ Chat router carregado")
    except Exception as e:
        log.warning("Chat router falhou: %s", e)

    # Agents
    try:
        from routes.agents import router as agents_router  # type: ignore
        app.include_router(agents_router, prefix="/agents")
        log.info("✓ Agents router carregado")
    except Exception as e:
        log.warning("Agents router falhou: %s", e)

    # Autonomy
    try:
        from routes.autonomy import router as autonomy_router  # type: ignore
        app.include_router(autonomy_router, prefix="/autonomy")
        log.info("✓ Autonomy router carregado")
    except Exception as e:
        log.warning("Autonomy router falhou: %s", e)

    # AutoDev
    try:
        from routes.autodev import router as autodev_router  # type: ignore
        app.include_router(autodev_router, prefix="/autodev")
        log.info("✓ AutoDev router carregado")
    except Exception as e:
        log.warning("AutoDev router falhou: %s", e)

    # Dashboard (optional)
    try:
        from routes.dashboard import router as dashboard_router  # type: ignore
        app.include_router(dashboard_router, prefix="/dashboard")
        log.info("✓ Dashboard router carregado")
    except Exception as e:
        log.warning("Dashboard router falhou: %s", e)

    # Memory (optional)
    try:
        from routes.memory import router as memory_router  # type: ignore
        app.include_router(memory_router, prefix="/memory")
        log.info("✓ Memory router carregado")
    except Exception as e:
        log.warning("Memory router falhou: %s", e)

    # Behavior (optional)
    try:
        from routes.behavior import router as behavior_router  # type: ignore
        app.include_router(behavior_router, prefix="/behavior")
        log.info("✓ Behavior router carregado")
    except Exception as e:
        log.warning("Behavior router falhou: %s", e)

    # Voice
    try:
        from backend.routes.voice import router as voice_router  # type: ignore
        app.include_router(voice_router, prefix="/voice", tags=["voice"])
        log.info("✓ Voice router carregado")
    except Exception as e:
        log.warning("Voice router falhou: %s", e)

    # Computer Control
    try:
        from routes.computer import router as computer_router  # type: ignore
        app.include_router(computer_router, prefix="/computer", tags=["computer"])
        log.info("✓ Computer router carregado")
    except Exception as e:
        log.warning("Computer router falhou: %s", e)

    # Jarvis multimodal chat
    try:
        from routes.jarvis import router as jarvis_router  # type: ignore
        app.include_router(jarvis_router, prefix="/jarvis", tags=["jarvis"])
        log.info("✓ Jarvis router carregado")
    except Exception as e:
        log.warning("Jarvis router falhou: %s", e)

    # Static files & Frontend
    try:
        from routes.static import router as static_router  # type: ignore
        app.include_router(static_router, prefix="")
        log.info("✓ Static/Frontend router carregado")
    except Exception as e:
        log.warning("Static router falhou: %s", e)


# =========================
# STARTUP
# =========================
@app.on_event("startup")
async def startup():
    log.info("Inicializando JARVIS...")
    log.info("Ollama URL: %s", get_config().ollama_url)

    # Mount routers ASAP
    _mount_routers()

    # Telemetry init (no-op if deps missing)
    try:
        from core.telemetry import initialize as telemetry_initialize  # type: ignore
        telemetry_initialize()
    except Exception:
        pass

    voice_enabled = _voice_runtime_enabled()

    if voice_enabled:
        # Start voice system (resilient — never crashes)
        asyncio.create_task(start_voice_system())
    else:
        log.info("[VOZ] Inicialização de voz desativada por ambiente")

    # Start wake word detection (só se openwakeword + sounddevice disponíveis)
    async def _on_wake_word_detected():
        """Callback when wake word is detected."""
        log.info("[WAKE] Wake word detectada — ativando escuta")
        await manager.broadcast({
            "status": "listening",
            "message": "Ouvindo, Senhor.",
            "source": "wake_word"
        })

    if voice_enabled:
        try:
            from voice.resilient_loader import check_voice_capabilities
            caps = check_voice_capabilities()

            if caps.wake_word_available and caps.audio_available:
                from voice.wake_word_engine import start_wake_word
                loop = asyncio.get_event_loop()
                engine = start_wake_word(
                    on_detected=_on_wake_word_detected,
                    loop=loop,
                    keyword="jarvis",
                    threshold=0.06,
                )
                if engine:
                    log.info("[WAKE] Wake word 'JARVIS' ativa e escutando")
                else:
                    log.warning("[WAKE] Wake word não pode ser iniciada")
            else:
                log.warning(
                    "[WAKE] Wake word indisponível — openwakeword: %s, sounddevice: %s",
                    caps.wake_word_available,
                    caps.audio_available,
                )
        except Exception as e:
            log.warning("[WAKE] Wake word não iniciada: %s", e)
    else:
        log.info("[WAKE] Wake word desativada por ambiente")

    # Autonomia
    if not env_flag("JARVIS_TEST_MODE"):
        try:
            from autonomy.controller import get_autonomy_controller
            asyncio.create_task(get_autonomy_controller().start())
        except Exception:
            pass
    else:
        log.info("[AUTONOMY] Inicialização desativada por ambiente de teste")

    await manager.broadcast(idle_msg("JARVIS ONLINE"))


# =========================
# WEBSOCKET
# =========================
_WS_PROCESS_TIMEOUT = 90   # seconds — guards against hung LLM calls
_WS_PING_INTERVAL   = 25   # seconds — keepalive ping


@app.websocket("/ws/jarvis")
async def websocket(ws: WebSocket):
    await manager.connect(ws)
    ping_task: asyncio.Task | None = None

    async def _heartbeat():
        try:
            while True:
                await asyncio.sleep(_WS_PING_INTERVAL)
                await ws.send_json({"type": "ping", "ts": asyncio.get_event_loop().time()})
        except Exception:
            pass

    try:
        await ws.send_json(idle_msg("Conectado ao núcleo JARVIS"))
        ping_task = asyncio.create_task(_heartbeat())

        while True:
            data = await ws.receive_text()

            if data.strip() in ('{"type":"pong"}', 'pong', '__ping__'):
                continue

            await ws.send_json(thinking_msg("Processando..."))

            tokens_sent = []

            async def on_token(token: str):
                tokens_sent.append(token)
                try:
                    await ws.send_json({"type": "token", "content": token})
                except Exception as e:
                    log.warning("Failed to send token: %s", e)

            response_text: str | None = None
            try:
                from ai.client import get_ai_client
                from services.session_store import get_history, SYSTEM_PROMPT, append_message

                history = list(get_history("ws"))[-10:]
                messages = [{"role": "system", "content": SYSTEM_PROMPT}]
                messages.extend(history)
                messages.append({"role": "user", "content": data})

                log.info("[WS] Streaming com %d msgs no contexto", len(messages))
                response_text = await get_ai_client().stream_chat(messages, on_token)
                log.info("[WS] Stream completo: %d tokens", len(tokens_sent))

                append_message("ws", "user", data)
                append_message("ws", "assistant", response_text)

            except asyncio.TimeoutError:
                log.warning("stream_chat timed out after %ds", _WS_PROCESS_TIMEOUT)
                response_text = "Timeout: sem resposta do modelo."
                await ws.send_json({"type": "token", "content": response_text})
            except Exception as e:
                log.warning("stream_chat falhou: %s — tentando fallback", e, exc_info=True)
                try:
                    from services.chat_service import process_message
                    response_text = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(
                            None, process_message, data, "ws"
                        ),
                        timeout=_WS_PROCESS_TIMEOUT,
                    )
                    if response_text:
                        await ws.send_json({"type": "token", "content": response_text})
                except Exception as e2:
                    log.warning("Fallback também falhou: %s", e2)
                    response_text = "Erro ao processar. Verifique a conexão com Ollama."
                    await ws.send_json({"type": "token", "content": response_text})

            if response_text:
                await ws.send_json({
                    "type": "done",
                    "action": "chat",
                    "full_response": response_text
                })
                await manager.broadcast(speaking_msg(response_text))
            else:
                await ws.send_json(error_msg("Nenhuma resposta gerada"))

    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception as e:
        log.exception("WebSocket error: %s", e)
        manager.disconnect(ws)
    finally:
        if ping_task and not ping_task.done():
            ping_task.cancel()


# =========================
# RUN
# =========================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)