import logging
import os
import tempfile
from typing import Any, Dict

from .pipeline import run_jarvis_pipeline

log = logging.getLogger(__name__)


async def process_voice_command(
    audio_file_path: str,
    session_id: str = "voice_v2",
    *,
    speak_response: bool = True,
) -> Dict[str, Any]:
    """Full voice pipeline: transcribe -> intent/chat -> response engine -> optional TTS."""
    try:
        result = await run_jarvis_pipeline(
            input_audio_path=audio_file_path,
            session_id=session_id,
            source="voice",
            synthesize_voice=speak_response,
        )
        status = "ok" if result.success else (result.error or "error")
        payload = result.model_dump()
        payload["status"] = status
        payload["response"] = result.response_short or result.response
        payload["audio_path"] = result.audio_path
        log.info(
            "Voice pipeline complete: session=%s status=%s trans=%d resp=%d",
            session_id,
            status,
            len(result.transcription or ""),
            len(payload["response"] or ""),
        )
        return payload
    finally:
        if audio_file_path.startswith(tempfile.gettempdir()):
            try:
                os.unlink(audio_file_path)
            except OSError:
                pass
