"""JARVIS OMEGA — implementar todos os módulos de uma vez."""
import pathlib, os

ROOT = pathlib.Path("C:/Users/cibernetico/JARVIS")

files = {}

# ── runtime/__init__.py ──────────────────────────────────────────────────────
files["backend/runtime/__init__.py"] = ""

# ── runtime/watchdog.py ──────────────────────────────────────────────────────
files["backend/runtime/watchdog.py"] = '''
import asyncio, logging, time
log = logging.getLogger("jarvis.watchdog")

class SystemWatchdog:
    def __init__(self):
        self._checks = {}
        self._failures = {}
        self._start = time.time()

    def register(self, name: str, fn):
        self._checks[name] = fn
        self._failures[name] = 0

    async def run(self, interval: int = 60):
        while True:
            await asyncio.sleep(interval)
            for name, fn in self._checks.items():
                try:
                    ok = await fn() if asyncio.iscoroutinefunction(fn) else fn()
                    if ok:
                        self._failures[name] = 0
                    else:
                        self._failures[name] += 1
                        log.warning("[WATCHDOG] %s falhou (%dx)", name, self._failures[name])
                except Exception as e:
                    log.error("[WATCHDOG] Erro em %s: %s", name, e)
                    self._failures[name] += 1

    def uptime(self) -> int:
        return int(time.time() - self._start)

    def status(self) -> dict:
        return {
            "uptime_seconds": self.uptime(),
            "checks": {k: {"failures": v} for k, v in self._failures.items()}
        }

_wd = None
def get_watchdog() -> SystemWatchdog:
    global _wd
    if _wd is None:
        _wd = SystemWatchdog()
    return _wd
'''.lstrip()

# ── core/event_bus.py ────────────────────────────────────────────────────────
files["backend/core/event_bus.py"] = '''
import asyncio, logging, time
from typing import Callable, Any
log = logging.getLogger("jarvis.eventbus")

class EventBus:
    def __init__(self):
        self._handlers: dict[str, list[Callable]] = {}
        self._history: list[dict] = []
        self._max_history = 1000

    def on(self, event: str, handler: Callable):
        self._handlers.setdefault(event, []).append(handler)
        return self

    async def emit(self, event: str, data: Any = None):
        entry = {"event": event, "data": data, "ts": time.time()}
        self._history.append(entry)
        if len(self._history) > self._max_history:
            self._history.pop(0)
        for h in self._handlers.get(event, []) + self._handlers.get("*", []):
            try:
                if asyncio.iscoroutinefunction(h):
                    asyncio.create_task(h(data))
                else:
                    h(data)
            except Exception as e:
                log.error("[EVENT_BUS] Erro em %s: %s", event, e)

    def get_history(self, event: str = None, limit: int = 50) -> list:
        h = [e for e in self._history if not event or e["event"] == event]
        return h[-limit:]

    def get_stats(self) -> dict:
        from collections import Counter
        counts = Counter(e["event"] for e in self._history)
        return {"total_events": len(self._history), "by_type": dict(counts)}

_bus = None
def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
'''.lstrip()

# ── observability/__init__.py ────────────────────────────────────────────────
files["backend/observability/__init__.py"] = ""

# ── observability/metrics.py ─────────────────────────────────────────────────
files["backend/observability/metrics.py"] = '''
import time, logging
from collections import defaultdict, deque
log = logging.getLogger("jarvis.metrics")

class RuntimeMetrics:
    def __init__(self):
        self._counters = defaultdict(int)
        self._timings  = defaultdict(lambda: deque(maxlen=200))
        self._gauges   = {}
        self._start    = time.time()

    def inc(self, key: str, val: int = 1):
        self._counters[key] += val

    def timing(self, key: str, seconds: float):
        self._timings[key].append(seconds)

    def gauge(self, key: str, val):
        self._gauges[key] = val

    def snapshot(self) -> dict:
        snap = {
            "uptime": int(time.time() - self._start),
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "timings": {}
        }
        for k, vals in self._timings.items():
            lst = list(vals)
            if lst:
                snap["timings"][k] = {
                    "count": len(lst),
                    "avg_ms": round(sum(lst)/len(lst)*1000, 1),
                    "max_ms": round(max(lst)*1000, 1),
                    "p95_ms": round(sorted(lst)[int(len(lst)*0.95)]*1000, 1)
                }
        return snap

_m = None
def get_metrics() -> RuntimeMetrics:
    global _m
    if _m is None:
        _m = RuntimeMetrics()
    return _m
'''.lstrip()

# ── observability/system_metrics.py ─────────────────────────────────────────
files["backend/observability/system_metrics.py"] = '''
import asyncio, logging
log = logging.getLogger("jarvis.sysmetrics")

async def collect(interval: int = 30):
    while True:
        try:
            import psutil
            from backend.observability.metrics import get_metrics
            m = get_metrics()
            m.gauge("cpu_percent",  psutil.cpu_percent(interval=None))
            vm = psutil.virtual_memory()
            m.gauge("ram_percent",  vm.percent)
            m.gauge("ram_used_mb",  vm.used // 1024 // 1024)
            m.gauge("ram_total_mb", vm.total // 1024 // 1024)
            try:
                disk = psutil.disk_usage("C:/")
                m.gauge("disk_percent", disk.percent)
                m.gauge("disk_free_gb", disk.free // 1024**3)
            except Exception:
                pass
        except ImportError:
            log.debug("[SYSMETRICS] psutil nao instalado")
            return
        except Exception as e:
            log.warning("[SYSMETRICS] %s", e)
        await asyncio.sleep(interval)
'''.lstrip()

# ── experience/__init__.py ───────────────────────────────────────────────────
files["backend/experience/__init__.py"] = ""

# ── experience/engine.py ─────────────────────────────────────────────────────
files["backend/experience/engine.py"] = '''
import sqlite3, json, time, pathlib, logging, os
log = logging.getLogger("jarvis.experience")

def _get_db_path() -> pathlib.Path:
    try:
        from backend.config import get_config
        d = pathlib.Path(get_config().data_dir)
    except Exception:
        d = pathlib.Path("data")
    d.mkdir(exist_ok=True)
    return d / "experience.db"

class ExperienceEngine:
    def __init__(self):
        self._db = _get_db_path()
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self._db) as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS experiences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                problem TEXT DEFAULT '',
                solution TEXT DEFAULT '',
                outcome TEXT DEFAULT '',
                tags TEXT DEFAULT '[]',
                confidence REAL DEFAULT 1.0,
                times_used INTEGER DEFAULT 0,
                created_at REAL DEFAULT (unixepoch()),
                updated_at REAL DEFAULT (unixepoch())
            );
            CREATE TABLE IF NOT EXISTS reflections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                what_worked TEXT,
                what_failed TEXT,
                pattern TEXT,
                improvement TEXT,
                created_at REAL DEFAULT (unixepoch())
            );
            CREATE INDEX IF NOT EXISTS idx_exp_cat ON experiences(category);
            CREATE INDEX IF NOT EXISTS idx_exp_title ON experiences(title);
            """)

    def save(self, category: str, title: str, problem: str = "",
             solution: str = "", outcome: str = "",
             tags: list = None, confidence: float = 1.0) -> int:
        with sqlite3.connect(self._db) as c:
            cur = c.execute(
                "INSERT INTO experiences (category,title,problem,solution,outcome,tags,confidence) VALUES(?,?,?,?,?,?,?)",
                (category, title[:200], problem[:3000], solution[:8000], outcome[:1000], json.dumps(tags or []), confidence)
            )
            return cur.lastrowid

    def find(self, query: str, category: str = None, limit: int = 5) -> list:
        if not query:
            with sqlite3.connect(self._db) as c:
                rows = c.execute("SELECT * FROM experiences ORDER BY times_used DESC, created_at DESC LIMIT ?", (limit,)).fetchall()
        else:
            q = f"%{query[:60]}%"
            with sqlite3.connect(self._db) as c:
                if category:
                    rows = c.execute("SELECT * FROM experiences WHERE category=? AND (title LIKE ? OR problem LIKE ? OR solution LIKE ?) ORDER BY times_used DESC, confidence DESC LIMIT ?", (category, q, q, q, limit)).fetchall()
                else:
                    rows = c.execute("SELECT * FROM experiences WHERE title LIKE ? OR problem LIKE ? OR solution LIKE ? ORDER BY times_used DESC, confidence DESC LIMIT ?", (q, q, q, limit)).fetchall()
        cols = ["id","category","title","problem","solution","outcome","tags","confidence","times_used","created_at","updated_at"]
        return [dict(zip(cols, r)) for r in rows]

    def use(self, exp_id: int):
        with sqlite3.connect(self._db) as c:
            c.execute("UPDATE experiences SET times_used=times_used+1, updated_at=unixepoch() WHERE id=?", (exp_id,))

    def reflect(self, session_id: str, worked: str, failed: str, pattern: str = "", improvement: str = ""):
        with sqlite3.connect(self._db) as c:
            c.execute("INSERT INTO reflections (session_id,what_worked,what_failed,pattern,improvement) VALUES(?,?,?,?,?)", (session_id, worked[:1000], failed[:1000], pattern[:500], improvement[:500]))

    def stats(self) -> dict:
        with sqlite3.connect(self._db) as c:
            total = c.execute("SELECT COUNT(*) FROM experiences").fetchone()[0]
            cats = c.execute("SELECT category, COUNT(*) FROM experiences GROUP BY category").fetchall()
            refs = c.execute("SELECT COUNT(*) FROM reflections").fetchone()[0]
        return {"total": total, "categories": dict(cats), "reflections": refs}

_exp = None
def get_experience() -> ExperienceEngine:
    global _exp
    if _exp is None:
        _exp = ExperienceEngine()
    return _exp
'''.lstrip()

# ── experience/reflection.py ─────────────────────────────────────────────────
files["backend/experience/reflection.py"] = '''
import asyncio, logging, time
log = logging.getLogger("jarvis.reflection")

class ReflectionEngine:
    def __init__(self, batch_size: int = 10):
        self._pending = []
        self._batch_size = batch_size

    def record(self, session_id: str, query: str, response: str,
               duration: float, agent: str, success: bool):
        self._pending.append({
            "session": session_id, "query": query[:200],
            "response": response[:300], "duration": duration,
            "agent": agent, "success": success, "ts": time.time()
        })
        if len(self._pending) >= self._batch_size:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._reflect())
            except Exception:
                pass

    async def _reflect(self):
        if not self._pending:
            return
        batch = self._pending[:self._batch_size]
        self._pending = self._pending[self._batch_size:]
        try:
            from backend.experience.engine import get_experience
            from backend.services.llm_service import call_llm
            summary = "\\n".join([
                f"Q:{i['query'][:60]}|A:{i['response'][:60]}|{'OK' if i['success'] else 'FAIL'}|{i['duration']:.1f}s"
                for i in batch
            ])
            resp = await call_llm([
                {"role": "system", "content": "Analise interacoes de IA. Responda JSON com: worked, failed, pattern, improvement. Seja breve."},
                {"role": "user", "content": f"Analise {len(batch)} interacoes:\\n{summary}"}
            ])
            import json
            try:
                start = resp.find("{"); end = resp.rfind("}") + 1
                if start >= 0:
                    data = json.loads(resp[start:end])
                    get_experience().reflect(
                        session_id=batch[0]["session"],
                        worked=data.get("worked",""),
                        failed=data.get("failed",""),
                        pattern=data.get("pattern",""),
                        improvement=data.get("improvement","")
                    )
            except Exception:
                pass
        except Exception as e:
            log.warning("[REFLECT] Falhou: %s", e)

_ref = None
def get_reflection() -> ReflectionEngine:
    global _ref
    if _ref is None:
        _ref = ReflectionEngine()
    return _ref
'''.lstrip()

# ── research_runtime/__init__.py ─────────────────────────────────────────────
files["backend/research_runtime/__init__.py"] = ""

# ── research_runtime/researcher.py ───────────────────────────────────────────
files["backend/research_runtime/researcher.py"] = '''
import logging, asyncio, httpx
log = logging.getLogger("jarvis.research")

class DeepResearcher:
    def __init__(self):
        self.active = False
        self.current_query = ""
        self.steps = []

    async def research(self, query: str, session_id: str, on_update=None) -> str:
        self.active = True
        self.current_query = query
        self.steps = []
        log.info("[RESEARCH] Iniciando: %s", query[:60])

        async def step(name: str, result: str):
            self.steps.append({"step": name, "result": result[:300]})
            if on_update:
                try:
                    await on_update({"step": name, "preview": result[:100]})
                except Exception:
                    pass

        try:
            from backend.experience.engine import get_experience
            similar = get_experience().find(query, limit=3)
            if similar:
                exp_txt = "\\n".join([f"- {e['title']}: {e['solution'][:100]}" for e in similar])
                await step("experiencias_anteriores", exp_txt)

            analysis = await self._analyze(query)
            await step("analise", analysis)

            gh = await self._search_github(query)
            if gh:
                await step("github", gh)

            solution = await self._synthesize(query, analysis, similar, gh)
            await step("sintese", solution)

            get_experience().save(
                category="research", title=query[:80],
                problem=query, solution=solution,
                tags=["deep_research", session_id]
            )

            from backend.core.event_bus import get_event_bus
            await get_event_bus().emit("research.completed", {"query": query[:80], "steps": len(self.steps), "session": session_id})

            return solution
        finally:
            self.active = False

    async def _analyze(self, query: str) -> str:
        try:
            from backend.services.llm_service import call_llm
            return await call_llm([
                {"role": "system", "content": "Analista tecnico senior. Identifique causa raiz, abordagens, riscos. Seja conciso."},
                {"role": "user", "content": query}
            ])
        except Exception as e:
            return f"Analise indisponivel: {e}"

    async def _search_github(self, query: str) -> str:
        try:
            clean = query[:60].replace(" ", "+")
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.get(
                    f"https://api.github.com/search/repositories?q={clean}&sort=stars&per_page=3",
                    headers={"Accept": "application/vnd.github.v3+json"}
                )
                if r.status_code == 200:
                    items = r.json().get("items", [])[:3]
                    return "\\n".join([f"- {i['full_name']} [{i['stargazers_count']}]: {(i.get('description') or '')[:60]}" for i in items])
        except Exception as e:
            log.debug("[RESEARCH] GitHub: %s", e)
        return ""

    async def _synthesize(self, query, analysis, similar, github) -> str:
        try:
            from backend.services.llm_service import call_llm
            ctx = [f"Problema: {query}", f"Analise: {analysis[:400]}"]
            if similar:
                ctx.append("Experiencias: " + "; ".join([e["title"] for e in similar]))
            if github:
                ctx.append(f"GitHub: {github[:300]}")
            return await call_llm([
                {"role": "system", "content": "Arquiteto senior de IA. Sintetize solucao clara e implementavel em portugues. Seja direto e tecnico."},
                {"role": "user", "content": "\\n".join(ctx)}
            ])
        except Exception as e:
            return f"Sintese indisponivel: {e}"

    def status(self) -> dict:
        return {"active": self.active, "query": self.current_query[:80], "steps_done": len(self.steps), "steps": self.steps[-5:]}

_res = None
def get_researcher() -> DeepResearcher:
    global _res
    if _res is None:
        _res = DeepResearcher()
    return _res
'''.lstrip()

# ── routes/experience.py ─────────────────────────────────────────────────────
files["backend/routes/experience.py"] = '''
from fastapi import APIRouter, Body
from backend.experience.engine import get_experience

router = APIRouter()

@router.get("/stats")
def exp_stats():
    return get_experience().stats()

@router.get("/search")
def exp_search(q: str = "", category: str = None, limit: int = 5):
    return {"results": get_experience().find(q, category, limit)}

@router.post("/save")
async def exp_save(
    category: str = Body(...),
    title: str = Body(...),
    problem: str = Body(""),
    solution: str = Body(""),
    tags: list = Body([])
):
    from backend.core.event_bus import get_event_bus
    id_ = get_experience().save(category, title, problem, solution, tags=tags)
    await get_event_bus().emit("experience.saved", {"id": id_, "title": title})
    return {"id": id_, "saved": True}

@router.get("/recent")
def exp_recent(limit: int = 10):
    return get_experience().find("", limit=limit)
'''.lstrip()

# ── routes/research.py ───────────────────────────────────────────────────────
files["backend/routes/research.py"] = '''
from fastapi import APIRouter, Body
from backend.research_runtime.researcher import get_researcher

router = APIRouter()

@router.post("/start")
async def start_research(
    query: str = Body(...),
    session_id: str = Body("research")
):
    researcher = get_researcher()
    result = await researcher.research(query, session_id)
    return {"result": result, "steps": researcher.steps}

@router.get("/status")
def research_status():
    return get_researcher().status()
'''.lstrip()

# ── routes/jarvis_tts.py ─────────────────────────────────────────────────────
files["backend/routes/jarvis_tts.py"] = '''
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
import asyncio, tempfile, uuid, os, logging
from backend.config import get_config

router = APIRouter()
log = logging.getLogger("jarvis.tts")

@router.get("/tts")
async def tts(
    text: str = Query(..., description="Texto para sintetizar"),
    lang: str = Query("pt")
):
    """Voz JARVIS Iron Man - PT-BR, grave."""
    if not text or not text.strip():
        raise HTTPException(400, "text obrigatorio")

    cfg = get_config()
    text = text.strip()[:500]

    try:
        import edge_tts
    except ImportError:
        raise HTTPException(503, "edge-tts nao instalado: pip install edge-tts")

    try:
        path = os.path.join(tempfile.gettempdir(), f"jarvis_{uuid.uuid4().hex}.mp3")
        comm = edge_tts.Communicate(text, cfg.tts_voice, rate=cfg.tts_rate, pitch=cfg.tts_pitch)
        await comm.save(path)

        if not os.path.exists(path) or os.path.getsize(path) < 100:
            raise Exception("Audio invalido ou muito pequeno")

        with open(path, "rb") as f:
            data = f.read()
        try:
            os.unlink(path)
        except Exception:
            pass

        try:
            from backend.observability.metrics import get_metrics
            get_metrics().inc("tts.requests")
            get_metrics().inc("tts.chars", len(text))
        except Exception:
            pass

        try:
            from backend.core.event_bus import get_event_bus
            asyncio.create_task(get_event_bus().emit("voice.tts", {"chars": len(text)}))
        except Exception:
            pass

        return Response(
            content=data,
            media_type="audio/mpeg",
            headers={"Cache-Control": "no-cache", "X-JARVIS-TTS": "ok", "X-Chars": str(len(text))}
        )
    except HTTPException:
        raise
    except Exception as e:
        log.error("[TTS] Erro: %s", e)
        raise HTTPException(500, f"TTS erro: {e}")
'''.lstrip()

# Escrever todos os arquivos
created = []
for rel_path, content in files.items():
    full = ROOT / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    created.append(rel_path)
    print(f"  ✅ {rel_path}")

print(f"\n{len(created)} arquivos criados/atualizados")
