"""JARVIS Backend — FastAPI v6.0"""
import asyncio, logging, os, sys, time
from typing import List

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

LOG_DIR = os.path.join(BACKEND_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            os.path.join(LOG_DIR, 'jarvis.log'),
            encoding='utf-8'
        ),
    ]
)
log = logging.getLogger('JARVIS')

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from config import get_config
from schemas.ws_messages import idle_msg, speaking_msg, thinking_msg

app = FastAPI(title='JARVIS v6.0', version='6.0.0')

app.add_middleware(CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

FRONTEND_DIR = os.path.join(
    os.path.dirname(BACKEND_DIR), 'frontend'
)
if os.path.exists(FRONTEND_DIR):
    app.mount('/static', StaticFiles(directory=FRONTEND_DIR),
              name='static')

@app.get('/', include_in_schema=False)
async def serve_frontend():
    index = os.path.join(FRONTEND_DIR, 'index.html')
    if os.path.exists(index):
        return FileResponse(index)
    return {'message': 'JARVIS API v6.0'}

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

def _mount_routers():
    cfg_map = [
        ('routes.health',    '',          True),
        ('routes.chat',      '/chat',     True),
        ('routes.agents',    '/agents',   False),
    ]
    for module, prefix, required in cfg_map:
        try:
            mod = __import__(module, fromlist=['router'])
            app.include_router(mod.router, prefix=prefix)
            log.info('[ROUTES] Carregado: %s%s', module, prefix)
        except ImportError as e:
            if required:
                log.error('[ROUTES] CRITICO %s: %s', module, e)
            else:
                log.debug('[ROUTES] Opcional nao carregado: %s', module)
        except Exception as e:
            log.warning('[ROUTES] %s falhou: %s', module, e)

@app.on_event('startup')
async def startup():
    log.info('='*50)
    log.info('JARVIS v6.0 iniciando...')
    cfg = get_config()
    log.info('Ollama: %s', cfg.ollama_url)
    log.info('Model : %s', cfg.local_model)

    _mount_routers()

    asyncio.create_task(_init_voice())
    asyncio.create_task(_prewarm_ollama())

    await manager.broadcast(idle_msg('JARVIS online. Ready, Sir.'))
    log.info('JARVIS pronto.')
    log.info('='*50)

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

async def _speak_boot():
    await asyncio.sleep(1)
    try:
        from voice_v2.output import speak
        await speak(
            'All systems online. Good evening, Sir. '
            'J.A.R.V.I.S. is ready.'
        )
    except Exception as e:
        log.debug('[BOOT_TTS] %s', e)

async def _prewarm_ollama():
    await asyncio.sleep(5)
    try:
        from ai.client import get_ai_client
        get_ai_client().call([
            {'role': 'user', 'content': 'respond with: ready'}
        ])
        log.info('[PREWARM] Ollama pre-carregado')
    except Exception as e:
        log.warning('[PREWARM] %s', e)

@app.websocket('/ws/jarvis')
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    session_id = f'ws_{id(ws)}'

    try:
        await ws.send_json(
            idle_msg('JARVIS online. Awaiting your command, Sir.')
        )

        async def _hb():
            while ws in manager.active:
                await asyncio.sleep(20)
                try:
                    await ws.send_json({'type': 'ping'})
                except Exception:
                    break
        asyncio.create_task(_hb())

        while True:
            data = await ws.receive_text()

            if not data.strip():
                continue
            if data.strip() == '__ping__':
                await ws.send_json({'type': 'pong'})
                continue

            log.info('[WS] Input (%s): %s', session_id, data[:50])
            await ws.send_json(thinking_msg('Processing...'))

            tokens: List[str] = []
            last_flush = [time.time()]

            async def on_tok(tok: str):
                tokens.append(tok)
                now = time.time()
                if len(tokens) % 3 == 0 or (now - last_flush[0]) > 0.08:
                    last_flush[0] = now
                    combined = ''.join(tokens[-3:])
                    try:
                        await ws.send_json({
                            'type': 'token',
                            'content': combined
                        })
                    except Exception:
                        pass

            full = ''
            t0 = time.time()
            try:
                try:
                    from agents.master_orchestrator import get_orchestrator
                    full = await asyncio.wait_for(
                        get_orchestrator().execute(
                            data, session_id, on_token=on_tok
                        ),
                        timeout=120.0
                    )
                except (ImportError, Exception) as e1:
                    log.debug('[WS] Orch: %s', e1)
                    try:
                        from ai.client import get_ai_client
                        from services.session_store import SYSTEM_PROMPT
                        msgs = [
                            {'role': 'system', 'content': SYSTEM_PROMPT},
                            {'role': 'user', 'content': data}
                        ]
                        full = await asyncio.wait_for(
                            get_ai_client().stream_chat(msgs, on_tok),
                            timeout=120.0
                        )
                    except Exception as e2:
                        log.debug('[WS] Stream: %s', e2)
                        from services.chat_service import process_message
                        full = await asyncio.get_event_loop()\
                            .run_in_executor(
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

async def _speak_bg(text: str):
    try:
        from voice_v2.output import speak
        await speak(text)
    except Exception as e:
        log.debug('[TTS] %s', e)

@app.get('/health')
async def health():
    from ai.client import get_ai_client
    ai_ok = False
    model = ''
    try:
        h = get_ai_client().health_check()
        ai_ok = h.get('ok', False)
        model = h.get('models', ['?'])[0] if ai_ok else ''
    except Exception: pass

    degraded = []
    if not ai_ok:
        degraded.append('ollama')

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
        snap = get_metrics().snapshot()
        uptime = snap.get('uptime', 0)
    except Exception:
        uptime = 0
    return {
        'jarvis': 'online',
        'model': os.getenv('JARVIS_MODEL', 'qwen2:0.5b'),
        'uptime_seconds': uptime,
        'voice': os.getenv('JARVIS_VOICE_ENABLED', 'true') == 'true',
    }

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
