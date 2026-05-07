# TODO_VOICE_IMPLEMENTATION

- [ ] Refatorar backend/main.py para iniciar Voice Loop em background com retry e desligamento controlado; manter rotas websocket e /process.
- [ ] Implementar VoiceState global (listening/speaking + lock) e anti-eco (pausar captura enquanto speaking=True) em backend/voice_v2/voice_loop.py.
- [x] Transformar voice_loop_realtime em voice_loop_background (sempre rodando) com retry automático (exponential backoff) e nunca travando o servidor.

- [ ] Garantir que toda entrada de voz/texto passe por run_jarvis_pipeline() como núcleo.
- [ ] Ajustar wake word: normalização (lower/strip) + tolerância mínima para variações.
- [ ] Otimizar Whisper: garantir modelo tiny e pipeline de transcrição em 16kHz mono; reduzir latência com timeouts.
- [ ] Ajustar pipeline/controles de TTS para garantir que speaking=True bloqueia captura (sem conflito async).
- [ ] Criar testes de smoke rodando main.py e exercitando sequência wake→Sim?→comando (via WS) usando /ws/jarvis.

