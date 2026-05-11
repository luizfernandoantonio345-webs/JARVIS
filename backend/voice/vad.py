"""
Voice Activity Detection Module — Detects when user stops speaking.

Uses silero-vad for efficient speech endpoint detection.
- Identifies when user finishes speaking
- Removes silence from beginning and end of audio
- Fallback to RMS-based VAD if silero-vad unavailable

Silero VAD is lightweight, offline, and works on CPU.
"""

from __future__ import annotations

import logging
import numpy as np
from typing import Any

from .persona import VoiceConfig

log = logging.getLogger(__name__)

try:
    import torch
    from silero_vad import load_silero_vad
    HAS_SILERO = True
except ImportError:
    HAS_SILERO = False
    log.warning("silero-vad not installed, using RMS-based fallback")


class VoiceActivityDetector:
    """Detects voice activity and silence boundaries."""

    def __init__(
        self,
        threshold: float = VoiceConfig.VAD_THRESHOLD,
        min_silence_ms: int = VoiceConfig.VAD_MIN_SILENCE_MS,
        sample_rate: int = VoiceConfig.SAMPLE_RATE,
    ) -> None:
        """
        Initialize VAD.
        
        Args:
            threshold: Speech confidence threshold (0.0-1.0)
            min_silence_ms: Minimum silence duration to trigger cutoff
            sample_rate: Audio sample rate
        """
        self.threshold = threshold
        self.min_silence_ms = min_silence_ms
        self.sample_rate = sample_rate
        self.min_silence_samples = int(sample_rate * min_silence_ms / 1000)
        
        self._model: Any = None
        self._initialized = False
        
        # Try to load silero-vad
        if HAS_SILERO:
            self._init_silero()
        else:
            log.warning("Silero VAD unavailable, using RMS fallback")

    def _init_silero(self) -> None:
        """Load silero-vad model (lazy loading)."""
        try:
            self._model = load_silero_vad()
            self._initialized = True
            log.info("Silero VAD initialized")
        except Exception as exc:
            log.error(f"Failed to load silero-vad: {exc}")
            self._initialized = False

    def is_speech(self, chunk: np.ndarray) -> bool:
        """
        Determine if chunk contains speech.
        
        Args:
            chunk: Audio chunk (numpy array)
        
        Returns:
            True if speech detected, False if silence
        """
        if self._initialized and self._model:
            return self._is_speech_silero(chunk)
        else:
            return self._is_speech_rms(chunk)

    def _is_speech_silero(self, chunk: np.ndarray) -> bool:
        """Use silero-vad to detect speech."""
        try:
            # Ensure mono float32
            if chunk.ndim > 1:
                chunk = chunk.mean(axis=1)
            chunk = chunk.astype(np.float32)
            
            # Normalize to [-1, 1]
            if np.max(np.abs(chunk)) > 0:
                chunk = chunk / np.max(np.abs(chunk))
            
            # Convert to torch tensor
            audio_tensor = torch.from_numpy(chunk)
            
            # Resample if needed
            if self.sample_rate != 16000:
                log.debug(f"Resampling from {self.sample_rate}Hz to 16kHz")
                # Simple decimation for 16000Hz
                if self.sample_rate == 16000:
                    pass
                elif self.sample_rate > 16000:
                    ratio = self.sample_rate // 16000
                    audio_tensor = audio_tensor[::ratio]
            
            # Get voice probabilities
            confidence = self._model(audio_tensor, self.sample_rate).item()
            return confidence >= self.threshold
        
        except Exception as exc:
            log.debug(f"Silero VAD error: {exc}, using RMS")
            return self._is_speech_rms(chunk)

    def _is_speech_rms(self, chunk: np.ndarray) -> bool:
        """Fallback: RMS-based voice detection."""
        if chunk.ndim > 1:
            chunk = chunk.mean(axis=1)
        
        # Calculate RMS (root mean square)
        rms = np.sqrt(np.mean(chunk ** 2))
        
        # Threshold tuned for typical speech levels (adjust if needed)
        speech_threshold = 0.02 * self.threshold  # Scale by confidence threshold
        return rms >= speech_threshold

    def find_speech_end(self, audio: np.ndarray) -> int:
        """
        Find the sample index where speech ends (silence detected).
        
        Args:
            audio: Audio array
        
        Returns:
            Index of detected silence start (or len(audio) if no silence)
        """
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        
        chunk_size = self.sample_rate // 20  # 50ms chunks
        silence_count = 0
        
        for i in range(len(audio) - chunk_size, -1, -chunk_size):
            chunk = audio[i:i + chunk_size]
            if not self.is_speech(chunk):
                silence_count += 1
                if silence_count * chunk_size >= self.min_silence_samples:
                    return i + chunk_size
            else:
                silence_count = 0
        
        return len(audio)

    def trim_silence(self, audio: np.ndarray) -> np.ndarray:
        """
        Remove silence from beginning and end of audio.
        
        Args:
            audio: Audio array
        
        Returns:
            Trimmed audio array
        """
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        
        chunk_size = self.sample_rate // 20  # 50ms chunks
        
        # Find speech start
        start_idx = 0
        for i in range(0, len(audio) - chunk_size, chunk_size):
            chunk = audio[i:i + chunk_size]
            if self.is_speech(chunk):
                start_idx = max(0, i - chunk_size)
                break
        
        # Find speech end
        end_idx = len(audio)
        for i in range(len(audio) - chunk_size, -1, -chunk_size):
            chunk = audio[i:i + chunk_size]
            if self.is_speech(chunk):
                end_idx = min(len(audio), i + chunk_size * 2)
                break
        
        trimmed = audio[start_idx:end_idx]
        log.info(f"Trimmed silence: {len(audio)} → {len(trimmed)} samples")
        return trimmed

    def get_speech_segments(self, audio: np.ndarray) -> list[tuple[int, int]]:
        """
        Find all speech segments in audio (returns start/end indices).
        
        Args:
            audio: Audio array
        
        Returns:
            List of (start_idx, end_idx) tuples for each speech segment
        """
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        
        chunk_size = self.sample_rate // 20  # 50ms chunks
        segments = []
        in_speech = False
        start = 0
        
        for i in range(0, len(audio) - chunk_size, chunk_size):
            chunk = audio[i:i + chunk_size]
            is_speech = self.is_speech(chunk)
            
            if is_speech and not in_speech:
                start = i
                in_speech = True
            elif not is_speech and in_speech:
                segments.append((start, i))
                in_speech = False
        
        # Close last segment if still in speech
        if in_speech:
            segments.append((start, len(audio)))
        
        log.info(f"Found {len(segments)} speech segments")
        return segments


# ──────────────────────────────────────────────────────────────────────────────
# Test entry point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from pathlib import Path
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    print("\n=== JARVIS Voice Activity Detector Test ===\n")
    
    # Test 1: Create silence and speech chunks
    print("Test 1: Create test audio (silence + noise)")
    vad = VoiceActivityDetector()
    sample_rate = 16000
    
    # Create 1 second of silence
    silence = np.zeros(sample_rate, dtype=np.float32)
    
    # Create 1 second of "speech" (white noise at speech level)
    np.random.seed(42)
    speech = np.random.normal(0, 0.05, sample_rate).astype(np.float32)
    
    # Combine: silence + speech + silence
    test_audio = np.concatenate([silence, speech, silence])
    
    print(f"  Created {len(test_audio)} samples ({len(test_audio)/sample_rate:.1f}s)")
    print(f"    Silence region: 0-{sample_rate}")
    print(f"    Speech region: {sample_rate}-{sample_rate*2}")
    print(f"    Silence region: {sample_rate*2}-{sample_rate*3}")
    print()
    
    # Test 2: Test is_speech
    print("Test 2: Detect speech in chunks")
    chunk_size = sample_rate // 20  # 50ms chunks
    for i in range(0, len(test_audio), chunk_size * 5):
        chunk = test_audio[i:i + chunk_size * 5]
        is_speech = vad.is_speech(chunk)
        rms = np.sqrt(np.mean(chunk ** 2))
        print(f"  [{i//sample_rate:.1f}s] RMS={rms:.4f}, Speech={is_speech}")
    print()
    
    # Test 3: Trim silence
    print("Test 3: Trim silence from audio")
    trimmed = vad.trim_silence(test_audio)
    print(f"  Original: {len(test_audio)} samples ({len(test_audio)/sample_rate:.1f}s)")
    print(f"  Trimmed: {len(trimmed)} samples ({len(trimmed)/sample_rate:.1f}s)")
    print()
    
    # Test 4: Get speech segments
    print("Test 4: Find speech segments")
    segments = vad.get_speech_segments(test_audio)
    for i, (start, end) in enumerate(segments):
        print(f"  Segment {i}: {start}-{end} samples ({start/sample_rate:.1f}s-{end/sample_rate:.1f}s)")
