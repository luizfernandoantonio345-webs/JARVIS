"""Voice pipeline: audio bytes → STT → LLM → TTS."""
import logging
import os
import uuid
from pathlib import Path

log = logging.getLogger(__name__)

# Diretório para servir os arquivos TTS ao frontend
_TTS_DIR = Path(__file__).parent.parent / "data" / "tts"
_TTS_DIR.mkdir(parents=True, exist_ok=True)

# Limite de arquivos TTS armazenados (cleanup automático)
_TTS_MAX_FILES = 50


def _cleanup_tts_dir() -> None:
    """Remove arquivos TTS antigos se passar do limite."""
    try:
        files = sorted(_TTS_DIR.glob("*.mp3"), key=lambda f: f.stat().st_mtime)
        for f in files[:-_TTS_MAX_FILES]:
            f.unlink(missing_ok=True)
    except Exception:
        pass


async def process_audio_pipeline(
    audio_bytes: bytes,
    session_id: str = "voice",
    language: str = "pt",
) -> dict:
    """
    Pipeline completo de voz:
      1. Transcreve áudio → texto (STT)
      2. Envia texto ao orchestrator (LLM)
      3. Gera TTS e retorna URL servível ao frontend/mobile
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
            "audio_url": None,
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

    # 3. TTS — salva em diretório servível e retorna URL relativa
    filename = f"tts_{uuid.uuid4().hex[:12]}.mp3"
    tts_file_path = str(_TTS_DIR / filename)
    local_path = await generate_tts_file(response_text, output_path=tts_file_path)

    audio_url = None
    if local_path and os.path.exists(local_path):
        audio_url = f"/voice/audio/{filename}"
        _cleanup_tts_dir()

    return {
        "status": "ok",
        "transcript": transcript,
        "response": response_text,
        "audio_url": audio_url,
        # Mantido por compatibilidade — mesmo valor que audio_url
        "audio_path": audio_url,
    }
