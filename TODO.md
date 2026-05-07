# TODO

- [x] Ler repo e identificar pontos de integração de voz
- [x] Criar response_engine (backend/core/response_engine.py)
- [x] Interceptar respostas no pipeline de voz (backend/voice_v2/controller.py) antes do TTS
- [x] Adicionar voice_loop com guard de TTS e wake word (backend/voice_v2/voice_loop.py)
- [ ] Integrar voice_loop com captura real de microfone / streaming (wake word contínuo funcional)
- [ ] Adicionar guarda de “para” para encerrar loop (quando a captura real estiver ligada)
- [x] Validar cenários reais no fluxo daily-use via frontend (SpeechRecognition → WS /ws/jarvis)
- [x] Wake word contínuo funcional via WS (wake: "jarvis" → "Sim?")
- [x] Comando "parar" finaliza a sessão always-on (fecha WS e desliga sempre-on no cliente)


