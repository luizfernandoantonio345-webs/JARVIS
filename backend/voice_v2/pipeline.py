"""Voice pipeline: audio bytes → STT → LLM → TTS."""
import logging

log = logging.getLogger(__name__)


async def process_audio_pipeline(
    audio_bytes: bytes,
    session_id: str = "voice",
    language: str = "pt",
) -> dict:
    """
    Pipeline completo de voz:
      1. Transcreve áudio → texto (STT)
      2. Envia texto ao orchestrator (LLM)
      3. Retorna texto da resposta + caminho do áudio TTS
    """
    from voice_v2.input import transcribe_async
    from voice_v2.output import generate_tts_file

    # 1. STT
    transcript = await transcribe_async(audio_bytes, language=language)
    if not transcript:
        return {
            "status": "error",
            "response": "Não consegui entender o áudio, Senhor.",
            "transcript": None,
            "audio_path": None,
        }

    log.info("[PIPELINE] Transcrito: %s", transcript[:80])

    # 2. LLM via orchestrator
    try:
        from agents.master_orchestrator import get_orchestrator
        response_text = await get_orchestrator().execute(transcript, session_id)
    except Exception as e:
        log.warning("[PIPELINE] Orchestrator falhou: %s. Usando fallback LLM.", e)
        try:
            from ai.client import get_ai_client
            response_text = get_ai_client().call([
                {"role": "system", "content": "Você é JARVIS. Responda em português, brevemente."},
                {"role": "user",   "content": transcript},
            ])
        except Exception as e2:
            log.error("[PIPELINE] LLM fallback falhou: %s", e2)
            response_text = "Sistema indisponível, Senhor."

    # 3. TTS
    audio_path = await generate_tts_file(response_text)

    return {
        "status": "ok",
        "transcript": transcript,
        "response": response_text,
        "audio_path": audio_path,
    }
