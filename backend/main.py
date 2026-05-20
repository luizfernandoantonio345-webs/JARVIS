"""
JARVIS Core v5.2 — Voice-Centric Autonomous System
"""

import asyncio
import logging
import os
import sys
import json
import time
import uuid
import requests
from typing import List

# Ensure backend directory is on sys.path so sibling imports like `from config import get_config`
# and `from schemas.ws_messages import ...` resolve correctly when starting from the repo root.
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from schemas.ws_messages import idle_msg, speaking_msg, thinking_msg, error_msg
from config import get_config
from backend.utils.env import env_flag
from core.logger import log_system, log_error


logging.basicConfig(level=logging.INFO)
log = logging.getLogger("JARVIS_CORE")

# Cache e Rate Limiting — graceful degradation se Redis indisponível
try:
    from fastapi_cache import FastAPICache
    from fastapi_cache.backends.inmemory import InMemoryBackend
    try:
        from fastapi_cache.backends.redis import RedisBackend
    except ImportError:
        RedisBackend = None
    from fastapi_cache.decorator import cache
    _CACHE_OK = True
except ImportError:
    log.warning("[CACHE] fastapi_cache não disponível — cache desabilitado")
    _CACHE_OK = False
    def cache(*a, **kw):
        def decorator(fn): return fn
        return decorator

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
try:
    import aioredis
    _AIOREDIS_OK = True
except Exception:
    _AIOREDIS_OK = False


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
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Configure CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Inicializar cache Redis e rate limiting
@app.on_event("startup")
async def startup_cache():
    if not _CACHE_OK:
        return
    # Tenta Redis; cai para InMemory se indisponível
    if _AIOREDIS_OK:
        try:
            redis = aioredis.from_url("redis://localhost", encoding="utf8", decode_responses=True)
            FastAPICache.init(RedisBackend(redis), prefix="jarvis-cache")
            log.info("[CACHE] Redis backend inicializado")
            return
        except Exception as e:
            log.warning("[CACHE] Redis falhou (%s) — usando InMemory", e)
    try:
        from fastapi_cache.backends.inmemory import InMemoryBackend
        FastAPICache.init(InMemoryBackend(), prefix="jarvis-cache")
        log.info("[CACHE] InMemory backend inicializado")
    except Exception as e:
        log.warning("[CACHE] Falha no InMemory backend: %s", e)

# Security headers
try:
    from middleware.security_headers import setup_security_headers
    setup_security_headers(app)
    log.info("✓ Security headers middleware carregado")
except Exception as e:
    log.warning("Security headers middleware falhou: %s", e)


# =========================
# RATE LIMITER GLOBAL
# =========================
@app.middleware("http")
async def global_rate_limit(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        log_error(
            "http_request_failed",
            category="error",
            error=str(exc),
            action=str(request.url.path),
            session_id=request_id,
        )
        raise
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    response.headers["x-request-id"] = request_id
    log_system(
        "http_request",
        session_id=request_id,
        action=f"{request.method} {request.url.path}",
        tool="http",
        risk=response.status_code,
        error=duration_ms,
    )
    return response


try:
    from prometheus_client import make_asgi_app
    app.mount("/metrics", make_asgi_app())
    log.info("✓ Metrics endpoint montado em /metrics")
except Exception as e:
    log.warning("Metrics endpoint falhou: %s", e)

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

    # Carrega voz em thread separada para não bloquear o event loop
    result = await asyncio.to_thread(load_voice_safe)
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
        # Pre-aquece o modelo Whisper em background para eliminar latência no 1º comando
        async def _prewarm_whisper():
            try:
                from voice.input import WhisperTranscriber
                await asyncio.to_thread(WhisperTranscriber().prewarm)
            except Exception as exc:
                log.debug("[STT] Pre-warm ignorado: %s", exc)
        asyncio.create_task(_prewarm_whisper())

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

    # Initialize Voice Pipeline v3 (headset → STT → pipeline → TTS)
    if mode == "full":
        try:
            from voice_v2.voice_pipeline_v3 import get_voice_pipeline
            pipeline = get_voice_pipeline()
            # Attach manager for WebSocket broadcasts
            pipeline.manager = manager
            try:
                from agents.master_orchestrator import get_orchestrator
                pipeline.orchestrator = get_orchestrator()
            except Exception:
                pass
            await pipeline.initialize()
            log.info('[VOZ_V3] Pipeline ativa — ouvindo headset')
        except Exception as e:
            log.warning('[VOZ_V3] Falha ao iniciar: %s', e)


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

    # Telemetry
    try:
        from routes.telemetry import router as telemetry_router  # type: ignore
        app.include_router(telemetry_router, prefix="/telemetry", tags=["telemetry"])
        log.info("✓ Telemetry router carregado")
    except Exception as e:
        log.warning("Telemetry router falhou: %s", e)

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
        from routes.jarvis import router as jarvis_router, tts_from_text  # type: ignore
        app.include_router(jarvis_router, prefix="/jarvis", tags=["jarvis"])
        if not any(getattr(r, "path", None) == "/tts" and "GET" in getattr(r, "methods", set()) for r in app.routes):
            app.add_api_route("/tts", tts_from_text, methods=["GET"], tags=["tts"])
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

    # Experience Engine
    try:
        from backend.routes.experience import router as exp_router
        app.include_router(exp_router, prefix="/experience", tags=["experience"])
        log.info("✓ Experience router carregado")
    except Exception as e:
        log.warning("Experience router falhou: %s", e)

    # Research
    try:
        from backend.routes.research import router as research_router
        app.include_router(research_router, prefix="/research", tags=["research"])
        log.info("✓ Research router carregado")
    except Exception as e:
        log.warning("Research router falhou: %s", e)

    # TTS Iron Man (edge-tts dedicado)
    try:
        from backend.routes.jarvis_tts import router as tts_router
        app.include_router(tts_router, prefix="/tts-iron", tags=["tts"])
        log.info("✓ TTS Iron Man router carregado em /tts-iron")
    except Exception as e:
        log.warning("TTS Iron Man router falhou: %s", e)

    # Metrics endpoints (runtime + events) - BEFORE Prometheus mount to avoid conflict
    try:
        from backend.observability.metrics import get_metrics
        from backend.core.event_bus import get_event_bus as _get_bus

        @app.get("/api-metrics/runtime", tags=["metrics"])
        async def _metrics_runtime():
            return get_metrics().snapshot()

        @app.get("/api-metrics/events", tags=["metrics"])
        async def _metrics_events(event: str = None, limit: int = 50):
            bus = _get_bus()
            return {"events": bus.get_history(event, limit), "stats": bus.get_stats()}

        log.info("✓ Metrics endpoints registrados (/api-metrics/*)")
    except Exception as e:
        log.warning("Metrics endpoints falharam: %s", e)


# =========================
# STARTUP
# =========================
@app.on_event("startup")
async def startup():
    log.info("Inicializando JARVIS...")
    log.info("Ollama URL: %s", get_config().ollama_url)

    # Mount routers ASAP
    _mount_routers()

    # ── OMEGA: Watchdog + SystemMetrics + Experience + EventBus ──
    try:
        from backend.runtime.watchdog import get_watchdog
        from backend.core.event_bus import get_event_bus
        from backend.observability.system_metrics import collect as collect_sys
        from backend.experience.engine import get_experience

        cfg = get_config()
        wd = get_watchdog()
        bus = get_event_bus()

        get_experience()  # init DB on startup

        async def _check_ollama():
            try:
                import httpx
                async with httpx.AsyncClient(timeout=3) as c:
                    r = await c.get(f"{cfg.ollama_url}/api/tags")
                    return r.status_code == 200
            except Exception:
                return False

        wd.register("ollama", _check_ollama)
        asyncio.create_task(wd.run(60))
        asyncio.create_task(collect_sys(30))
        await bus.emit("system.startup", {"version": "6.0"})
        log.info("[OMEGA] Watchdog + Metrics + Experience inicializados")
    except Exception as e:
        log.warning("[OMEGA] Init parcial: %s", e)

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
        # Mover setup do wake word para background task — evita bloquear startup
        async def _start_wake_word_background():
            try:
                from voice.resilient_loader import check_voice_capabilities
                caps = await asyncio.to_thread(check_voice_capabilities)

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

        asyncio.create_task(_start_wake_word_background())
    else:
        log.info("[WAKE] Wake word desativada por ambiente")

    # Autonomia
    if not env_flag("JARVIS_TEST_MODE"):
        try:
            from autonomy.controller import get_autonomy_controller as _get_ac  # type: ignore
            asyncio.create_task(_get_ac().start())
        except Exception as e:
            log.warning("[AUTONOMY] Nao iniciado: %s", e)
    else:
        log.info("[AUTONOMY] Inicialização desativada por ambiente de teste")

    await manager.broadcast(idle_msg("JARVIS ONLINE"))

    # Warmup: pré-carrega modelo Ollama em background para eliminar cold start
    async def _warmup_ollama():
        try:
            cfg = get_config()
            log.info("[WARMUP] Pré-carregando modelo %s no Ollama...", cfg.model)
            from backend.ai.client import get_ai_client
            client = get_ai_client()
            result = await asyncio.to_thread(
                client._post_chat,
                {"model": client.model, "messages": [{"role": "user", "content": "hi"}], "stream": False, "keep_alive": "30m"},
            )
            if result:
                log.info("[WARMUP] OK — modelo %s pronto na VRAM", client.model)
            else:
                log.warning("[WARMUP] Sem resposta — cold start na 1a mensagem")
        except Exception as e:
            log.warning("[WARMUP] Falhou (nao critico): %r", e)

    asyncio.create_task(_warmup_ollama())


# =========================
# WEBSOCKET
# =========================
_WS_PROCESS_TIMEOUT = 90   # seconds — guards against hung LLM calls
_WS_PING_INTERVAL   = 25   # seconds — keepalive ping


# ===============
# AUDIO STREAM WS
# ===============
import base64

@app.websocket("/ws/audio_stream")
async def audio_stream_ws(ws: WebSocket):
    """
    WebSocket para streaming de áudio bidirecional:
    - Recebe chunks de áudio (base64 PCM/WAV)
    - Retorna transcrição parcial/final e resposta TTS (base64 áudio)
    """
    # Lazy import para evitar crash forrtl no startup
    try:
        from backend.voice.input import WhisperTranscriber
        from backend.voice.output import speak_silent
    except Exception as e:
        await ws.accept()
        await ws.send_json({"type": "error", "message": f"Voice não disponível: {e}"})
        await ws.close()
        return
    await ws.accept()
    transcriber = WhisperTranscriber()
    buffer = bytearray()
    try:
        while True:
            msg = await ws.receive_json()
            if msg.get("type") == "audio_chunk":
                chunk = base64.b64decode(msg["data"])
                buffer.extend(chunk)
                # Opcional: transcrição parcial (não bloqueante)
                if len(buffer) > 32000:  # ~2s áudio
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                        f.write(buffer)
                        f.flush()
                        text = await transcriber.transcribe_audio(f.name)
                    await ws.send_json({"type": "partial_transcript", "text": text})
            elif msg.get("type") == "end":
                # Transcrição final
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    f.write(buffer)
                    f.flush()
                    text = await transcriber.transcribe_audio(f.name)
                await ws.send_json({"type": "final_transcript", "text": text})
                # Gera resposta TTS
                tts_path = await speak_silent(text)
                if tts_path:
                    audio_bytes = Path(tts_path).read_bytes()
                    await ws.send_json({"type": "tts_audio", "data": base64.b64encode(audio_bytes).decode()})
                buffer.clear()
            elif msg.get("type") == "ping":
                await ws.send_json({"type": "pong"})
    except Exception as e:
        await ws.close(code=status.WS_1011_INTERNAL_ERROR)
        log.error(f"[WS][audio_stream] erro: {e}")


async def _speak_response(text: str) -> None:
    """Falar resposta via TTS de forma assíncrona."""
    try:
        from voice.output import speak
        await speak(text[:300])
    except Exception as e:
        log.warning("[VOZ] Fala falhou: %s", e)


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
        await ws.send_json(idle_msg("JARVIS online. Ouvindo, Senhor."))
        ping_task = asyncio.create_task(_heartbeat())

        while True:
            data = await ws.receive_text()

            if data.strip() in ('{"type":"pong"}', 'pong', '__ping__'):
                await ws.send_json({"type": "pong"})
                continue

            await ws.send_json(thinking_msg("Processando..."))

            _ws_t0 = time.time()
            try:
                from backend.observability.metrics import get_metrics as _get_m
                _get_m().inc("ws.messages_received")
            except Exception:
                pass

            response_text: str | None = None
            tokens_sent: list[str] = []

            # Closure captura ws do escopo externo corretamente
            current_ws = ws

            # Fast-path: if Ollama is dead and no API keys, skip orchestration entirely
            from backend.ai.client import is_ollama_available
            from services.llm_service import _ANTHROPIC_KEY, _OPENAI_KEY
            if not _ANTHROPIC_KEY and not _OPENAI_KEY and not is_ollama_available():
                ollama_url = get_config().ollama_url
                response_text = (
                    f"JARVIS offline - Ollama nao responde em {ollama_url}. "
                    "Verifique se o servico esta rodando e se JARVIS_OLLAMA_URL esta correto."
                )
                await current_ws.send_json({"type": "done", "action": "chat", "full_response": response_text})
                await manager.broadcast(speaking_msg(response_text))
                await ws.send_json({"type": "idle", "message": "JARVIS pronto."})
                continue

            async def on_token(token: str) -> None:
                tokens_sent.append(token)
                try:
                    await current_ws.send_json({"type": "token", "content": token})
                except Exception as tok_err:
                    log.warning("[WS] token send failed: %s", tok_err)

            try:
                # FASE 3.2: Usar orquestrador para rotear e executar
                from agents.master_orchestrator import get_orchestrator
                orch = get_orchestrator()

                # Detecta agente e envia ao frontend
                agent_name = orch.route(data)
                await current_ws.send_json({"type": "agent", "agent": agent_name})
                log.info("[WS] Agente: %s | Msg: %s", agent_name, data[:60])

                response_text = await orch.execute(
                    message=data,
                    session_id="ws",
                    on_token=on_token,
                )
                log.info("[WS] Stream completo: %d tokens", len(tokens_sent))

            except Exception as e:
                log.warning("[WS] Orquestrador falhou: %s — fallback direto", e, exc_info=True)
                try:
                    # Fallback: stream_chat direto
                    from ai.client import get_ai_client
                    from services.session_store import get_history, SYSTEM_PROMPT, append_message

                    history = list(get_history("ws"))[-10:]
                    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
                    msgs.extend(history)
                    msgs.append({"role": "user", "content": data})

                    response_text = await get_ai_client().stream_chat(msgs, on_token)
                    append_message("ws", "user", data)
                    append_message("ws", "assistant", response_text)

                except Exception as e2:
                    log.warning("[WS] Fallback stream_chat falhou: %s — sync fallback", e2)
                    try:
                        from services.chat_service import process_message
                        response_text = await asyncio.wait_for(
                            asyncio.get_event_loop().run_in_executor(
                                None, process_message, data, "ws"
                            ),
                            timeout=_WS_PROCESS_TIMEOUT,
                        )
                        if response_text:
                            await current_ws.send_json({"type": "token", "content": response_text})
                    except Exception as e3:
                        log.error("[WS] Todos os fallbacks falharam: %s", e3)
                        response_text = "Erro ao processar. Verifique a conexão com Ollama."
                        await current_ws.send_json({"type": "token", "content": response_text})

            if response_text:
                await current_ws.send_json({
                    "type": "done",
                    "action": "chat",
                    "full_response": response_text[:500],
                })
                await manager.broadcast(speaking_msg(response_text))

                try:
                    from backend.observability.metrics import get_metrics as _get_m
                    _get_m().timing("ws.response_time", time.time() - _ws_t0)
                    _get_m().inc("ws.messages_responded")
                except Exception:
                    pass

                # FASE 4.2: TTS assíncrono após resposta completa
                cfg = get_config()
                if getattr(cfg, "voice_enabled", True):
                    asyncio.create_task(_speak_response(response_text))
            else:
                await current_ws.send_json(error_msg("Nenhuma resposta gerada"))

    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception as e:
        log.exception("[WS] Erro crítico: %s", e)
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