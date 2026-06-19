"""
check_jarvis.py -- Diagnostico completo do JARVIS antes de ligar na escola.
Uso: python check_jarvis.py
"""
from __future__ import annotations
import sys, os, sqlite3, shutil, json, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

_issues = 0
_warns  = 0

def check(label: str, ok: bool, detail: str = "", warn: bool = False):
    global _issues, _warns
    tag = "[OK]   " if ok else ("[AVISO]" if warn else "[ERRO] ")
    if not ok and not warn:
        _issues += 1
    elif not ok and warn:
        _warns += 1
    msg = f"  {tag}  {label}"
    if detail:
        msg += f"  ->  {detail}"
    print(msg)


print()
print("=" * 58)
print("  JARVIS -- Diagnostico do Sistema")
print("=" * 58)

# ── 1. Python ─────────────────────────────────────────────
print("\n[1] Python")
v = sys.version_info
check("Python 3.11+", v >= (3, 11), f"{v.major}.{v.minor}.{v.micro}")

# ── 2. Dependencias ───────────────────────────────────────
print("\n[2] Dependencias")
deps = {"fastapi": "FastAPI", "uvicorn": "Uvicorn", "httpx": "httpx"}
optional = {
    "sqlalchemy":           "SQLAlchemy",
    "chromadb":             "ChromaDB (RAG)",
    "sentence_transformers":"sentence-transformers (RAG embeddings)",
    "faster_whisper":       "faster-whisper (STT)",
    "edge_tts":             "edge-tts (TTS)",
    "sounddevice":          "sounddevice (microfone)",
}
for pkg, name in deps.items():
    try:
        __import__(pkg)
        check(name, True)
    except ImportError:
        check(name, False, "pip install " + pkg)

for pkg, name in optional.items():
    try:
        __import__(pkg)
        check(name, True)
    except ImportError:
        check(name, False, "nao instalado -- funcionalidade opcional desabilitada", warn=True)

# ── 3. Ollama ─────────────────────────────────────────────
print("\n[3] Ollama")
ollama_url = os.getenv("JARVIS_OLLAMA_URL", "http://127.0.0.1:11434")
try:
    with urllib.request.urlopen(f"{ollama_url}/api/tags", timeout=3) as r:
        data = json.loads(r.read())
    models = [m["name"] for m in data.get("models", [])]
    check("Ollama respondendo", True, ollama_url)
    check("Modelos disponiveis", bool(models), ", ".join(models[:5]) or "nenhum")
    wanted = os.getenv("JARVIS_MODEL", "qwen2:0.5b")
    has_model = any(wanted in m for m in models)
    check(f"Modelo '{wanted}' presente", has_model,
          "" if has_model else f"execute: ollama pull {wanted}")
except Exception as e:
    check("Ollama respondendo", False, str(e)[:80])
    check("Modelos disponiveis", False, "Ollama offline")

# ── 4. Banco de dados ─────────────────────────────────────
print("\n[4] Banco de dados")
db_path = ROOT / "backend" / "security.db"
try:
    if db_path.exists():
        con = sqlite3.connect(str(db_path))
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        con.close()
        check("security.db acessivel", True, f"{len(tables)} tabelas")
    else:
        check("security.db", False, "sera criado ao iniciar", warn=True)
except Exception as e:
    check("security.db", False, str(e))

# ── 5. Recursos ───────────────────────────────────────────
print("\n[5] Recursos")
total, used, free = shutil.disk_usage(ROOT)
free_gb = free / 1e9
check("Espaco em disco (>2GB)", free_gb > 2, f"{free_gb:.1f} GB livres")

try:
    import psutil
    ram = psutil.virtual_memory()
    ram_gb = ram.available / 1e9
    check("RAM disponivel (>1GB)", ram_gb > 1, f"{ram_gb:.1f} GB disponiveis")
except ImportError:
    check("RAM", False, "psutil nao instalado -- skip", warn=True)

# ── 6. Frontend ───────────────────────────────────────────
print("\n[6] Frontend")
frontend = ROOT / "frontend"
for fname in ["index.html", "app.js", "style.css", "manifest.json"]:
    check(fname, (frontend / fname).exists())

# ── 7. Configuracao ───────────────────────────────────────
print("\n[7] Configuracao (.env)")
env_file = ROOT / ".env"
if env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file, override=False)
    except ImportError:
        pass
    check(".env encontrado", True)
    has_key = bool(os.getenv("JARVIS_SECRET_KEY"))
    check("JARVIS_SECRET_KEY", has_key,
          "" if has_key else "vazio -- auth desabilitada (ok para dev local)", warn=not has_key)
else:
    check(".env encontrado", False, "crie a partir de .env.example")

# ── Resumo ────────────────────────────────────────────────
print()
print("=" * 58)
if _issues == 0:
    print(f"  OK  JARVIS pronto! ({_warns} aviso(s))")
    print("  Execute: .\\start_jarvis.bat  (ou start_jarvis_escola.bat)")
else:
    print(f"  ERRO: {_issues} problema(s) critico(s), {_warns} aviso(s).")
    print("  Corrija os [ERRO] acima antes de iniciar.")
print("=" * 58)
print()
sys.exit(0 if _issues == 0 else 1)
