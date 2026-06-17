"""Resilient voice loader — detecta TTS/STT disponíveis sem travar o startup."""
import logging

log = logging.getLogger(__name__)


def load_voice_safe() -> dict:
    """
    Tenta carregar componentes de voz.
    Retorna dict com 'mode':
      'none'     — nada disponível
      'tts_only' — apenas TTS (edge-tts)
      'full'     — TTS + STT (whisper)
    """
    tts_ok = _check_tts()
    stt_ok = _check_stt()

    if tts_ok and stt_ok:
        mode = "full"
    elif tts_ok:
        mode = "tts_only"
    else:
        mode = "none"

    log.info("[VOICE] Modo: %s | TTS=%s | STT=%s", mode, tts_ok, stt_ok)
    return {
        "mode": mode,
        "tts": "edge_tts" if tts_ok else None,
        "stt": "whisper" if stt_ok else None,
    }


def _check_tts() -> bool:
    try:
        import edge_tts  # noqa: F401
        log.info("[VOICE] TTS: edge-tts disponível")
        return True
    except ImportError:
        log.warning("[VOICE] TTS: edge-tts ausente — execute: pip install edge-tts")
        return False


def _check_stt() -> bool:
    try:
        import faster_whisper  # noqa: F401
        log.info("[VOICE] STT: faster-whisper disponível")
        return True
    except ImportError:
        pass
    try:
        import whisper  # noqa: F401
        log.info("[VOICE] STT: openai-whisper disponível")
        return True
    except ImportError:
        log.info("[VOICE] STT: whisper ausente (voz via upload desabilitada)")
        return False
