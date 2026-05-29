# JARVIS v6.0 — Iniciar em 1 Clique

## Pré-requisitos
- Python 3.11 (venv311 já configurado)
- Ollama instalado (iniciado automaticamente)
- Windows 10+

## Iniciar

```batch
.\start_jarvis.bat
```

**O script automaticamente:**
1. Ativa venv311
2. Verifica/inicia Ollama em localhost:11434
3. Inicia backend FastAPI em porta 8000
4. Pré-aquece modelo qwen2:0.5b
5. Abre http://localhost:8000 no browser

**Tempo total:** ~15 segundos até estar pronto.

## Usar

### Web Interface
- Local: http://localhost:8000
- Remote: http://100.110.105.46:8000 (Tailscale)

### Arquitetura
- **Backend:** FastAPI, Python 3.11
- **LLM:** Ollama local (qwen2:0.5b)
- **Voice:** TTS en-GB-RyanNeural
- **Database:** SQLite em data/memory.db

### Logs
```
backend/logs/jarvis.log
```

---

**Status:** Production Ready v6.0  
**Última atualização:** 2026-05-29
