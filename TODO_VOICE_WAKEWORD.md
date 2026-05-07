# TODO: Wake word ("Jarvis"), botão zero

## Objetivo
- Operar sem botão: o microfone fica sempre ligado.
- Quando detectar "Jarvis" (wake word), o sistema responde "Sim?" e em seguida captura e executa o próximo comando.

## Implementado
- `backend/voice_v2/voice_loop.py`
  - adicionar `stop_event: Optional[asyncio.Event]` para desligar o loop de forma limpa.

## Próximos passos (backbone de UX)
1. Integrar a UI/cliente para streaming contínuo (microfone sempre ligado).
   - Opção A (recomendado): client só envia áudio quando detectar wake.
   - Opção B: client envia texto transcrito contínuo e o servidor detecta wake.
2. Garantir que o caminho usado seja consistente:
   - para “wake->sim->comando” usar o mesmo pipeline do loop ou WS (não misturar).
3. Ajustar match do wake word (reduzir falsos positivos):
   - normalizar texto (lower/strip)
   - permitir pequenas variações (fuzzy)
4. Telemetria e debugs:
   - registrar eventos: listening, wake, recording, processing, speaking
   - registrar latência por etapa (transcrição, intent, TTS)
5. Testes rápidos:
   - cenário: falar só "Jarvis" (deve responder Sim?)
   - cenário: falar "Jarvis" seguido de comando em ~1-3s (deve executar)
   - cenário: falar durante TTS (deve ignorar/evitar realimentação)


