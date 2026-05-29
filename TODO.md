# TODO — Implementação dos 11 módulos no JARVIS

- [ ] Instalar dependências no `venv311`
- [ ] Criar `backend/actions/send_message.py`
- [ ] Criar `backend/actions/weather_report.py`
- [ ] Criar `backend/actions/youtube_video.py`
- [ ] Criar `backend/actions/reminder.py`
- [ ] Criar `backend/actions/code_helper.py`
- [ ] Criar `backend/actions/file_controller.py`
- [ ] Criar `backend/actions/web_search.py`
- [ ] Criar `backend/actions/save_memory.py`
- [ ] Criar `backend/actions/game_updater.py`
- [ ] Criar `backend/actions/flight_finder.py`
- [ ] Criar `backend/actions/agent_task.py`
- [ ] Atualizar `backend/routes/computer.py` com novos endpoints
- [ ] Integrar memória automática em `backend/routes/chat.py`
- [ ] Atualizar `backend/core/intent_classifier.py` com intents estendidas
- [ ] Reiniciar backend
- [ ] Testar endpoints solicitados

---

# TODO — Fase: Produto utilizável (start + seleção por RAM + testes)

## 1) Script único confiável (Ollama + backend)
- [ ] Criar `start_jarvis_product.bat` para:
  - [ ] ativar `venv311`
  - [ ] iniciar/verificar Ollama (`ollama serve`)
  - [ ] esperar Ollama online (`/api/tags`)
  - [ ] iniciar backend (`uvicorn backend.main:app --port 8000`)
  - [ ] smoke test `/health`
  - [ ] smoke test ws `/ws/jarvis` (mensagem → `done`/resposta)
  - [ ] smoke test ws voz `/ws/audio_stream` (se STT/TTS indisponível: degradar graciosamente)
  - [ ] abrir interface

## 2) Seleção automática de modelo por RAM (override manual sempre)
- [ ] Criar `backend/utils/model_selector.py`:
  - [ ] detectar RAM total (Windows via WMI + fallback)
  - [ ] mapear faixas RAM → modelo recomendado
  - [ ] respeitar override manual: se `JARVIS_MODEL` definido, usar ele
- [ ] Editar `backend/main.py`:
  - [ ] no `startup()`, resolver modelo por RAM antes de qualquer chamada ao LLM client
  - [ ] logar RAM detectada + modelo resolvido
- [ ] Editar `backend/config.py` se necessário (flags/params da estratégia)

## 3) Testar chat, websocket e voz sem desabilitar modo
- [ ] Rodar `scripts/smoke_test.py` e corrigir falhas
- [ ] Garantir que voz sem dependências não derrube o backend
- [ ] Ajustar testes de websocket/voz conforme endpoints reais

## 4) Corrigir o que quebrar (confiabilidade)
- [ ] Remediar/limitar scripts que matam `python.exe` globalmente (trocar por PID/porta)
- [ ] Revisar circuit breaker / timeouts do Ollama se aparecerem timeouts

## 5) Depois: cockpit/UI estilo JARVIS
- [ ] Expor status para frontend (Ollama/modelo/voz/deps/last error)
- [ ] Integrar cockpit no `frontend/`
