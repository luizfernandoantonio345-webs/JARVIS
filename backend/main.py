"""JARVIS Backend — FastAPI v9.0"""
import asyncio
import logging
import os
import sys
import time
import uuid
from typing import List

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

LOG_DIR = os.path.join(BACKEND_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

from logging.handlers import RotatingFileHandler as _RFH
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        _RFH(
            os.path.join(LOG_DIR, 'jarvis.log'),
            maxBytes=10 * 1024 * 1024,  # 10 MB por arquivo
            backupCount=5,
            encoding='utf-8'
        ),
    ]
)
log = logging.getLogger('JARVIS')

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config import get_config
from schemas.ws_messages import idle_msg, speaking_msg, thinking_msg

_cfg = get_config()

# ── Guardian / Security ────────────────────────────────────────────────────────
_guardian = None
_JARVIS_SECRET = os.getenv('JARVIS_SECRET_KEY', '')
if _JARVIS_SECRET:
    try:
        from security.guardian import init_guardian
        _guardian = init_guardian(_JARVIS_SECRET)
        log.info('[SECURITY] Guardian: ATIVO (tokens HMAC-SHA256 + detecção de ameaças)')
    except Exception as _ge:
        log.warning('[SECURITY] Guardian não carregado: %s', _ge)
else:
    log.info('[SECURITY] JARVIS_SECRET_KEY não definida — Guardian desativado (modo aberto)')

# ── CORS ───────────────────────────────────────────────────────────────────────
_raw_origins = _cfg.cors_origins.strip()
CORS_ORIGINS: List[str] = (
    ["*"] if _raw_origins == "*"
    else [o.strip() for o in _raw_origins.split(",") if o.strip()]
)

app = FastAPI(
    title='JARVIS v8.0',
    version='8.0.0',
    description='J.A.R.V.I.S. — Just A Rather Very Intelligent System. Personal AI Backend.',
    docs_url='/docs',
    redoc_url='/redoc',
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# ── Request-ID + Timing middleware ─────────────────────────────────────────────
@app.middleware("http")
async def _request_id_timing(request: Request, call_next):
    req_id = request.headers.get("X-Request-ID") or f"j{uuid.uuid4().hex[:10]}"
    t0 = time.monotonic()
    response = await call_next(request)
    elapsed_ms = round((time.monotonic() - t0) * 1000)
    response.headers["X-Request-ID"] = req_id
    response.headers["X-Response-Time"] = f"{elapsed_ms}ms"
    response.headers["X-JARVIS-Version"] = "9.0"
    return response

# ── Security Middleware Stack ──────────────────────────────────────────────────
try:
    from middleware.security_headers import SecurityHeadersMiddleware
    app.add_middleware(SecurityHeadersMiddleware)
    log.info('[SECURITY] SecurityHeaders: ATIVO')
except Exception as e:
    log.warning('[SECURITY] SecurityHeaders não carregado: %s', e)

try:
    from middleware.input_guard import InputGuardMiddleware
    app.add_middleware(InputGuardMiddleware)
    log.info('[SECURITY] InputGuard (anti-injection): ATIVO')
except Exception as e:
    log.warning('[SECURITY] InputGuard não carregado: %s', e)

try:
    from middleware.audit import AuditMiddleware
    app.add_middleware(AuditMiddleware)
    log.info('[SECURITY] AuditLog: ATIVO → logs/audit.jsonl')
except Exception as e:
    log.warning('[SECURITY] AuditLog não carregado: %s', e)

try:
    from middleware.rate_limiter import rate_limit_middleware
    from starlette.middleware.base import BaseHTTPMiddleware
    app.add_middleware(BaseHTTPMiddleware, dispatch=rate_limit_middleware)
    log.info('[SECURITY] RateLimiter: ATIVO')
except Exception as e:
    log.warning('[SECURITY] RateLimiter não carregado: %s', e)

# ── Guardian security middleware ───────────────────────────────────────────────
# Roda quando JARVIS_SECRET_KEY está definida — valida token Bearer em todas as rotas
# (exceto /health, /ping, /sw.js, /manifest.json, /static/)
if _guardian:
    @app.middleware("http")
    async def _guardian_middleware(request: Request, call_next):
        ip = request.client.host if request.client else "unknown"
        path = request.url.path
        method = request.method

        # Leitura do body (limitada a 8KB para payload scan)
        body = ""
        if method in ("POST", "PUT", "PATCH"):
            try:
                raw = await request.body()
                body = raw[:8192].decode("utf-8", errors="replace")
            except Exception:
                pass

        token = ""
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        if not token:
            token = request.query_params.get("auth", "")

        user_agent = request.headers.get("User-Agent", "")

        allowed, status_code, detail = _guardian.check_request(
            ip=ip, path=path, method=method,
            body=body, user_agent=user_agent, token=token,
        )

        if not allowed:
            return JSONResponse(
                {"error": "Acesso negado", "detail": detail},
                status_code=status_code,
                headers={"X-JARVIS-Blocked": "true"},
            )

        return await call_next(request)

# ── Optional Bearer-token auth (legado — substituído pelo Guardian quando JARVIS_SECRET_KEY definida) ──
_API_KEY = _cfg.api_key.strip()

if _API_KEY:
    _PUBLIC_PATHS = {"/", "/health", "/status", "/docs", "/openapi.json", "/redoc"}

    @app.middleware("http")
    async def _auth(request: Request, call_next):
        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)
        # WebSocket: aceita token via query param ?token=...
        if request.url.path.startswith("/ws"):
            ws_token = request.query_params.get("token", "")
            if ws_token == _API_KEY:
                return await call_next(request)
            # Sem token → recusa (retorna 401; o WS client verá onclose)
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != _API_KEY:
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)

# ── Static frontend ────────────────────────────────────────────────────────────
FRONTEND_DIR = os.path.join(os.path.dirname(BACKEND_DIR), 'frontend')
if os.path.exists(FRONTEND_DIR):
    app.mount('/static', StaticFiles(directory=FRONTEND_DIR), name='static')


@app.get('/', include_in_schema=False)
async def serve_frontend():
    index = os.path.join(FRONTEND_DIR, 'index.html')
    if os.path.exists(index):
        return FileResponse(index)
    return {'message': 'JARVIS API v9.0'}


@app.get('/sw.js', include_in_schema=False)
async def serve_service_worker():
    """Serve o service worker com escopo raiz para PWA funcionar corretamente."""
    sw_path = os.path.join(FRONTEND_DIR, 'sw.js')
    if os.path.exists(sw_path):
        return FileResponse(
            sw_path,
            media_type='application/javascript',
            headers={'Service-Worker-Allowed': '/'},
        )
    return JSONResponse({'error': 'sw.js not found'}, status_code=404)


@app.get('/manifest.json', include_in_schema=False)
async def serve_manifest():
    """Serve o manifest PWA para instalação em mobile."""
    m_path = os.path.join(FRONTEND_DIR, 'manifest.json')
    if os.path.exists(m_path):
        return FileResponse(m_path, media_type='application/manifest+json')
    return JSONResponse({'error': 'manifest.json not found'}, status_code=404)


# ── WebSocket connection manager ───────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        log.info('[WS] Conectado. Total: %d', len(self.active))

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, msg: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


# ── Router loader (executado no nível de módulo — rotas disponíveis imediatamente) ──
# Chamado no nível de módulo para que as rotas estejam disponíveis desde o import
# (TestClient e imports diretos funcionam sem precisar do evento startup)
def _mount_routers():
    cfg_map = [
        # (module,              url_prefix,       required)
        ('routes.health',       '',               True),
        ('routes.chat',         '/chat',          True),
        ('routes.agents',       '/agents',        False),
        ('routes.jarvis_tts',   '/tts-iron',      False),
        ('routes.memory',       '/memory',        False),
        ('routes.voice',        '/voice',         False),
        # ── JARVIS v7.0: Power routes ──────────────────────────────────────
        ('routes.investigate',  '/investigate',   False),  # OSINT: phone/IP/email
        ('routes.analyze',      '/analyze',       False),  # Code analysis + errors
        ('routes.architect',    '/architect',     False),  # System architecture planner
        # ── JARVIS v8.0: Generation + Task queue ───────────────────────────
        ('routes.generate',     '/generate',      False),  # Code/docs/diagrams/tests generation
        ('routes.tasks',        '/tasks',         False),  # Background task queue
        # ── JARVIS v9.0: Security dashboard ───────────────────────────────────
        ('routes.security',     '/security',      False),  # Auth tokens + threat dashboard
    ]
    for module, prefix, required in cfg_map:
        try:
            mod = __import__(module, fromlist=['router'])
            app.include_router(mod.router, prefix=prefix)
            log.info('[ROUTES] Carregado: %s%s', module, prefix or '/')
        except ImportError as e:
            if required:
                log.error('[ROUTES] CRITICO %s: %s', module, e)
            else:
                log.debug('[ROUTES] Opcional nao carregado: %s — %s', module, e)
        except Exception as e:
            log.warning('[ROUTES] %s falhou: %s', module, e)


# Registrar todas as rotas imediatamente ao importar o módulo
_mount_routers()

# ── Lifecycle ──────────────────────────────────────────────────────────────────
@app.on_event('startup')
async def startup():
    log.info('=' * 50)
    log.info('JARVIS v8.0 iniciando...')
    log.info('Ollama: %s', _cfg.ollama_url)

    # Seleciona modelo por RAM (JARVIS_MODEL manual sempre tem prioridade)
    try:
        from utils.model_selector import resolve_model
        resolved = resolve_model(_cfg)
        if resolved != _cfg.local_model:
            os.environ['JARVIS_MODEL'] = resolved
            os.environ['JARVIS_LOCAL_MODEL'] = resolved
            log.info('Model : %s (auto-selecionado por RAM)', resolved)
        else:
            log.info('Model : %s', _cfg.local_model)
    except Exception as _e:
        log.warning('[MODEL_SEL] %s — usando %s', _e, _cfg.local_model)

    auth_status = 'habilitado' if _API_KEY else 'desabilitado (local)'
    log.info('Auth  : %s', auth_status)
    log.info('CORS  : %s', CORS_ORIGINS)

    # Registrar callback do Guardian para broadcast de alertas via WebSocket
    if _guardian:
        async def _broadcast_security_alert(payload: dict):
            await manager.broadcast(payload)
        _guardian.register_alert_callback(_broadcast_security_alert)
        log.info('[SECURITY] Alertas de ameaça conectados ao WebSocket.')

    asyncio.create_task(_init_voice())
    asyncio.create_task(_prewarm_ollama())
    asyncio.create_task(_check_model_health())

    await manager.broadcast(idle_msg('JARVIS online. Ready, Sir.'))
    log.info('JARVIS pronto.')
    log.info('=' * 50)


async def _init_voice():
    await asyncio.sleep(2)
    try:
        from voice_v2.resilient_loader import load_voice_safe
        result = load_voice_safe()
        mode = result.get('mode', 'none')
        log.info('[VOICE] Modo: %s', mode)
        if mode in ('tts_only', 'full'):
            asyncio.create_task(_speak_boot())
    except Exception as e:
        log.warning('[VOICE] %s', e)

    if os.getenv('JARVIS_HEADSET_MODE', 'false').lower() == 'true':
        asyncio.create_task(_init_headset_pipeline())


async def _init_headset_pipeline():
    """Start headset listener pipeline for hands-free voice interaction."""
    await asyncio.sleep(4)
    try:
        from voice_v2.voice_pipeline_v3 import get_voice_pipeline
        from agents.master_orchestrator import get_orchestrator
        import main as _main_mod
        pipeline = get_voice_pipeline()
        pipeline.orchestrator = get_orchestrator()
        pipeline.manager = _main_mod.manager
        await pipeline.initialize()
        log.info('[HEADSET_PIPELINE] Hands-free mode active')
    except Exception as e:
        log.warning('[HEADSET_PIPELINE] Could not start: %s', e)

    # ── Wake word engine ─────────────────────────────────────────────────────
    if os.getenv('JARVIS_WAKE_WORD_ENABLED', 'true').lower() == 'true':
        await asyncio.sleep(2)
        try:
            from voice_v2.wake_word import start_wake_word
            from voice_v2.voice_pipeline_v3 import get_voice_pipeline as _gvp

            _pipeline = _gvp()

            async def _on_wake(audio):
                """Callback: processa áudio capturado após wake word."""
                await _pipeline._on_audio(audio)

            loop = asyncio.get_event_loop()
            start_wake_word(on_wake=_on_wake, loop=loop)
            log.info('[WAKE_WORD] Engine ativo — diga "Hey JARVIS" para ativar')
        except Exception as e:
            log.warning('[WAKE_WORD] Não foi possível iniciar: %s', e)


async def _speak_boot():
    await asyncio.sleep(1)
    try:
        from voice_v2.output import speak
        await speak('All systems online. Good evening, Sir. J.A.R.V.I.S. is ready.')
    except Exception as e:
        log.debug('[BOOT_TTS] %s', e)


async def _prewarm_ollama():
    await asyncio.sleep(5)
    try:
        from ai.client import get_ai_client
        get_ai_client().call([{'role': 'user', 'content': 'respond with: ready'}])
        log.info('[PREWARM] Ollama pre-carregado')
    except Exception as e:
        log.warning('[PREWARM] %s', e)


async def _check_model_health():
    """Check if configured model is available in Ollama."""
    await asyncio.sleep(3)
    try:
        from ai.client import get_ai_client
        client = get_ai_client()
        result = client.health_check()
        if result.get("ok"):
            log.info("[STARTUP] Modelo '%s' disponível", result.get("model", result.get("models", ["?"])[0] if result.get("models") else "?"))
        else:
            log.warning("[STARTUP] Ollama não disponível — modo offline")
    except Exception as e:
        log.warning("[STARTUP] Health check do modelo falhou: %s", e)


# ── WebSocket endpoint ─────────────────────────────────────────────────────────
@app.websocket('/ws/jarvis')
async def websocket_endpoint(ws: WebSocket, session_id: str = ''):
    # ── WS Guard: validar IP e origem ─────────────────────────────────────────
    try:
        from middleware.ws_guard import check_ws_allowed
        client_ip = ws.client.host if ws.client else "unknown"
        origin = ws.headers.get("origin")
        allowed, reason = check_ws_allowed(client_ip, origin)
        if not allowed:
            await ws.close(code=1008, reason=reason)
            log.warning('[WS] Conexão recusada: %s — %s', client_ip, reason)
            return
    except Exception:
        pass  # Fail-open: se guard falhar, permite conexão
    await manager.connect(ws)

    # Accept a stable session_id from the client (stored in localStorage).
    # If none provided, generate a new one and return it so the client can persist it.
    if not session_id:
        session_id = f'ws_{uuid.uuid4().hex[:16]}'

    try:
        init_msg = idle_msg('JARVIS online. Awaiting your command, Sir.')
        init_msg['session_id'] = session_id
        await ws.send_json(init_msg)

        async def _heartbeat():
            while ws in manager.active:
                await asyncio.sleep(20)
                try:
                    await ws.send_json({'type': 'ping'})
                except Exception:
                    break

        asyncio.create_task(_heartbeat())

        # Uma ponte por conexão: a resposta de confirmação chega pelo mesmo
        # socket que fez a pergunta.
        ponte_ativa: dict = {}

        while True:
            data = await ws.receive_text()

            if not data.strip():
                continue
            if data.strip() == '__ping__':
                await ws.send_json({'type': 'pong'})
                continue

            # Resposta de confirmação de ação irreversível: libera a thread do
            # agente que está parada esperando e volta a ouvir.
            try:
                from core.agent_bridge import ler_resposta_confirmacao
                resposta = ler_resposta_confirmacao(data)
            except Exception:
                resposta = None
            if resposta is not None:
                id_pedido, aprovado = resposta
                ponte = ponte_ativa.get('ponte')
                atendido = ponte.responder(id_pedido, aprovado) if ponte else False
                await ws.send_json({'type': 'agent_confirm_ack',
                                    'id': id_pedido,
                                    'approved': aprovado,
                                    'handled': atendido})
                continue

            log.info('[WS] Input (%s): %s', session_id, data[:60])
            await ws.send_json(thinking_msg('Processing...'))

            # Pedido de trabalho vai para o laço com ferramentas; conversa segue
            # pelo caminho de sempre. Modelo pequeno com 9 schemas na frente de
            # um "bom dia" se perde, e cada iteração é uma ida ao LLM.
            usar_agente = False
            try:
                from core.agent_bridge import precisa_de_ferramentas
                usar_agente = precisa_de_ferramentas(data)
            except Exception as exc:
                log.debug('[WS] detector de tarefa indisponível: %s', exc)

            if usar_agente:
                full = await _rodar_agente(ws, data, session_id, ponte_ativa)
                if full is not None:
                    await ws.send_json({'type': 'done', 'action': 'agent',
                                        'full_response': full[:300]})
                    if full:
                        asyncio.create_task(_speak_bg(full))
                    await manager.broadcast(speaking_msg(full[:200]))
                    continue
                # Laço indisponível: cai no caminho de conversa sem reclamar.

            tokens: List[str] = []
            last_flush = [time.time()]

            async def on_tok(tok: str):
                tokens.append(tok)
                now = time.time()
                if len(tokens) % 3 == 0 or (now - last_flush[0]) > 0.08:
                    last_flush[0] = now
                    try:
                        await ws.send_json({
                            'type': 'token',
                            'content': ''.join(tokens[-3:])
                        })
                    except Exception:
                        pass

            full = ''
            t0 = time.time()
            try:
                try:
                    from agents.master_orchestrator import get_orchestrator
                    full = await asyncio.wait_for(
                        get_orchestrator().execute(data, session_id, on_token=on_tok),
                        timeout=120.0
                    )
                except (ImportError, Exception) as e1:
                    log.debug('[WS] Orch fallback: %s', e1)
                    try:
                        from ai.client import get_ai_client
                        from services.session_store import SYSTEM_PROMPT
                        msgs = [
                            {'role': 'system', 'content': SYSTEM_PROMPT},
                            {'role': 'user',   'content': data}
                        ]
                        full = await asyncio.wait_for(
                            get_ai_client().stream_chat(msgs, on_tok),
                            timeout=120.0
                        )
                    except Exception as e2:
                        log.debug('[WS] Stream fallback: %s', e2)
                        from services.chat_service import process_message
                        full = await asyncio.get_event_loop().run_in_executor(
                            None, process_message, data, session_id
                        )
                        if full:
                            await on_tok(full)

            except asyncio.TimeoutError:
                full = 'Request timed out, Sir. Please try again.'
                await on_tok(full)
            except Exception as e:
                log.error('[WS] Erro: %s', e)
                full = 'System error, Sir. Please try again.'
                await on_tok(full)

            elapsed = time.time() - t0
            log.info('[WS] Resposta em %.1fs', elapsed)

            await ws.send_json({
                'type': 'done',
                'action': 'chat',
                'full_response': (full or '')[:300],
                'latency_ms': int(elapsed * 1000),
            })

            if full:
                asyncio.create_task(_speak_bg(full))

            await manager.broadcast(speaking_msg((full or '')[:200]))

    except WebSocketDisconnect:
        log.info('[WS] Desconectado: %s', session_id)
        manager.disconnect(ws)
    except Exception as e:
        log.error('[WS] Erro fatal: %s', e)
        manager.disconnect(ws)


AGENT_WS_TIMEOUT = float(os.getenv('JARVIS_AGENT_WS_TIMEOUT', '900'))


async def _rodar_agente(ws, objetivo: str, session_id: str, ponte_ativa: dict):
    """
    Executa o laço com ferramentas e devolve o texto final.

    Devolve None quando o laço não está disponível — aí o chamador segue pelo
    caminho de conversa, que é o comportamento antigo e sempre funciona.
    """
    try:
        from core.agent_bridge import PonteAgente
    except Exception as exc:
        log.debug('[WS] laço de agente indisponível: %s', exc)
        return None

    from core.agent_bridge import ler_resposta_confirmacao

    ponte = PonteAgente(enviar=ws.send_json)
    ponte_ativa['ponte'] = ponte

    # Enquanto o laço roda, o handler principal não está lendo o socket — e a
    # confirmação que o laço espera chega justamente por ele. Sem este ouvinte
    # concorrente os dois ficam parados um pelo outro: o agente esperando a
    # autorização, o servidor esperando o agente.
    async def _ouvir_durante_a_tarefa():
        while True:
            texto = await ws.receive_text()
            if not texto.strip() or texto.strip() == '__ping__':
                continue
            resposta = ler_resposta_confirmacao(texto)
            if resposta is not None:
                id_pedido, aprovado = resposta
                atendido = ponte.responder(id_pedido, aprovado)
                await ws.send_json({'type': 'agent_confirm_ack',
                                    'id': id_pedido,
                                    'approved': aprovado,
                                    'handled': atendido})
            else:
                # Mensagem nova no meio da tarefa: avisa em vez de engolir.
                await ws.send_json({
                    'type': 'agent_busy',
                    'message': 'Estou no meio de uma tarefa, Sir. '
                               'Me manda de novo quando eu terminar.'})

    ouvinte = asyncio.create_task(_ouvir_durante_a_tarefa())
    try:
        resultado = await asyncio.wait_for(
            ponte.executar(objetivo, session_id=session_id),
            timeout=AGENT_WS_TIMEOUT,
        )
    except asyncio.TimeoutError:
        log.warning('[WS] agente excedeu %.0fs', AGENT_WS_TIMEOUT)
        return 'A tarefa passou do tempo limite, Sir. Posso retomar de onde parou.'
    except Exception as exc:
        log.error('[WS] agente falhou: %s', exc)
        return None                      # cai na conversa, não na mensagem de erro
    finally:
        ouvinte.cancel()
        ponte_ativa.pop('ponte', None)

    texto = (resultado.final_text or '').strip()
    if not texto:
        texto = ('Terminei o que dava, Sir, mas não consegui formular a resposta. '
                 f'Motivo: {resultado.stopped_reason}.')

    # O texto final vai como token para o frontend tratar igual a qualquer
    # resposta — o orb e o histórico não precisam saber que veio do laço.
    try:
        await ws.send_json({'type': 'token', 'content': texto})
    except Exception:
        pass
    return texto


async def _speak_bg(text: str):
    try:
        from voice_v2.output import speak
        await speak(text)
    except Exception as e:
        log.debug('[TTS] %s', e)


# ── Health & status ────────────────────────────────────────────────────────────
@app.get('/health')
async def health():
    from ai.client import get_ai_client
    ai_ok = False
    model = ''
    try:
        h = get_ai_client().health_check()
        ai_ok = h.get('ok', False)
        model = h.get('models', ['?'])[0] if ai_ok else ''
    except Exception:
        pass

    degraded = [] if ai_ok else ['ollama']
    return {
        'status': 'ok' if not degraded else 'degraded',
        'version': '6.0',
        'service': 'JARVIS API',
        'models': {'local_model': model or 'offline'},
        'degraded': degraded,
    }


@app.get('/status')
async def status():
    try:
        from observability.metrics import get_metrics
        uptime = get_metrics().snapshot().get('uptime', 0)
    except Exception:
        uptime = 0
    return {
        'jarvis': 'online',
        'version': '8.0',
        'model': os.getenv('JARVIS_MODEL', 'qwen2:0.5b'),
        'uptime_seconds': uptime,
        'voice': os.getenv('JARVIS_VOICE_ENABLED', 'true') == 'true',
    }


@app.get('/ping', include_in_schema=False)
async def ping():
    """Ultra-lightweight liveness probe — returns in <1ms."""
    return {'pong': True, 'ts': time.time()}


@app.get('/ready', include_in_schema=False)
async def ready():
    """Readiness probe — checks if Ollama is reachable."""
    from config import get_config
    cfg = get_config()
    try:
        import httpx
        async with httpx.AsyncClient(timeout=1.5) as c:
            r = await c.get(f"{cfg.ollama_url}/api/tags")
            ollama_ok = r.status_code == 200
    except Exception:
        ollama_ok = False
    status_code = 200 if ollama_ok else 503
    return JSONResponse(
        content={'ready': ollama_ok, 'ollama': 'up' if ollama_ok else 'down'},
        status_code=status_code,
    )


@app.get('/capabilities', include_in_schema=False)
async def capabilities():
    """Lists all JARVIS v8.0 capabilities and endpoints."""
    return {
        'version': '8.0',
        'features': {
            'chat': 'POST /chat — conversação inteligente com streaming SSE',
            'websocket': 'WS /ws/jarvis — chat em tempo real bidirecional',
            'voice': 'POST /voice/command — STT → LLM → TTS pipeline completo',
            'osint': 'POST /investigate — investigação OSINT (phone/IP/email/domain)',
            'code_analysis': 'POST /analyze — análise de código com 25+ linguagens',
            'architect': 'POST /architect — plano arquitetural completo com tech stack',
            'generate': {
                'code': 'POST /generate/code — gerar código a partir de descrição',
                'tests': 'POST /generate/tests — gerar suite de testes',
                'docs': 'POST /generate/docs — gerar documentação',
                'regex': 'POST /generate/regex — gerar + explicar regex',
                'diagram': 'POST /generate/diagram — gerar diagrama Mermaid',
                'api': 'POST /generate/api — gerar especificação REST API',
                'docker': 'POST /generate/docker — gerar Dockerfile + docker-compose',
                'readme': 'POST /generate/readme — gerar README.md profissional',
                'refactor': 'POST /generate/refactor — refatorar código',
                'convert': 'POST /generate/convert — converter entre linguagens',
                'explain': 'POST /generate/explain — explicar código/conceito',
                'fix': 'POST /generate/fix — corrigir código com erro',
                'review': 'POST /generate/review — code review profissional',
                'optimize': 'POST /generate/optimize — otimizar performance/legibilidade',
                'summarize': 'POST /generate/summarize — resumir texto/código/documento',
            },
            'tasks': 'POST /tasks — criar tarefa background + GET /tasks/{id} para status',
            'memory': 'GET /memory/search?q=... — busca semântica na memória',
            'agents': 'POST /agents/{role}/run — invocar agente especializado',
            'metrics': 'GET /metrics — métricas do sistema (CPU/RAM/disco/rede)',
            'health': 'GET /health — health check + Ollama status',
            'network': 'GET /network/info — IP local para conectar celular',
        },
        'power_modes': {
            'F2': 'OSINT Investigation',
            'F3': 'Code Analysis',
            'F4': 'System Architect',
            'F5': 'Generate Code (novo v8.0)',
            'F6': 'Summarize (novo v8.0)',
        },
        'agents': [
            'Master Orchestrator', 'Dev Senior', 'Security/OSINT', 'Architect',
            'QA/Testing', 'DevOps/Cloud', 'AI/ML', 'Project Manager', 'Critic',
        ],
    }


# ── /network — informações para acesso mobile e remoto ────────────────────────
@app.get('/network', tags=['System'])
async def network_info():
    """
    Retorna IPs locais da máquina para acesso de celular/tablet na mesma rede.
    Acesse http://<IP_LOCAL>:8000 no celular conectado ao mesmo Wi-Fi.
    """
    import socket
    ips = {}

    # IPs de todas as interfaces
    try:
        hostname = socket.gethostname()
        ips['hostname'] = hostname
        # IP principal (rota padrão)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ips['lan_ip'] = s.getsockname()[0]
    except Exception:
        ips['lan_ip'] = '127.0.0.1'

    port = _cfg.port if hasattr(_cfg, 'port') else 8000
    lan_ip = ips.get('lan_ip', '127.0.0.1')
    tailscale_ip = os.getenv('JARVIS_TAILSCALE_IP', '')

    access_urls = {
        'localhost': f'http://localhost:{port}',
        'lan': f'http://{lan_ip}:{port}',
    }
    if tailscale_ip:
        access_urls['tailscale'] = f'http://{tailscale_ip}:{port}'

    return {
        'lan_ip': lan_ip,
        'port': port,
        'hostname': ips.get('hostname', ''),
        'tailscale_ip': tailscale_ip or None,
        'access_urls': access_urls,
        'instructions': {
            'same_wifi': f'No celular, abra: http://{lan_ip}:{port}',
            'pwa_install': 'No browser mobile, clique em "Adicionar à tela inicial"',
            'remote': 'Para acesso remoto, instale Tailscale (tailscale.com) — gratuito',
        },
        'websocket': f'ws://{lan_ip}:{port}/ws/jarvis',
    }


# ── Global error handlers ──────────────────────────────────────────────────────
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(
        status_code=404,
        content={
            'error': 'Not Found',
            'message': f"Rota '{request.url.path}' não existe, Senhor.",
            'available_docs': '/docs',
            'capabilities': '/capabilities',
        },
    )


@app.exception_handler(500)
async def server_error_handler(request: Request, exc: Exception):
    req_id = request.headers.get("X-Request-ID", "unknown")
    log.error('[500] %s %s — req_id=%s — %s', request.method, request.url.path, req_id, exc)
    return JSONResponse(
        status_code=500,
        content={
            'error': 'Internal Server Error',
            'message': 'Erro interno, Senhor. Verifique os logs.',
            'request_id': req_id,
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    req_id = request.headers.get("X-Request-ID", "unknown")
    log.error('[UNHANDLED] %s %s — req_id=%s — %s: %s',
              request.method, request.url.path, req_id, type(exc).__name__, exc)
    return JSONResponse(
        status_code=500,
        content={
            'error': str(exc),
            'status': 500,
            'request_id': req_id,
        },
    )


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
