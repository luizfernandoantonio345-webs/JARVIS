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

# Whisper model size: "tiny" ≈ 0.3s/cmd | "base" ≈ 0.6s | "small" ≈ 1.5s (todos CPU int8)
# Para PT-BR "tiny" é suficiente — comandos curtos têm acurácia comparável a "small".
import os as _os
_WHISPER_MODEL = _os.getenv("JARVIS_WHISPER_MODEL", "tiny")


class WhisperTranscriber:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            try:
                faster_whisper = importlib.import_module("faster_whisper")
                # "tiny" + int8 + num_workers=2 → ~0.3s por comando em CPU
                cls._instance.model = faster_whisper.WhisperModel(
                    _WHISPER_MODEL,
                    device="cpu",
                    compute_type="int8",
                    num_workers=2,          # paraleliza I/O de decodificação
                    cpu_threads=4,          # threads de inferência
                )
                log.info("[STT] WhisperModel '%s' carregado (int8, cpu)", _WHISPER_MODEL)
            except Exception as exc:
                log.warning("faster_whisper unavailable; voice transcription disabled: %s", exc)
                cls._instance.model = None
            cls._instance.language = "pt"  # PT-BR
        return cls._instance

    def prewarm(self) -> None:
        """Pre-aquece o modelo com áudio silencioso para eliminar latência no 1º comando."""
        if self.model is None:
            return
        try:
            np = importlib.import_module("numpy")
            silent = np.zeros(16000, dtype=np.float32)  # 1s de silêncio
            list(self.model.transcribe(silent, language=self.language, beam_size=1)[0])
            log.info("[STT] Whisper pre-aquecido — pronto para uso")
        except Exception as exc:
            log.debug("[STT] Pre-warm falhou (não crítico): %s", exc)


    async def transcribe_audio(self, file_path: str) -> str:
        """Transcribe audio file to text. Non-blocking via asyncio.to_thread. Fallback robusto."""
        loop = asyncio.get_event_loop()
        try:
            text = await loop.run_in_executor(
                None,
                self._sync_transcribe,
                file_path
            )
            if not text:
                log.warning("[STT] Transcrição vazia para arquivo: %s", file_path)
                return "[STT offline] Falha ao transcrever áudio."
            return text
        except Exception as e:
            log.error("[STT] Falha total na transcrição: %s", e)
            return "[STT offline] Erro crítico na transcrição."

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
            # beam_size=1 (greedy) → 2-3x mais rápido vs beam_size=5, acurácia quase igual em PT-BR
            beam_size=1,
            # VAD integrado: pula segmentos silenciosos antes de decodificar
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300, "speech_pad_ms": 100},
            # Não condiciona no texto anterior → mais rápido para comandos isolados
            condition_on_previous_text=False,
            # Threshold alto → ignora ruído de fundo como fala
            no_speech_threshold=0.7,
        )
        
        text = "".join(segment.text.strip() for segment in segments).strip()
        log.info("Transcribed: %s", text[:100] + "..." if len(text) > 100 else text)
        return text
