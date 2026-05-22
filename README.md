<div align="center">

# JARVIS — Just A Rather Very Intelligent System

**Assistente de IA pessoal, autônomo e offline-first**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Ollama](https://img.shields.io/badge/Ollama-Local%20LLM-black?style=flat-square)](https://ollama.ai)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

> **Roda 100% no seu hardware. Sem nuvem obrigatória. Sem dados enviados a terceiros.**

</div>

---

## Visão Geral

JARVIS é um assistente de IA pessoal de alto desempenho com arquitetura modular, projetado para rodar localmente com **Ollama** e LLMs open-source. Ele integra voz bidirecional (STT + TTS), memória semântica vetorial, autonomia proativa com controle de risco, monitoramento do sistema e uma interface web responsiva — tudo sem dependência de APIs externas pagas.

### Capacidades

| Capacidade | Detalhe |
|---|---|
| **Offline-first** | Modelos locais via Ollama (phi, mistral, llama3, tinyllama) |
| **Voz bidirecional** | STT via faster-whisper + TTS via edge-tts (pt-BR-AntonioNeural) |
| **Memória semântica** | ChromaDB + sentence-transformers para contexto persistente |
| **Autonomia proativa** | Decision engine + safety gate — confirmação antes de ações críticas |
| **Observability** | Prometheus metrics + stack Grafana integrada |
| **Multi-LLM routing** | Roteamento por complexidade: Ollama local → Claude / OpenAI |
| **Interface PWA** | SPA offline-capable com orb animado e chat em tempo real via WebSocket |

---

## Arquitetura

```
jarvis/
├── backend/                   # FastAPI — núcleo do sistema
│   ├── main.py                # Entry point + WebSocket hub
│   ├── config.py              # Configuração centralizada (pydantic-settings)
│   ├── core/                  # Persona, logger, risk engine, event bus
│   ├── routes/                # Endpoints HTTP & WebSocket
│   ├── services/              # LLM service, session store
│   ├── ai/                    # Cliente multi-LLM (Ollama / Claude / OpenAI)
│   ├── voice/                 # Pipeline de voz v1 (STT + TTS)
│   ├── voice_v2/              # Pipeline de voz v2 com headset detection
│   ├── memory/                # Context augmentor + semantic engine
│   ├── autonomy/              # Decision engine, activity tracker, safety gate
│   ├── intents/               # Intent parser, executor, risk evaluator
│   ├── experience/            # Engine de aprendizado por experiência
│   ├── observability/         # Prometheus metrics + system metrics
│   ├── research_runtime/      # Motor de pesquisa autônoma
│   ├── runtime/               # Watchdog de processo
│   ├── cybersecurity/         # Módulo de auditoria de segurança
│   └── agents/                # Agentes especializados
├── frontend/                  # Interface web (HTML + PWA)
│   ├── index.html             # SPA principal — orb animado + chat
│   ├── manifest.json          # PWA manifest
│   └── service-worker.js      # Offline cache
├── infra/                     # Infraestrutura
│   ├── prometheus/            # Configuração de métricas
│   ├── grafana/               # Datasources e dashboards
│   └── caddy/                 # Reverse proxy com HTTPS automático
├── scripts/                   # Scripts utilitários
├── tests/                     # Suite de testes
├── docker-compose.yml         # Stack completa em containers
└── backend/.env.example       # Template de variáveis de ambiente
```

---

## Pré-requisitos

| Dependência | Versão | Obrigatório |
|---|---|---|
| Python | 3.11+ | ✅ |
| [Ollama](https://ollama.ai) | latest | ✅ |
| Node.js | 18+ | Apenas para build do frontend |
| Docker + Compose | v2+ | Apenas para deploy em container |
| Microfone / Speakers | — | Apenas para uso com voz |

---

## Instalação Rápida

### 1 — Clone o repositório

```bash
git clone https://github.com/luizfernandoantonio345-webs/JARVIS.git
cd JARVIS
```

### 2 — Ambiente Python

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate
```

### 3 — Dependências

```bash
pip install -r backend/requirements.txt
```

### 4 — Configuração do ambiente

```bash
# Copie o template e edite com seus valores
cp backend/.env.example .env
```

Variáveis mínimas para rodar:

```env
JARVIS_MODEL=phi:latest
JARVIS_OLLAMA_URL=http://localhost:11434
JARVIS_VOICE_ENABLED=true
```

> **Segurança:** nunca commite o arquivo `.env`. Ele está no `.gitignore`.

### 5 — Baixe um modelo Ollama

```bash
ollama pull phi       # leve, rápido (recomendado para início)
ollama pull mistral   # melhor qualidade
ollama pull llama3    # mais capaz
```

### 6 — Inicie

```bash
# Windows — atalho de um clique
start_jarvis.bat

# Manual
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Acesse: **http://localhost:8000**

---

## Deploy com Docker

```bash
# Stack completa (JARVIS + Prometheus + Grafana + Caddy)
docker-compose up -d

# Verificar saúde
curl http://localhost:8000/health
```

| Serviço | URL padrão |
|---|---|
| JARVIS API + UI | http://localhost:8000 |
| Docs interativos | http://localhost:8000/docs |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3001 |

---

## API Reference

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/health` | Health check do sistema |
| `POST` | `/api/v1/chat` | Chat via HTTP |
| `WS` | `/ws` | WebSocket bidirecional |
| `POST` | `/api/v1/voice/speak` | TTS — texto → áudio |
| `POST` | `/api/v1/voice/transcribe` | STT — áudio → texto |
| `GET` | `/api/v1/memory` | Consulta memória semântica |
| `GET` | `/api/v1/autonomy/status` | Status da autonomia |
| `GET` | `/metrics` | Métricas Prometheus |

Documentação completa e interativa: **http://localhost:8000/docs**

---

## Configuração de Voz

```env
JARVIS_VOICE_ENABLED=true
JARVIS_WAKE_WORD=jarvis
JARVIS_TTS_VOICE=pt-BR-AntonioNeural
JARVIS_TTS_RATE=-12%
JARVIS_VOICE_LANGUAGE=pt-BR
JARVIS_STM_MODEL=small          # tiny | base | small | medium | large
```

Para listar dispositivos de áudio disponíveis:

```bash
python test_audio_devices.py
```

---

## Módulo de Autonomia

O JARVIS pode tomar iniciativas proativas com controle granular de risco:

```env
JARVIS_AUTONOMY_ENABLED=true
JARVIS_AUTONOMY_SAFE_MODE=true          # confirmação obrigatória para ações críticas
JARVIS_AUTONOMY_MAX_ACTIONS_PER_MINUTE=3
JARVIS_IDLE_TIMEOUT_MINUTES=5
```

O **Safety Gate** classifica cada ação nos níveis `LOW → MEDIUM → HIGH → CRITICAL` e bloqueia automaticamente operações de alto impacto sem confirmação explícita do usuário.

---

## Testes

```bash
# Instalar dependências de desenvolvimento
pip install -r backend/requirements-dev.txt

# Suite completa
pytest tests/ -v

# Testes por módulo
pytest tests/test_chat.py -v
pytest tests/test_voice.py -v
```

---

## Segurança

- **Nenhuma chave de API é commitada** — use sempre o arquivo `.env` (incluído no `.gitignore`)
- **Dados de memória são locais** — bancos `.db` e vetores ChromaDB ficam apenas na sua máquina, nunca sobem ao repositório
- **Safe Mode ativo por padrão** — ações autônomas de alto risco exigem confirmação explícita
- **Rate limiting** integrado via `slowapi` para proteger todos os endpoints
- Para reportar vulnerabilidades, abra uma **Issue** privada no repositório

---

## Variáveis de Ambiente

Todas as variáveis utilizam o prefixo `JARVIS_`. Veja o template completo em [`backend/.env.example`](backend/.env.example).

| Variável | Padrão | Descrição |
|---|---|---|
| `JARVIS_MODEL` | `tinyllama:latest` | Modelo Ollama principal |
| `JARVIS_OLLAMA_URL` | `http://localhost:11434` | URL do servidor Ollama |
| `JARVIS_VOICE_ENABLED` | `true` | Habilitar módulo de voz |
| `JARVIS_AUTONOMY_ENABLED` | `true` | Habilitar autonomia proativa |
| `JARVIS_AUTONOMY_SAFE_MODE` | `true` | Exigir confirmação em ações críticas |
| `JARVIS_ANTHROPIC_API_KEY` | *(vazio)* | Chave Claude — opcional |
| `JARVIS_OPENAI_API_KEY` | *(vazio)* | Chave OpenAI — opcional |
| `JARVIS_PORT` | `8000` | Porta do servidor backend |

---

## Contribuindo

1. Faça fork do repositório
2. Crie sua branch: `git checkout -b feature/minha-feature`
3. Commit com mensagem semântica: `git commit -m "feat: adiciona X"`
4. Push: `git push origin feature/minha-feature`
5. Abra um Pull Request descrevendo a mudança

---

## Licença

Distribuído sob a licença **MIT**. Veja [`LICENSE`](LICENSE) para detalhes.

---

<div align="center">

*"Qualquer tecnologia suficientemente avançada é indistinguível da magia." — Arthur C. Clarke*

</div>
