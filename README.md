<div align="center">

# J.A.R.V.I.S.

**Just A Rather Very Intelligent System**

Personal AI assistant — 100% local, offline-first, no cloud required.

[![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![Ollama](https://img.shields.io/badge/Ollama-local_LLM-black?logo=ollama)](https://ollama.com)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

</div>

---

## What is JARVIS?

JARVIS is a fully local AI assistant inspired by Iron Man's J.A.R.V.I.S. It runs entirely on your machine — no data leaves your computer, no subscriptions, no API keys required (unless you choose to enable them). It uses [Ollama](https://ollama.com) to run large language models locally and exposes a full API via FastAPI.

**Highlights:**
- Real-time chat via WebSocket with streaming tokens
- 8 specialized AI agents (Dev, Architect, Debugger, Reviewer, Security, Planner, Executor, System)
- Voice input (STT via faster-whisper) and output (TTS via edge-tts)
- Wake word detection ("Hey JARVIS")
- Semantic memory with RAG (ChromaDB + sentence-transformers)
- Hardened security system (threat detection, IP blocking, token auth, audit log)
- Modern SPA frontend (no framework — pure HTML/CSS/JS)
- Auto model selection based on available RAM

---

## Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| OS | Windows 10 | Windows 10/11 |
| Python | 3.11 | 3.11 |
| RAM | 4 GB | 16+ GB |
| Storage | 3 GB | 10 GB |
| [Ollama](https://ollama.com) | Latest | Latest |

**Ollama models by RAM:**

| Available RAM | Model | Quality |
|--------------|-------|---------|
| 4–6 GB | `qwen2:0.5b` | Basic |
| 6–12 GB | `qwen2:1.5b` | Good |
| 12–28 GB | `llama3.2:3b` | Great |
| 32 GB+ | `mistral:7b` | Best |

---

## Quick Start

### 1. Install Ollama
Download and install from [ollama.com](https://ollama.com), then pull a model:
```bash
ollama pull qwen2:0.5b
```

### 2. Setup Python environment
```bash
git clone https://github.com/luizfernandoantonio345-webs/JARVIS.git
cd JARVIS

python -m venv venv311
venv311\Scripts\pip install -r backend\requirements.txt
```

### 3. Configure (optional)
```bash
copy .env.example .env
# Edit .env if needed (default config works out of the box)
```

### 4. Start JARVIS
```bash
start.bat
```

JARVIS will auto-detect your RAM, pick the best model, start Ollama, and open the interface at `http://localhost:8000`.

---

## Project Structure

```
JARVIS/
├── backend/                  # FastAPI application
│   ├── main.py               # Entry point, WebSocket, lifecycle
│   ├── config.py             # Centralized config via Pydantic
│   ├── agents/               # 8 specialized AI agents
│   │   ├── base_agent.py
│   │   ├── dev_agent.py
│   │   ├── architect_agent.py
│   │   ├── debugger_agent.py
│   │   ├── reviewer_agent.py
│   │   ├── security_agent.py
│   │   ├── planner_agent.py
│   │   └── executor_agent.py
│   ├── routes/               # 11 HTTP routers
│   │   ├── chat.py           # POST /chat, GET /chat/stream
│   │   ├── agents.py         # GET /agents/, POST /agents/{role}/run
│   │   ├── security.py       # /security/* (15+ endpoints)
│   │   ├── health.py         # GET /health, /status, /health/deep
│   │   ├── voice.py          # POST /voice/command
│   │   ├── memory.py         # GET /memory/search
│   │   ├── investigate.py    # POST /investigate/{type} (OSINT)
│   │   ├── analyze.py        # POST /analyze/code
│   │   ├── architect.py      # POST /architect
│   │   ├── generate.py       # POST /generate/*
│   │   └── tasks.py          # POST /tasks/run
│   ├── security/             # Hardened security layer
│   │   ├── auth_manager.py   # HMAC-SHA256 tokens, TTL, allowlist
│   │   ├── threat_detector.py# 11 attack pattern types
│   │   └── guardian.py       # Lockdown, scoring, device ban
│   ├── services/             # Business logic
│   │   ├── llm_service.py    # Ollama API + retry logic
│   │   ├── rag_service.py    # ChromaDB RAG
│   │   └── session_store.py  # SQLite conversation history
│   ├── voice_v2/             # Voice pipeline
│   │   ├── input.py          # STT via faster-whisper
│   │   ├── output.py         # TTS via edge-tts (4 fallback backends)
│   │   └── wake_word.py      # "Hey JARVIS" detection
│   ├── memory/               # Persistent + semantic memory
│   ├── middleware/           # Security headers, rate limiting, audit
│   └── tests/                # 516 passing tests
├── frontend/
│   ├── index.html            # SPA structure
│   ├── app.js                # All JavaScript (~3000 lines)
│   └── style.css             # All CSS (~670 lines)
├── .env.example              # Configuration template
├── start.bat                 # One-click startup (Windows)
├── stop_jarvis.bat           # Stop all JARVIS processes
├── check_jarvis.py           # Pre-flight diagnostics
└── docker-compose.yml        # Docker deployment
```

---

## Configuration

Copy `.env.example` to `.env` and adjust as needed. All variables are optional — the defaults work out of the box for local use.

| Variable | Default | Description |
|----------|---------|-------------|
| `JARVIS_MODEL` | `qwen2:0.5b` | Ollama model (auto-selected by start.bat) |
| `JARVIS_OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama endpoint |
| `JARVIS_VOICE_ENABLED` | `true` | Enable TTS voice output |
| `JARVIS_TTS_VOICE` | `pt-BR-AntonioNeural` | Edge-TTS voice |
| `JARVIS_LANG` | `pt-BR` | Interface language |
| `JARVIS_SECRET_KEY` | *(empty)* | Token signing key (leave empty for local use) |
| `JARVIS_API_KEY` | *(empty)* | Bearer auth (leave empty to disable) |
| `JARVIS_SAFE_MODE` | `true` | Restrict high-risk shell operations |

---

## API Endpoints

| Method | Route | Description |
|--------|-------|-------------|
| WS | `/ws/jarvis?session_id=` | Real-time chat with streaming |
| GET | `/health` | Health check + Ollama status |
| GET | `/health/deep` | Deep check (Ollama, SQLite, disk, RAM) |
| GET | `/status` | Uptime, model, voice status |
| POST | `/chat` | Synchronous chat |
| GET | `/agents/` | List available agents |
| POST | `/agents/{role}/run` | Run a specific agent |
| POST | `/voice/command` | STT → LLM → TTS pipeline |
| POST | `/investigate/{type}` | OSINT (phone/ip/email/domain) |
| POST | `/analyze/code` | Code analysis (25+ languages) |
| POST | `/architect` | System architecture design |
| POST | `/generate/code` | Code generation |
| POST | `/tasks/run` | Async background task |
| GET | `/security/guardian` | Security status + score |
| GET | `/docs` | Swagger UI |

---

## Keyboard Shortcuts (Frontend)

| Shortcut | Action |
|----------|--------|
| `Space` | Toggle voice input |
| `1–4` | Show panels (code/map/data/protocols) |
| `Esc` | Close all panels |
| `Ctrl+K` | Focus chat input |
| `Ctrl+L` | Clear response panel |
| `Ctrl+R` | Reconnect WebSocket |
| `Ctrl+/` | Show shortcuts help |
| `F2` | OSINT investigation |
| `F3` | Code analysis |
| `F4` | Architecture design |
| `F5` | Code generation |
| `F6` | Summarize text |
| `F7` | Generate tests |
| `F8` | Mermaid diagram |
| `F9` | Keyboard shortcuts modal |

---

## AI Agents

JARVIS routes messages automatically to the most appropriate agent:

| Agent | Role | Trigger keywords |
|-------|------|-----------------|
| `dev` | Write clean code | "código", "implementar", "code", "write" |
| `architect` | System design + Mermaid diagrams | "arquitetura", "design", "architecture" |
| `debugger` | Root cause analysis + fixes | "erro", "bug", "debug", "fix" |
| `reviewer` | Structured code review | "revisar", "review", "feedback" |
| `security` | OWASP / pentest analysis | "segurança", "vulnerability", "pentest" |
| `planner` | Multi-step planning | "planejar", "plan", "steps" |
| `executor` | Shell command execution | "execute", "run", "executar" |
| `system` | CPU/RAM/disk monitoring | "sistema", "system", "monitor" |

---

## Security

JARVIS includes a production-grade security layer:

- **11 attack pattern detectors**: SQLi, XSS, Path Traversal, CMD Injection, LDAP, XXE, SSRF, SSTI, NoSQL, Log4Shell, Prototype Pollution
- **Progressive auto-ban**: 5min → 1h → 24h → permanent
- **Token TTL and revocation**: HMAC-SHA256 signed tokens with expiry
- **IP allowlist** and **lockdown mode**
- **Honeypot endpoints**: 20 trap paths
- **Alert deduplication**: prevents spam
- **Full audit log** with rotation

---

## Docker

```bash
docker-compose up -d
```

Requires Ollama running on the host. Edit `docker-compose.yml` to set `JARVIS_OLLAMA_URL` to your host IP.

---

## Diagnostics

Run the pre-flight check before deploying:

```bash
python check_jarvis.py
```

This verifies Python, dependencies, Ollama, SQLite, disk space, RAM, frontend files, and config.

---

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11 + FastAPI 0.115 + Uvicorn |
| LLM | Ollama (local, offline) |
| Memory | SQLite (session history) + ChromaDB (semantic/RAG) |
| TTS | edge-tts (pt-BR-AntonioNeural) + 4 fallback backends |
| STT | faster-whisper (optional) |
| Frontend | Pure HTML/CSS/JS SPA (no framework) |
| Security | Custom HMAC-SHA256 auth + threat detection layer |

---

## License

MIT — Personal project, free to use and modify.

---

<div align="center">
Made with dedication. Powered by local AI.
</div>
