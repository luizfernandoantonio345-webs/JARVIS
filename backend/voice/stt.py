"""
Speech-to-Text Module — Converts audio to text using faster-whisper.

Uses faster-whisper for fast, offline transcription on CPU.
- Supports multiple model sizes
- Automatic language detection or configured language
- Returns confidence scores
- Graceful fallback if model unavailable

faster-whisper is a faster, more efficient version of Whisper.
"""

from __future__ import annotations

import asyncio
import logging
import numpy as np
import time
from typing import Optional, Tuple

from .persona import VoiceConfig

log = logging.getLogger(__name__)

try:
    from faster_whisper import WhisperModel
    HAS_FASTER_WHISPER = True
except ImportError:
    HAS_FASTER_WHISPER = False
    log.warning("faster-whisper not installed, STT disabled")


class SpeechToTextError(Exception):
    """Raised on STT errors."""
    pass


class SpeechToText:
    """
    Converts audio to text using faster-whisper.
    
    Model loading is lazy (on first use) to avoid startup delays.
    """

    def __init__(
        self,
        model_size: str = VoiceConfig.STT_MODEL_SIZE,
        language: str = VoiceConfig.STT_LANGUAGE,
        device: str = VoiceConfig.STT_DEVICE,
        compute_type: str = "int8",  # Quantized for speed
    ) -> None:
        """
        Initialize STT engine.
        
        Args:
            model_size: "tiny", "small", "medium", "large"
            language: "pt" (Portuguese), "en" (English), etc.
            device: "cpu" or "cuda"
            compute_type: "default", "int8", "int16", "float16", "float32"
        """
        self.model_size = model_size
        self.language = language
        self.device = device
        self.compute_type = compute_type
        
        self._model: Optional[WhisperModel] = None
        self._initialized = False
        
        log.info(
            f"SpeechToText initialized: model={model_size}, "
            f"lang={language}, device={device}"
        )

    def _init_model(self) -> bool:
        """Load faster-whisper model (lazy loading)."""
        if self._initialized:
            return self._model is not None
        
        if not HAS_FASTER_WHISPER:
            log.error("faster-whisper not installed")
            self._initialized = True
            return False
        
        try:
            log.info(f"Loading faster-whisper model: {self.model_size}")
            start = time.time()
            
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
                language=self.language,
                download_root=None,  # Use default cache
            )
            
            elapsed = time.time() - start
            log.info(f"faster-whisper model loaded in {elapsed:.2f}s")
            self._initialized = True
            return True
        
        except Exception as exc:
            log.error(f"Failed to load faster-whisper: {exc}")
            self._initialized = True
            return False

    def transcribe(
        self,
        audio: np.ndarray,
        language: Optional[str] = None,
    ) -> Tuple[str, float]:
        """
        Transcribe audio to text.
        
        Args:
            audio: Audio array (numpy, float32, mono or stereo)
            language: Language code ("pt", "en", etc.). Uses default if None.
        
        Returns:
            Tuple of (text, confidence) where confidence is average token probability
        
        Raises:
            SpeechToTextError: If transcription fails
        """
        if not self._init_model():
            raise SpeechToTextError("faster-whisper model not available")
        
        if self._model is None:
            raise SpeechToTextError("faster-whisper model failed to initialize")
        
        try:
            # Ensure float32 mono
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            audio = audio.astype(np.float32)
            
            # Skip very short audio
            if len(audio) < 16000 * 0.3:  # Less than 0.3 seconds
                log.debug(f"Audio too short: {len(audio)} samples")
                return "", 0.0
            
            # Normalize audio to [-1, 1]
            max_val = np.max(np.abs(audio))
            if max_val > 0:
                audio = audio / max_val
            
            log.info(f"Transcribing {len(audio)} samples ({len(audio)/16000:.2f}s)")
            start = time.time()
            
            # Use specified language or configured default
            lang = language or self.language
            
            # Transcribe
            segments, info = self._model.transcribe(
                audio,
                language=lang if lang != "auto" else None,
                beam_size=5,
                best_of=5,
            )
            
            # Collect results
            texts = []
            confidences = []
            
            for segment in segments:
                texts.append(segment.text)
                confidences.append(segment.confidence)
            
            full_text = " ".join(texts).strip()
            avg_confidence = np.mean(confidences) if confidences else 0.0
            
            elapsed = time.time() - start
            log.info(
                f"Transcription complete in {elapsed:.2f}s: "
                f"'{full_text}' (confidence: {avg_confidence:.2%})"
            )
            
            # Clean up result
            if not full_text or full_text.isspace():
                log.debug("Empty transcription result")
                return "", 0.0
            
            return full_text, float(avg_confidence)
        
        except Exception as exc:
            log.error(f"Transcription error: {exc}")
            raise SpeechToTextError(f"Transcription failed: {exc}")

    async def transcribe_async(
        self,
        audio: np.ndarray,
        language: Optional[str] = None,
    ) -> Tuple[str, float]:
        """
        Async wrapper for transcribe (runs in thread pool).
        
        Args:
            audio: Audio array
            language: Language code
        
        Returns:
            Tuple of (text, confidence)
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.transcribe(audio, language)
        )

    def transcribe_file(
        self,
        file_path: str,
        language: Optional[str] = None,
    ) -> Tuple[str, float]:
        """
        Transcribe audio file.
        
        Args:
            file_path: Path to audio file (.wav, .mp3, etc.)
            language: Language code
        
        Returns:
            Tuple of (text, confidence)
        """
        try:
            import soundfile as sf
            audio, sr = sf.read(file_path)
            
            # Resample if needed
            if sr != 16000:
                import resampy
                audio = resampy.resample(audio, sr_orig=sr, sr_target=16000)
            
            return self.transcribe(audio, language)
        except Exception as exc:
            raise SpeechToTextError(f"Cannot read audio file: {exc}")

    def get_info(self) -> dict:
        """Get model info and configuration."""
        return {
            "model_size": self.model_size,
            "language": self.language,
            "device": self.device,
            "compute_type": self.compute_type,
            "initialized": self._initialized,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Test entry point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    print("\n=== JARVIS Speech-to-Text Test ===\n")
    
    if not HAS_FASTER_WHISPER:
        print("faster-whisper not installed. Install with:")
        print("  pip install faster-whisper")
        sys.exit(1)
    
    # Test 1: Create synthetic speech-like audio
    print("Test 1: Create synthetic audio")
    sample_rate = 16000
    duration = 2.0
    frequency = 440  # A4 note
    
    t = np.arange(int(sample_rate * duration)) / sample_rate
    # Modulate with envelope
    envelope = np.sin(np.pi * t / duration)
    audio = 0.3 * np.sin(2 * np.pi * frequency * t) * envelope
    audio = audio.astype(np.float32)
    
    print(f"  Created {len(audio)} samples ({duration}s)")
    print()
    
    # Test 2: Initialize and transcribe
    print("Test 2: Initialize and transcribe")
    try:
        stt = SpeechToText(
            model_size="tiny",  # Smallest for quick test
            language="pt",
        )
        print(f"  STT config: {stt.get_info()}")
        print()
        
        print("  Transcribing audio...")
        text, confidence = stt.transcribe(audio)
        print(f"  Result: '{text}'")
        print(f"  Confidence: {confidence:.2%}")
    
    except SpeechToTextError as exc:
        print(f"  STT error: {exc}")
    except Exception as exc:
        print(f"  Unexpected error: {exc}")
