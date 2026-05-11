# 🤖 JARVIS v5.2 — Sistema de IA Autônoma & Voice-Centric

**Versão:** 5.2 | **Status:** ✅ MVP Funcional | **Stack:** Python 3.11+, FastAPI, SQLite, asyncio, Pydantic v2

> **Sistema de IA autônomo com controle por voz, orquestração multiagente e autonomia operacional.**

---

## 🚀 Início Rápido

### 1. Iniciar o servidor
```bash
cd c:\Users\cibernetico\JARVIS
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

**Resultado esperado:**
```
INFO:JARVIS_CORE:Inicializando JARVIS...
INFO:JARVIS_CORE:✓ Health router carregado
INFO:JARVIS_CORE:✓ Chat router carregado
...
INFO:JARVIS_CORE:[WAKE] Wake word 'JARVIS' ativa e escutando
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 2. Verificar saúde do servidor
```bash
# PowerShell
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -Method Get

# Resultado:
# status           : ok
# service          : JARVIS API
# uptime           : 00:00:45
```

### 3. Testar chat
```bash
$json = '{"message":"responda OK","session_id":"test"}'
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/chat/process' -Method Post `
  -Body $json -ContentType 'application/json'
```

---

## 🎯 Capacidades Principais

| Capacidade | Status | Descrição |
|-----------|--------|-----------|
| 🎤 Voice Input | ✅ | STT via Faster Whisper (português/inglês) |
| 🔊 Voice Output | ✅ | TTS via Edge TTS (vozes brasileiras) |
| 💭 Intent Classification | ✅ | Classificação inteligente de domínio |
| 🤝 Multi-Agent | ✅ | Orquestrador de agentes (Architect, Dev, Reviewer, Security) |
| ⚙️ AutoDev | ✅ | Geração automática de código com validação |
| 🎯 Autonomy | ✅ | Loop autônomo com detecção de eventos |
| 🖥️ Computer Control | ✅ | Mouse, teclado, screenshots (whitelist) |
| 🌐 Browser Control | ✅ | Navegação automática (validação de URLs) |
| 📝 File Operations | ✅ | Leitura/escrita segura com restrições |
| 🔍 Web Search | ✅ | Busca integrada |
| 💾 Memory | ✅ | 3-tier memory (cache, semantic, wiki) |

---

## 📁 Estrutura de Diretórios

```
jarvis/backend/
├── main.py                     # FastAPI entrypoint + startup/shutdown lifecycle
├── config.py                   # JarvisConfig centralizado (BaseSettings)
│
├── routes/                     # HTTP + WebSocket endpoints
│   ├── health.py               # GET /health (básico)
│   ├── chat.py                 # POST /chat, /chat/stream
│   ├── agents.py               # POST /agents/run
│   ├── autodev.py              # POST /autodev/start, WS /autodev/stream/{id}
│   ├── autonomy.py             # POST /autonomy/start|pause|stop|resume, GET /autonomy/status|log
│   ├── behavior.py             # GET|PUT /behavior/profile, POST /behavior/profile/reset
│   ├── dashboard.py            # WS /dashboard/stream, GET /dashboard/
│   ├── orchestrator.py         # POST /orchestrate
│   ├── terminal.py             # POST /terminal/create, /terminal/send
│   ├── workspace.py            # POST /workspace/scaffold, GET /workspace/detect
│   ├── memory.py               # GET /memory/*, POST /memory/*
│   ├── security.py             # POST /security/scan
│   ├── tasks.py                # POST /tasks/run
│   └── execute.py              # POST /execute
│
├── core/                       # Infraestrutura central
│   ├── autonomous_loop.py      # Observe→Plan→Execute→Re-plan cycle
│   ├── boot_restorer.py        # Restaura contexto ao reiniciar
│   ├── context_injector.py     # Injeta boot context no primeiro LLM call
│   ├── session_checkpoint.py   # Salva estado a cada 5min + on shutdown
│   ├── health.py               # Health check unificado (GET /health)
│   └── circuit_breaker.py      # Proteção contra falhas em cascata
│
├── agents/                     # Multi-Agent System (Fase 9)
│   ├── multi_agent_orchestrator.py
│   ├── planner_agent.py
│   ├── executor_agent.py
│   ├── critic_agent.py
│   ├── memory_agent.py
│   └── agent_protocol.py
│
├── autodev/                    # AutoDev Engine (Fase 10)
│   ├── loop.py                 # AutoDevLoop: scaffold→generate→validate→fix
│   ├── scaffolder.py
│   ├── code_generator.py       # Geração com ProjectContext cross-file
│   ├── context_tracker.py      # Coerência entre arquivos gerados
│   ├── validator.py
│   └── auto_fixer.py           # Retry inteligente: error+original→diff→history
│
├── autonomy/                   # System Event Loop (Fase 11A)
│   ├── controller.py           # AutonomyController: start/stop/pause + rate limit
│   ├── event_detector.py       # 4 watchers: FS + Log + Schedule + Idle
│   ├── event_router.py         # Match evento → action → Orchestrator
│   ├── goal_decomposer.py      # Decompõe daily goal em workplan
│   ├── work_session.py         # Executa workplan task a task
│   ├── daily_briefing.py       # Morning briefing via voz
│   ├── confirmation_gate.py    # Confirmação contextual por risk_tolerance
│   ├── schedule.json           # Tarefas agendadas (cron-like)
│   └── rules.json              # Regras de roteamento de eventos
│
├── behavior/                   # Behavior Profile (Fase 11B)
│   ├── profile.py              # BehaviorProfile Pydantic model
│   ├── profile_manager.py      # Load/save/evolve perfil
│   ├── profile_injector.py     # Injeta preferências no system prompt
│   ├── profile.json            # Perfil atual (criado automaticamente)
│   └── reports/                # Relatórios de evolução semanal
│
├── services/                   # Serviços de suporte
│   ├── llm_service.py          # Hybrid LLM router (Ollama/Claude/GPT-4o)
│   ├── memory_service.py       # 3-tier SQLite memory
│   ├── chat_service.py
│   ├── terminal_manager.py
│   └── ...
│
├── voice/                      # Interface de voz (Fase 12A)
│   └── command_mapper.py       # Mapeamento voz → API calls
│
├── integrations/
│   └── vscode_bridge.py        # VS Code diagnostics bridge
│
├── actions/                    # Tools/Actions disponíveis
│   ├── shell_exec.py
│   ├── file_reader.py / file_writer.py / file_editor.py
│   ├── web_search.py
│   ├── git_clone.py / git_pr.py
│   └── system_monitor.py
│
├── reports/daily/              # Relatórios diários (EOD report)
├── memory.db                   # SQLite: episodic + preferences + project + checkpoints
└── .env.example                # Template de variáveis de ambiente
```

---

## Instalação

### Pré-requisitos
- Python 3.11+
- Ollama instalado localmente: https://ollama.ai
- (Opcional) Chaves de API para Claude/OpenAI

### Passo a passo

```bash
# 1. Clone o repositório
git clone <repo> && cd JAVIS/backend

# 2. Crie ambiente virtual
python -m venv .venv
.venv\Scripts\activate   # Windows
source .venv/bin/activate # Linux/Mac

# 3. Instale dependências
pip install -r requirements.txt

# 4. Configure ambiente
cp .env.example .env
# Edite .env com suas configurações

# 5. Inicie o Ollama e baixe o modelo
ollama serve
ollama pull qwen2:0.5b

# 6. Inicie o servidor
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 7. Acesse o dashboard
# http://localhost:8000/dashboard/
```

---

## Variáveis de Ambiente

| Variável | Default | Descrição |
|----------|---------|-----------|
| `JARVIS_JOBS_DIR` | `D:/JAVIS/jobs` | Diretório dos jobs AutoDev |
| `JARVIS_WATCH_DIRS` | (projeto atual) | Dirs monitorados (separados por `:`) |
| `JARVIS_OLLAMA_URL` | `http://localhost:11434` | URL do Ollama |
| `JARVIS_LOCAL_MODEL` | `qwen2:0.5b` | Modelo Ollama padrão |
| `JARVIS_ANTHROPIC_API_KEY` | `` | Chave API Claude |
| `JARVIS_OPENAI_API_KEY` | `` | Chave API OpenAI |
| `JARVIS_AUTONOMY_ENABLED` | `true` | Iniciar Event Loop no startup |
| `JARVIS_AUTONOMY_MAX_ACTIONS_PER_MINUTE` | `3` | Rate limit do loop autônomo |
| `JARVIS_AUTONOMY_SAFE_MODE` | `true` | Confirmar escritas de arquivo |
| `JARVIS_IDLE_TIMEOUT_MINUTES` | `5` | Tempo idle antes do IdleWatcher disparar |
| `JARVIS_RISK_TOLERANCE` | `medium` | `low`/`medium`/`high` |
| `JARVIS_VOICE_ENABLED` | `true` | Habilitar voz |
| `JARVIS_VOICE_LANGUAGE` | `pt-BR` | Idioma de reconhecimento |
| `JARVIS_MEMORY_MAX_SIZE_MB` | `500` | Limite do SQLite antes de cleanup |

Ver `.env.example` para lista completa.

---

## API Endpoints

### Health
| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/health` | Status completo de todos os componentes |

### Chat
| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/chat` | `{"message": "..."}` → resposta do LLM |
| POST | `/chat/stream` | Stream SSE da resposta |

### AutoDev Engine
| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/autodev/start` | `{"goal": "...", "constraints": {}}` → inicia job |
| GET | `/autodev/status/{job_id}` | Status atual do job |
| WS | `/autodev/stream/{job_id}` | Stream em tempo real de eventos do job |

### Agents (Multi-Agent)
| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/agents/run` | `{"goal": "..."}` → executa via orquestrador |
| POST | `/agents/{role}/run` | Executa agente específico (planner/executor/critic) |

### Autonomy (Event Loop)
| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/autonomy/start` | Inicia o System Event Loop |
| POST | `/autonomy/pause` | Pausa (continua monitorando, não age) |
| POST | `/autonomy/resume` | Retoma após pausa |
| POST | `/autonomy/stop` | Para completamente |
| POST | `/autonomy/confirm/{id}` | `{"approved": bool}` → responde confirmação safe mode |
| GET | `/autonomy/status` | Estado, eventos hoje, ações tomadas |
| GET | `/autonomy/log` | Últimas 50 ações autônomas |

### Behavior Profile
| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/behavior/profile` | Perfil atual |
| PUT | `/behavior/profile` | Atualização parcial |
| POST | `/behavior/profile/reset` | Volta ao default |
| GET | `/behavior/profile/history` | Histórico de mudanças |
| POST | `/behavior/profile/feedback` | `{"feedback": "..."}` → atualiza via linguagem natural |

### Dashboard
| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/dashboard/` | Dashboard HTML em tempo real |
| WS | `/dashboard/stream` | Stream de estado completo (atualiza a cada 2s) |

### Memory
| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/memory/episodic` | Entradas episódicas recentes |
| GET | `/memory/preferences` | Preferências do usuário |
| POST | `/memory/save` | Salva nova entrada |

### Session
| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/session/context` | Contexto restaurado do boot |

---

## Comandos de Voz

Ative com a wake word **"Jarvis"** seguida do comando:

| Comando | Ação |
|---------|------|
| `Jarvis, pausa a autonomia` | `POST /autonomy/pause` |
| `Jarvis, retoma a autonomia` | `POST /autonomy/resume` |
| `Jarvis, qual o status?` | Lê `/autonomy/status` em voz |
| `Jarvis, modo silencioso` | Verbosity → minimal |
| `Jarvis, modo detalhado` | Verbosity → detailed |
| `Jarvis, o que você fez hoje?` | Resume as últimas 10 ações |
| `Jarvis, cancela o job atual` | Cancela job ativo |
| `Jarvis, bom dia` | Ativa Daily Briefing |
| `Jarvis, modo trabalho` | Ativa Work Session Manager |
| `Jarvis, pausa a sessão` | Pausa Work Session |
| `Jarvis, status do dia` | Progresso do workplan |
| `Jarvis, pula essa task` | Skipa task atual |

---

## Como adicionar nova Action/Tool

1. Crie `backend/actions/minha_action.py` com uma função `async def run(params: dict) -> str`
2. Adicione metadata:
   ```python
   ACTION_META = {
       "name": "minha_action",
       "description": "O que essa action faz",
       "params": {"param1": "string"},
   }
   ```
3. O `action_loader.py` descobre automaticamente (sem registro manual)

---

## Como adicionar novo Event Watcher

1. Crie uma classe em `backend/autonomy/event_detector.py` com método `async def run(self) -> None`
2. A classe deve fazer `await self._queue.put(MeuEvento(...))` para emitir eventos
3. Instancie no `EventDetector.start()` e adicione à lista `self._tasks`
4. Adicione regra em `autonomy/rules.json` para rotear o novo tipo de evento

---

## Troubleshooting

### 1. Ollama não conecta
```bash
ollama serve   # deve estar rodando
ollama list    # confirme que o modelo está instalado
```

### 2. Import circular no boot
- Verifique se novos módulos usam `TYPE_CHECKING` para imports condicionais
- Imports que causam circular devem ser movidos para dentro da função

### 3. AutoDev job travado (stuck)
```bash
GET /autodev/status/{job_id}  # verifique o status
POST /autodev/start {"goal": "..."} # retoma automaticamente se mesmo goal
```

### 4. Memory DB crescendo demais
- O `MemoryCircuitBreaker` faz limpeza automática quando excede `JARVIS_MEMORY_MAX_SIZE_MB`
- Limpeza manual: `DELETE FROM memory WHERE timestamp < (unixepoch() - 30*86400)`

### 5. Autonomy loop agindo demais
- Ajuste `JARVIS_AUTONOMY_MAX_ACTIONS_PER_MINUTE=1` no `.env`
- Ou use `POST /autonomy/pause` para pausar temporariamente
- O `EventLoopThrottle` (circuit breaker) bloqueia automaticamente se > 10 eventos/min

---

## Arquitetura de Decisão do LLM

```
Mensagem recebida
    │
    ├─ ProfileInjector: adiciona preferências de código/verbosidade
    ├─ BootContextInjector: adiciona contexto da sessão anterior (1x por restart)
    │
    ↓
ComplexityScorer (0.0–1.0)
    │
    ├─ ≤ COMPLEX_THRESHOLD (0.45) → Ollama local
    └─ > COMPLEX_THRESHOLD        → API externa
            │
            ├─ ANTHROPIC_KEY set → Claude (melhor raciocínio)
            ├─ OPENAI_KEY set    → OpenAI GPT-4o-mini
            └─ fallback          → Ollama local

BehaviorProfile.llm_routing substitui o threshold para task_types conhecidos:
    code_gen → ollama | analysis → claude | quick → gpt-4o-mini
```
