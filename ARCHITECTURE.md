# 🏗️ ARCHITECTURE — JARVIS v5.2

**Visão Geral do Sistema**

---

## 📐 DIAGRAMA DE ARQUITETURA

```
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND LAYER                        │
│                    (Browser/Dashboard)                       │
│                  backend/static/index.html                   │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP + WebSocket
                         │ ws://host:8000/ws/jarvis
                         ↓
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI SERVER                          │
│                    backend/main.py:8000                      │
├─────────────────────────────────────────────────────────────┤
│  Routes (backend/routes/)                                    │
│  ├─ health.py          → GET /health                         │
│  ├─ chat.py            → POST /chat/process                  │
│  ├─ agents.py          → POST /agents/run                    │
│  ├─ autonomy.py        → POST /autonomy/*                    │
│  ├─ autodev.py         → POST /autodev/*                     │
│  ├─ computer.py        → POST /computer/*                    │
│  ├─ static.py          → GET / (Frontend)                    │
│  └─ ... (10+ routes)                                         │
└──────────────┬──────────────┬──────────────┬─────────────────┘
               │              │              │
      ┌────────▼──────┐ ┌─────▼──────┐ ┌────▼─────────┐
      │    CORE       │ │  SERVICES  │ │   ACTIONS    │
      │   LAYER       │ │            │ │              │
      ├───────────────┤ ├────────────┤ ├──────────────┤
      │Orchestrator   │ │ChatService │ │ShellExec     │
      │IntentClassif  │ │LLMService  │ │FileOps       │
      │WebSocketMgr   │ │MemoryMgr   │ │ComputerCtrl  │
      │HealthCheck   │ │SessionMgr   │ │BrowserCtrl   │
      │AutonLoop     │ │             │ │WebSearch     │
      └────────┬──────┘ └─────┬──────┘ └────┬─────────┘
               │              │              │
        ┌──────▼──────────────▼──────────────▼──────────┐
        │              EXTERNAL SERVICES                │
        ├──────────────────────────────────────────────┤
        │ • Ollama (Local LLM) @ http://ollama:11434   │
        │ • Claude API (optional)                      │
        │ • OpenAI API (optional)                      │
        │ • PostgreSQL (optional)                      │
        │ • Redis (optional)                           │
        └──────────────────────────────────────────────┘
```

---

## 📦 ESTRUTURA DE DIRETÓRIOS

```
JARVIS/
├── backend/                          # Python backend
│   ├── main.py                      # FastAPI app + startup/shutdown
│   ├── config.py                    # Configuration (BaseSettings)
│   ├── requirements.txt              # Dependencies
│   │
│   ├── routes/                       # HTTP endpoints
│   │   ├── health.py                # /health
│   │   ├── chat.py                  # /chat/*
│   │   ├── agents.py                # /agents/*
│   │   ├── autonomy.py              # /autonomy/*
│   │   ├── autodev.py               # /autodev/*
│   │   ├── static.py                # GET / (frontend)
│   │   └── ... (10+ routes)
│   │
│   ├── core/                         # Core infrastructure
│   │   ├── orchestrator.py          # Intent routing
│   │   ├── websocket_manager.py     # WS with heartbeat
│   │   ├── encryption.py            # Secret encryption
│   │   ├── health.py                # Health checks
│   │   └── circuit_breaker.py       # Fault protection
│   │
│   ├── middleware/                   # FastAPI middleware
│   │   ├── rate_limiter.py          # Rate limiting
│   │   └── security_headers.py      # Security headers
│   │
│   ├── services/                     # Business logic
│   │   ├── llm_service.py           # LLM routing
│   │   ├── chat_service.py          # Chat processing
│   │   ├── memory_service.py        # Memory storage
│   │   └── ...
│   │
│   ├── actions/                      # Tools/Actions (50+ files)
│   │   ├── shell_exec.py            # Command execution
│   │   ├── file_*.py                # File operations
│   │   ├── web_*.py                 # Web integration
│   │   └── ...
│   │
│   ├── agents/                       # Multi-agent system
│   │   ├── base_agent.py            # Base class
│   │   ├── planner_agent.py         # Task planning
│   │   ├── executor_agent.py        # Execution
│   │   └── ...
│   │
│   ├── autonomy/                     # Autonomous system
│   │   ├── controller.py            # Start/stop/pause
│   │   ├── event_detector.py        # Event watching
│   │   ├── event_router.py          # Event handling
│   │   └── ...
│   │
│   ├── voice/                        # Voice system
│   │   ├── input.py                 # STT (Whisper)
│   │   ├── output.py                # TTS (Edge-TTS)
│   │   ├── wake_word_engine.py      # Wake word detection
│   │   └── ...
│   │
│   ├── memory/                       # Memory system
│   │   ├── vector_store.py          # Embeddings (ChromaDB)
│   │   ├── memory_manager.py        # Query/store
│   │   └── schemas.py               # Data models
│   │
│   ├── behavior/                     # Behavior profiling
│   │   ├── profile.py               # User profile
│   │   ├── profile_manager.py       # Load/save
│   │   └── ...
│   │
│   ├── static/                       # Frontend files
│   │   └── index.html               # Dashboard
│   │
│   ├── logs/                         # Log files
│   │   └── jarvis.log               # Main log
│   │
│   └── memory.db                     # SQLite database

├── tests/                            # Test suite
│   ├── test_critical_path.py        # E2E tests
│   ├── test_actions_*.py            # Action tests
│   ├── test_chat_workflow.py        # Chat tests
│   ├── test_security.py             # Security tests
│   └── conftest.py                  # Fixtures
│
├── .github/workflows/                # CI/CD
│   ├── test.yml                     # Tests + coverage
│   ├── quality.yml                  # Linting
│   ├── security.yml                 # Security scan
│   └── build.yml                    # Build check
│
├── frontend/                         # Legacy (use backend/static/)
│   └── ... (various HTML/CSS)
│
├── Dockerfile                        # Multi-stage build
├── docker-compose.yml                # Dev stack
├── .dockerignore                     # Build optimization
│
├── README.md                         # Overview
├── DEPLOYMENT.md                     # This guide
├── ARCHITECTURE.md                   # This document
├── SECURITY_AUDIT_REPORT.md         # Security analysis
│
├── .env.example                      # Template
└── requirements.txt                  # Python deps
```

---

## 🔄 REQUEST FLOW

### 1. HTTP Chat Request

```
User types message in dashboard
    ↓
POST http://localhost:8000/chat/process
{
    "message": "What is Python?",
    "session_id": "user_123"
}
    ↓
routes/chat.py → process_message()
    ↓
services/chat_service.py
    ├─ Intent classification (NLP)
    ├─ Memory retrieval (semantic search)
    ├─ Action planning (if needed)
    └─ LLM call
    ↓
LLM Service (Hybrid Router)
    ├─ Ollama (local, fast, free)
    ├─ Claude (if ANTHROPIC_KEY)
    └─ GPT-4o-mini (if OPENAI_KEY)
    ↓
Response to client
{
    "response": "Python is a high-level programming language...",
    "source": "ollama",
    "timestamp": "2026-05-13T10:30:00"
}
```

### 2. WebSocket Real-time

```
Client connects
    ↓
GET ws://localhost:8000/ws/jarvis
    ↓
core/websocket_manager.py → ConnectionManager
    ├─ Accept connection
    ├─ Add to active_connections
    └─ Start heartbeat (30s interval)
    ↓
Client sends message
    ↓
Server processes
    ├─ Parse message
    ├─ Route via orchestrator
    └─ Execute action (if needed)
    ↓
Send response via WebSocket
{
    "type": "text",
    "content": "Response here",
    "timestamp": "2026-05-13T10:30:01"
}
    ↓
Heartbeat every 30s
{
    "type": "heartbeat",
    "content": "ping"
}
    ↓
Client auto-reconnect if timeout
```

### 3. Autonomous Operation

```
AutonomyController starts
    ↓
EventDetector watches (4 watchers)
    ├─ FileSystemWatcher
    ├─ LogWatcher
    ├─ ScheduleWatcher
    └─ IdleWatcher (5+ min)
    ↓
Event detected
    ↓
EventRouter matches rule
    ↓
ConfirmationGate (if risky)
    ├─ low risk → auto-approve
    ├─ medium → log + proceed
    └─ high → wait for user
    ↓
WorkSession executes task
    ├─ Plan decomposition
    ├─ Action execution
    └─ Error recovery
    ↓
Update memory + logs
```

---

## 🔌 COMPONENT INTERACTIONS

### Orchestrator (Core Router)

```python
# Main decision engine
class Orchestrator:
    async def process(message: str, session_id: str):
        # 1. Intent classification
        intent = classify_intent(message)
        
        # 2. Route to appropriate handler
        if intent.domain == "code":
            return await agents.executor.run(intent)
        elif intent.domain == "search":
            return await actions.web_search(intent)
        elif intent.domain == "chat":
            return await services.llm.generate(message)
        
        # 3. Store in memory
        memory.store(SessionEntry(
            session_id=session_id,
            input=message,
            output=response,
            timestamp=now()
        ))
        
        return response
```

### Memory System (3-tier)

```
Tier 1: Cache
├─ Type: In-memory dict
├─ TTL: 1 hour
├─ Speed: < 1ms
└─ Purpose: Hot data

Tier 2: Semantic
├─ Type: ChromaDB (vector store)
├─ Capacity: ~100K embeddings
├─ Speed: 50-500ms
└─ Purpose: Similarity search

Tier 3: Persistent
├─ Type: SQLite DB
├─ Capacity: Unlimited
├─ Speed: 10-100ms
└─ Purpose: Long-term storage
```

### LLM Service (Hybrid Router)

```python
class LLMService:
    def route(message: str, complexity: float) -> str:
        # Complexity score: 0.0-1.0
        
        if complexity < 0.4:
            return ollama.generate(message)  # Fast, cheap
        elif has_anthropic_key:
            return claude.generate(message)  # Best reasoning
        elif has_openai_key:
            return gpt4.generate(message)    # Good quality
        else:
            return ollama.generate(message)  # Fallback
```

---

## 🔐 SECURITY ARCHITECTURE

```
┌─────────────────────────────────────┐
│   Client Request                     │
└────────────┬────────────────────────┘
             │
             ↓
┌──────────────────────────────────────┐
│   Security Headers Middleware         │
│   • CSP, HSTS, X-Frame-Options      │
└────────────┬─────────────────────────┘
             │
             ↓
┌──────────────────────────────────────┐
│   Rate Limiting                       │
│   • Per-session tracking             │
│   • Per-endpoint limits              │
└────────────┬─────────────────────────┘
             │
             ↓
┌──────────────────────────────────────┐
│   Input Validation                    │
│   • Type checking                    │
│   • Whitelist/Blacklist              │
│   • Length limits                    │
└────────────┬─────────────────────────┘
             │
             ↓
┌──────────────────────────────────────┐
│   Route Handler                       │
│   • Execute action                   │
│   • Store logs                       │
└────────────┬─────────────────────────┘
             │
             ↓
┌──────────────────────────────────────┐
│   Encryption (at rest)                │
│   • API keys encrypted               │
│   • Secrets hashed                   │
└────────────┬─────────────────────────┘
             │
             ↓
┌──────────────────────────────────────┐
│   Response                            │
│   • Minimal info leakage             │
│   • Audit logged                     │
└──────────────────────────────────────┘
```

---

## 📊 DATA MODELS

### Message (Core)
```python
class Message(BaseModel):
    id: str                    # UUID
    session_id: str            # User session
    role: str                  # "user" | "assistant" | "system"
    content: str               # Message text
    timestamp: datetime        # When sent
    metadata: dict             # Extra data
```

### Intent (Classification)
```python
class Intent(BaseModel):
    domain: str                # "code" | "chat" | "search" | ...
    action: str                # Specific action
    confidence: float          # 0.0-1.0
    entities: dict             # Named entities
```

### MemoryEntry (Storage)
```python
class MemoryEntry(BaseModel):
    type: str                  # "episodic" | "semantic" | "wiki"
    content: str               # Entry text
    embedding: List[float]     # Vector (ChromaDB)
    timestamp: datetime        # When created
    session_id: str            # Associated session
    metadata: dict             # Tags, importance, etc
```

---

## ⚡ PERFORMANCE CHARACTERISTICS

| Operation | Latency | Notes |
|-----------|---------|-------|
| Health check | <10ms | No I/O |
| Chat (cached intent) | 100-300ms | Memory + LLM |
| Chat (new intent) | 500-2000ms | Classification + LLM |
| File operation | 50-500ms | FS I/O dependent |
| Memory retrieval | 50-200ms | DB query |
| AutoDev (simple) | 5-10s | Code generation |
| AutoDev (complex) | 30-120s | Testing + fixing |

---

## 🔄 DEPLOYMENT TOPOLOGY

### Single Machine
```
Internet
    ↓
Port 8000
    ↓
FastAPI (1 worker)
    ↓
Ollama (local)
SQLite (local)
```

### Scaled (Recommended)
```
Internet
    ↓
Nginx (Reverse Proxy + LB)
    ├─ FastAPI (4 workers)
    ├─ FastAPI (4 workers)
    └─ FastAPI (4 workers)
         ↓
    PostgreSQL (HA)
    Redis Cache
    Ollama Cluster
```

---

**Status:** ✅ PRODUCTION READY  
**Last Updated:** 2026-05-13
