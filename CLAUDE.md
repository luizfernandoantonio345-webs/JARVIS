# JARVIS — Guia do Codebase para Claude Code

## O que é este projeto

JARVIS (Just A Rather Very Intelligent System) é um assistente de IA pessoal offline-first, rodando 100% local via Ollama + FastAPI + SPA em HTML. Criado para uso pessoal e demonstração escolar.

## Stack

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.11 + FastAPI 0.115 + Uvicorn |
| LLM | Ollama local (mistral:7b na escola, qwen2:0.5b dev) |
| Memória | SQLite (histórico/sessão) + ChromaDB (semântica/RAG) |
| Voz TTS | edge-tts (en-GB-RyanNeural) + 4 backends fallback |
| Voz STT | faster-whisper (opcional) |
| Frontend | SPA HTML/JS/CSS puro (3931 linhas), sem framework |
| Auth | Bearer token opcional (vazio = aberto localmente) |

## Como rodar

```bat
# Desenvolvimento (qwen2:0.5b)
.\start_jarvis.bat

# Escola (mistral:7b, 32GB RAM, headset mode)
.\start_jarvis_escola.bat

# Primeira vez na escola (setup completo)
.\setup_escola.bat
```

O backend sobe em `http://localhost:8000`. O frontend é servido pelo próprio FastAPI em `/`.

## Estrutura de diretórios

```
JARVIS/
├── backend/
│   ├── main.py               ← Entry point FastAPI, WebSocket, lifecycle
│   ├── config.py             ← Todas as configurações via Pydantic + .env
│   ├── routes/               ← 11 routers HTTP
│   │   ├── health.py         ← GET /health /status /ping /ready
│   │   ├── chat.py           ← POST /chat, GET /chat/stream, GET /chat/history
│   │   ├── agents.py         ← GET /agents/, POST /agents/{role}/run
│   │   ├── voice.py          ← POST /voice/command
│   │   ├── memory.py         ← GET /memory/search
│   │   ├── investigate.py    ← POST /investigate/{type} (OSINT)
│   │   ├── analyze.py        ← POST /analyze/code
│   │   ├── architect.py      ← POST /architect
│   │   ├── generate.py       ← POST /generate/* (15 sub-endpoints)
│   │   ├── tasks.py          ← POST /tasks/run, GET /tasks/{id}
│   │   └── jarvis_tts.py     ← GET /tts-iron/tts
│   ├── agents/               ← 8 agentes especializados + orchestrators
│   │   ├── base_agent.py     ← BaseAgent com run() e stream() via LLM
│   │   ├── master_orchestrator.py ← Roteamento por keywords PT+EN
│   │   ├── dev_agent.py      ← Escrita de código
│   │   ├── architect_agent.py ← Design de sistemas
│   │   ├── debugger_agent.py ← Debug e root cause
│   │   ├── reviewer_agent.py ← Code review estruturado (JSON output)
│   │   ├── security_agent.py ← OWASP / pentest
│   │   ├── planner_agent.py  ← Multi-step planning
│   │   └── executor_agent.py ← Execução de comandos
│   ├── services/
│   │   ├── agent_registry.py ← Registry central de todos os agentes
│   │   ├── session_store.py  ← Histórico de sessão com SQLite
│   │   ├── llm_service.py    ← call_llm() e call_llm_stream()
│   │   ├── rag_service.py    ← RAG via ChromaDB (get_rag_context, index_document)
│   │   └── memory_service.py ← Memória semântica 3-tier
│   ├── voice_v2/
│   │   ├── wake_word.py      ← "Hey JARVIS" detection (energy + Whisper tiny)
│   │   ├── output.py         ← TTS com 4 backends (pygame/playsound/PS/ffmpeg)
│   │   ├── input.py          ← STT via faster-whisper
│   │   └── voice_pipeline_v3.py ← Pipeline completo STT→LLM→TTS
│   ├── core/
│   │   ├── jarvis_persona.py ← MAIN_SYSTEM_PROMPT e build_agent_prompt()
│   │   ├── intent_classifier.py ← Detecção de intent com score
│   │   ├── safety_gate.py    ← Risk classification LOW/MEDIUM/HIGH/CRITICAL
│   │   └── risk_engine.py    ← Wrapper de evaluate_risk()
│   ├── autonomy/             ← Policy engine, night mode, activity tracking
│   ├── middleware/           ← SecurityHeaders, InputGuard, Audit, RateLimiter
│   ├── memory/               ← PersistentMemory SQLite
│   ├── ai/
│   │   └── client.py         ← Multi-LLM client (Ollama/Claude/OpenAI)
│   └── utils/
│       └── model_selector.py ← Auto-seleciona modelo por RAM disponível
├── frontend/
│   └── index.html            ← SPA completa (3931 linhas, inline CSS+JS)
├── .env                      ← Config ativa (gerada pelo .bat)
├── .env.escola               ← Config para PC da escola (mistral:7b)
├── .env.example              ← Template com todos os campos
├── start_jarvis.bat          ← Iniciar modo dev
├── start_jarvis_escola.bat   ← Iniciar modo escola
└── setup_escola.bat          ← Setup completo (rodar 1x na escola)
```

## Variáveis de ambiente importantes

| Variável | Padrão | Descrição |
|---|---|---|
| `JARVIS_MODEL` | `qwen2:0.5b` | Modelo Ollama a usar |
| `JARVIS_OLLAMA_URL` | `http://127.0.0.1:11434` | URL do Ollama |
| `JARVIS_VOICE_ENABLED` | `true` | Habilitar TTS |
| `JARVIS_HEADSET_MODE` | `false` | Modo mãos-livres com headset |
| `JARVIS_WAKE_WORD_ENABLED` | `true` | Ativar "Hey JARVIS" |
| `JARVIS_SECRET_KEY` | — | Chave AES-256 (gerar com secrets.token_hex(32)) |
| `JARVIS_API_KEY` | vazio | Bearer token auth (vazio = desabilitado) |
| `JARVIS_SAFE_MODE` | `false` | Restringe ações de alto risco |
| `JARVIS_SAFETY_LEVEL` | `trusted` | Portão do laço: off/trusted/strict |
| `JARVIS_TTS_PROFILE` | `jarvis` | Voz: jarvis/jarvis_en/ultron/operacional/neutro |
| `JARVIS_TTS_OUTPUT` | `browser` | Onde o áudio toca: browser/server |
| `JARVIS_AGENT_MAX_ITERATIONS` | `25` | Teto de passos do laço |
| `JARVIS_AGENT_WS_TIMEOUT` | `900` | Segundos até abortar a tarefa |
| `JARVIS_ROUTER_LLM` | `true` | Classificação de rota via LLM |
| `JARVIS_ESCALATE` | `auto` | Escalada: off/advice/auto |
| `JARVIS_ESCALATE_PROVIDER` | auto | `claude` ou `openai` |
| `JARVIS_ANTHROPIC_API_KEY` | vazio | Liga a escalada para Claude |
| `JARVIS_OPENAI_API_KEY` | vazio | Liga a escalada para OpenAI |
| `JARVIS_TOTAL_RAM_GB` | auto | Força RAM para seleção de modelo |

## Fluxo de uma mensagem de chat

O WebSocket bifurca: pedido de trabalho vai para o laço com ferramentas,
conversa segue pelo orquestrador de prompt. Quem decide é
`core.agent_bridge.precisa_de_ferramentas()` — "bom dia" não custa 25 idas ao
modelo, e um modelo pequeno com 9 schemas na frente de uma saudação se perde.

```
WebSocket /ws/jarvis
    │
    ├─ precisa_de_ferramentas(texto) == True  → LAÇO DE AGENTE
    │   → PonteAgente.executar()         (core/agent_bridge.py)
    │       → run_agent() numa thread    (core/agent_loop.py)
    │           → memória inicial        (core/tools_memory.py)
    │           → modelo escolhe ferramenta → agent_safety.avaliar()
    │               → irreversível? confirm_handler → agent_confirm no socket
    │               → senão executa e devolve o resultado ao modelo
    │           → impasse? escalation.pedir_conselho() → retoma local
    │                        2º impasse → assumir_tarefa() → encerra
    │           → repete até concluir (teto de 25 iterações)
    │       → eventos pela fila: thinking / tool_call / tool_result / done
    │   → texto final enviado como token
    │
    └─ caso contrário                         → CONVERSA
        → MasterOrchestrator.execute()
            → SmartRouter (regex ancorada → LLM → keyword)
            → agente especializado (dev/architect/debugger/...)
            → call_llm() com SYSTEM_PROMPT do agente
        → Fallback: ai.client.stream_chat() direto
        → Fallback: services.chat_service.process_message()

    → TTS: navegador (JARVIS_TTS_OUTPUT=browser, orb acompanha a fala)
           ou servidor (=server)
```

Enquanto o laço roda, o handler não está lendo o socket — e a confirmação que
o laço espera chega por ele. Por isso `_rodar_agente()` sobe um ouvinte
concorrente: sem ele, agente e servidor ficam parados um pelo outro.

### Escalada para modelo forte

`JARVIS_ESCALATE`: `off` | `advice` | `auto` (padrão), com
`JARVIS_ANTHROPIC_API_KEY` ou `JARVIS_OPENAI_API_KEY`. Sem chave fica
desligada e o laço segue só com o modelo local.

A ferramenta `ask_stronger_model` já existia, mas depender do modelo pequeno
para *decidir* usá-la não funciona: um 7B que entrou em loop não percebe que
entrou em loop — repete a mesma chamada com convicção. Quem percebe é o laço,
por três sinais observáveis de fora (`core/escalation.py`):

| Sinal | Quando dispara |
|---|---|
| `repeticao` | mesma ferramenta com os mesmos argumentos de novo |
| `erros` | três resultados de erro seguidos |
| `vazio` | dois turnos sem texto e sem ferramenta |
| `teto` | bateu o limite de iterações sem entregar nada |

Primeiro impasse pede orientação e devolve ao modelo local, que continua
trabalhando — custa uma chamada e costuma destravar. Segundo impasse entrega a
tarefa: o modelo forte responde e o laço encerra. No `teto` vai direto para a
entrega, porque ali não há laço para continuar.

### Portão de segurança

`JARVIS_SAFETY_LEVEL`: `off` | `trusted` (padrão) | `strict`.

Em `trusted` o agente trabalha sem interrupção e só pede confirmação no que não
tem desfazer — remoção recursiva, `git push --force`, `DROP DATABASE`, `mkfs`,
`curl | sh`, `sudo` e companhia (lista completa em `core/agent_safety.py`).
Sem ninguém para confirmar, a ação é recusada com texto que o modelo lê e
relata, em vez de falhar em silêncio.

## Agentes registrados

| Role | Classe | Função |
|---|---|---|
| `dev` | DevAgent | Escreve código limpo em qualquer linguagem |
| `architect` | ArchitectAgent | Design de sistemas + diagramas Mermaid |
| `debugger` | DebuggerAgent | Root cause analysis + fixes mínimos |
| `reviewer` | ReviewerAgent | Code review com veredicto JSON |
| `security` | SecurityAgent | OWASP Top 10 + pentest |
| `planner` | PlannerAgent | Quebra goal em multi-step plan |
| `executor` | ExecutorAgent | Executa comandos shell com whitelist |
| `system` | SystemAgent | CPU/RAM/disk/processo monitoring |

Todos herdam de `BaseAgent` que já implementa `run()` e `stream()`.

## Convenções de código

- Imports: sempre `from __future__ import annotations` no topo
- Logging: `log = logging.getLogger("jarvis.<módulo>")`
- Config: sempre via `from config import get_config; _cfg = get_config()`
- Async: prefer `asyncio.to_thread()` para operações blocking
- Fallbacks: todo módulo opiconal usa try/except no import e degrada graciosamente
- Língua: código em inglês, comentários e logs podem ser PT-BR

## Endpoints principais

| Método | Rota | Descrição |
|---|---|---|
| WS | `/ws/jarvis?session_id=` | Chat em tempo real com streaming |
| GET | `/health` | Health check + status Ollama |
| GET | `/status` | Uptime, model, voice |
| POST | `/chat` | Chat síncrono |
| GET | `/chat/stream` | SSE streaming |
| GET | `/agents/` | Lista agentes |
| POST | `/agents/{role}/run` | Invocar agente específico |
| POST | `/voice/command` | Pipeline STT→LLM→TTS |
| POST | `/investigate/{type}` | OSINT (phone/ip/email/domain) |
| POST | `/analyze/code` | Análise de código (25+ linguagens) |
| POST | `/architect` | Design de arquitetura |
| POST | `/generate/*` | Geração de código/docs/testes |
| POST | `/tasks/run` | Task assíncrona em background |
| GET | `/docs` | Swagger UI automático |

## Checklist para uso na escola

Antes de levar o JARVIS para a escola:

- [ ] Rodar `setup_escola.bat` no PC da escola (1x)
- [ ] Confirmar que Ollama está instalado (`ollama --version`)
- [ ] Confirmar que mistral:7b está baixado (`ollama list`)
- [ ] Confirmar que venv311 existe com requirements
- [ ] Usar `start_jarvis_escola.bat` para iniciar
- [ ] Acessar `http://localhost:8000` no browser
- [ ] Testar `http://localhost:8000/health` — deve retornar `{"status": "ok"}`
