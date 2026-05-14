import logging
import asyncio
import importlib
from pathlib import Path
from typing import Optional

import io

log = logging.getLogger(__name__)


def normalize_audio(data):
    np = importlib.import_module("numpy")
    max_val = np.max(np.abs(data))
    if max_val < 500:  # áudio praticamente mudo
        return data
    return (data / max_val * 0.8 * 32767).astype(np.int16)

class WhisperTranscriber:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            try:
                faster_whisper = importlib.import_module("faster_whisper")
                cls._instance.model = faster_whisper.WhisperModel(
                    "small",
                    device="cpu",
                    compute_type="int8"
                )
            except Exception as exc:
                log.warning("faster_whisper unavailable; voice transcription disabled: %s", exc)
                cls._instance.model = None
            cls._instance.language = "pt"  # PT-BR
        return cls._instance
    
    async def transcribe_audio(self, file_path: str) -> str:
        """Transcribe audio file to text. Non-blocking via asyncio.to_thread."""
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(
            None,
            self._sync_transcribe,
            file_path
        )
        return text or ""

    def _sync_transcribe(self, file_path: str) -> str:
        path = Path(file_path)
        if not path.exists():
            log.warning("Audio file not found: %s", file_path)
            return ""
        if self.model is None:
            log.warning("Voice transcription requested but faster_whisper is unavailable")
            return ""
        try:
            audio_segment = importlib.import_module("pydub").AudioSegment
            np = importlib.import_module("numpy")
        except Exception as exc:
            log.warning("voice audio dependencies unavailable; transcription disabled: %s", exc)
            return ""
        
        # Load and preprocess audio to 16kHz mono
        audio = audio_segment.from_file(file_path)
        audio = audio.set_frame_rate(16000).set_channels(1)
        raw_audio = np.array(audio.get_array_of_samples(), dtype=np.int16)
        raw_audio = normalize_audio(raw_audio)
        whisper_audio = raw_audio.astype(np.float32) / 32768.0

        segments, info = self.model.transcribe(
            whisper_audio,
            language=self.language,
            beam_size=5,
            vad_filter=False,
        )
        
        text = "".join(segment.text.strip() for segment in segments).strip()
        log.info("Transcribed: %s", text[:100] + "..." if len(text) > 100 else text)
        return text
