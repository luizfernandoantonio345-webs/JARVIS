# JARVIS AUDIT REPORT — BEFORE
Timestamp: 2026-05-23 13:28:47

## AMBIENTE
- Python: 3.11.9
- OS: Windows 10.0.19045
- venv: venv311

## OLLAMA LOCAL
- OK: http://localhost:11434
- Modelos: phi:latest, qwen2:0.5b, tinyllama:latest

## BACKEND
- OFFLINE — porta 8000 não respondia no momento da auditoria

## ENDPOINTS
- FAIL: /health, /, /experience/stats, /api-metrics/runtime, /research/status

## IMPORTS (todos OK)
- OK: config, ai.client, services.chat_service, services.llm_service
- OK: services.session_store, agents.master_orchestrator
- OK: memory.persistent_memory, voice_v2.output
- OK: experience.engine, observability.metrics, research_runtime.researcher

## DUPLICAÇÕES
- DUP: backend/voice/ e backend/voice_v2/ coexistem

## ARQUIVOS LEGADOS NA RAIZ (para limpeza)
### BATs (10 desnecessários): diagnose_jarvis, healthcheck, open_jarvis_hands_free,
###   start_and_verify, start_backend, start_frontend, start_jarvis_final,
###   start_jarvis_one_click, start_omega, test_jarvis
### PYs (~27 arquivos): auditoria, create_modules, fix_config, jarvis, jarvis_chat,
###   jarvis_client, jarvis_code, launch_jarvis, mapear_duplicacoes, simular_humano,
###   smoke_final, test_*, validate_jarvis_final, verify_jarvis, voice_gate, _audit_before

## VOZ
- OK: edge_tts, faster_whisper, sounddevice, soundfile, openwakeword
- MISS: pyttsx3 (não crítico)

## RESUMO PRÉ-LIMPEZA
- Ollama: ONLINE (3 modelos)
- Backend: OFFLINE
- Imports: 100% OK (0 falhas)
- Arquivos para remover: ~37 (10 BATs + 27 PYs)
- Duplicações: 1 (voice/ vs voice_v2/)
