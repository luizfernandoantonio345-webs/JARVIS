import pathlib
import platform
import sys
import time

sys.path.insert(0, "backend")

print("=== JARVIS AUDIT REPORT - BEFORE ===", flush=True)
print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
print()

print("=== AMBIENTE ===", flush=True)
print(f"Python: {sys.version}", flush=True)
print(f"OS: {platform.system()} {platform.version()[:30]}", flush=True)
print(f"venv: {sys.prefix}", flush=True)
print()

print("=== OLLAMA LOCAL ===", flush=True)
try:
    import requests
except Exception as exc:
    requests = None
    print(f"  FAIL: requests indisponivel - {exc}", flush=True)

if requests:
    for url in ["http://localhost:11434", "http://127.0.0.1:11434"]:
        try:
            r = requests.get(f"{url}/api/tags", timeout=3)
            models = [m["name"] for m in r.json().get("models", [])]
            print(f"  OK: {url} - modelos: {models}", flush=True)
            break
        except Exception as exc:
            print(f"  FAIL: {url} - {exc}", flush=True)

print()
print("=== BACKEND ===", flush=True)
if requests:
    try:
        r = requests.get("http://localhost:8000/health", timeout=5)
        d = r.json()
        print(f"  Status: {d.get('status')}", flush=True)
        print(f"  Versao: {d.get('version')}", flush=True)
        print(f"  Uptime: {d.get('uptime')}", flush=True)
        print(f"  Degraded: {d.get('degraded', [])}", flush=True)
    except Exception as exc:
        print(f"  OFFLINE: {exc}", flush=True)

print()
print("=== ENDPOINTS ===", flush=True)
if requests:
    endpoints = [
        ("GET", "/health", None, 5),
        ("GET", "/", None, 5),
        ("POST", "/chat", {"message": "test", "session_id": "audit"}, 20),
        ("GET", "/tts-iron?text=test", None, 10),
        ("GET", "/experience/stats", None, 5),
        ("GET", "/api-metrics/runtime", None, 5),
        ("GET", "/research/status", None, 5),
    ]
    for method, path, body, timeout in endpoints:
        try:
            if method == "GET":
                r = requests.get(f"http://localhost:8000{path}", timeout=timeout)
            else:
                r = requests.post(
                    f"http://localhost:8000{path}", json=body, timeout=timeout
                )
            print(f"  {r.status_code} {method} {path}", flush=True)
        except Exception as exc:
            print(f"  FAIL {method} {path} - {str(exc)[:80]}", flush=True)

print()
print("=== IMPORTS ===", flush=True)
mods = [
    "config",
    "ai.client",
    "services.chat_service",
    "services.llm_service",
    "services.session_store",
    "agents.master_orchestrator",
    "memory.persistent_memory",
    "voice_v2.output",
    "voice_v2.resilient_loader",
    "experience.engine",
    "observability.metrics",
    "research_runtime.researcher",
    "runtime.watchdog",
    "core.event_bus",
]
for mod in mods:
    try:
        __import__(mod)
        print(f"  OK  : {mod}", flush=True)
    except Exception as exc:
        print(f"  FAIL: {mod} - {str(exc)[:80]}", flush=True)

print()
print("=== DUPLICAÇÕES ===", flush=True)
backend = pathlib.Path("backend")
for v1, v2 in [
    ("voice", "voice_v2"),
    ("memory", "memory_v2"),
    ("autonomy", "autonomy_v2"),
    ("behavior", "behavior_v2"),
]:
    if (backend / v1).exists() and (backend / v2).exists():
        print(f"  DUP: {v1}/ e {v2}/ coexistem", flush=True)

frontend = pathlib.Path("frontend")
print(f"  HTMLs frontend: {[h.name for h in frontend.glob('*.html')]}", flush=True)
print(f"  BATs raiz: {[b.name for b in pathlib.Path('.').glob('*.bat')]}", flush=True)
print(f"  PYs raiz: {[p.name for p in pathlib.Path('.').glob('*.py')]}", flush=True)

print()
print("=== VOZ ===", flush=True)
for dep in ["edge_tts", "faster_whisper", "sounddevice", "soundfile", "pyttsx3", "openwakeword"]:
    try:
        __import__(dep)
        print(f"  OK  : {dep}", flush=True)
    except Exception:
        print(f"  MISS: {dep}", flush=True)

print()
print("=== FIM RELATÓRIO ANTES ===", flush=True)
