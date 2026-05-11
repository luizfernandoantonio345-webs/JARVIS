"""
Audio Capture Module — Real-time microphone streaming with device management.

Provides:
  - List available audio devices
  - Stream audio chunks in real-time (generator)
  - Record until silence detected
  - Test microphone functionality
  - Graceful error handling and recovery

Uses sounddevice for cross-platform audio I/O.
"""

from __future__ import annotations

import asyncio
import logging
import numpy as np
import sounddevice as sd
import soundfile as sf
from pathlib import Path
from typing import Generator

from .persona import VoiceConfig

log = logging.getLogger(__name__)


class JarvisAudioError(Exception):
    """Base exception for audio subsystem errors."""
    pass


class NoAudioDeviceError(JarvisAudioError):
    """Raised when no audio device is found."""
    pass


class AudioStream:
    """Handles continuous audio stream from microphone."""
    
    def __init__(
        self,
        sample_rate: int = VoiceConfig.SAMPLE_RATE,
        channels: int = VoiceConfig.CHANNELS,
        chunk_duration_ms: int = VoiceConfig.CHUNK_DURATION_MS,
        device_index: int | None = VoiceConfig.MICROPHONE_INDEX,
    ) -> None:
        """
        Initialize audio stream.
        
        Args:
            sample_rate: Samples per second (16000 = Whisper standard)
            channels: Number of channels (1 = mono)
            chunk_duration_ms: Duration of each chunk in milliseconds
            device_index: Microphone device index (None = default)
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_duration_ms = chunk_duration_ms
        self.device_index = device_index
        
        # Calculate chunk size in samples
        self.chunk_size = int(sample_rate * chunk_duration_ms / 1000)
        
        self._stream = None
        self._is_running = False
        
        log.info(
            f"AudioStream initialized: {sample_rate}Hz, "
            f"{channels}ch, chunk={chunk_duration_ms}ms, device={device_index}"
        )

    def _validate_device(self) -> bool:
        """Validate that specified device exists and is usable."""
        try:
            devices = sd.query_devices()
            if isinstance(devices, dict):  # Single device
                return True
            if self.device_index is None:
                return True
            if 0 <= self.device_index < len(devices):
                return True
            log.error(f"Invalid device index: {self.device_index}")
            return False
        except Exception as exc:
            log.error(f"Failed to query audio devices: {exc}")
            return False

    def start(self) -> None:
        """Start the audio stream."""
        if self._is_running:
            log.warning("Stream already running")
            return
        
        if not self._validate_device():
            raise NoAudioDeviceError(f"Audio device {self.device_index} not found")
        
        try:
            self._stream = sd.InputStream(
                device=self.device_index,
                samplerate=self.sample_rate,
                channels=self.channels,
                blocksize=self.chunk_size,
                latency="low",
            )
            self._stream.start()
            self._is_running = True
            log.info("AudioStream started")
        except Exception as exc:
            log.error(f"Failed to start stream: {exc}")
            raise JarvisAudioError(f"Cannot start audio stream: {exc}")

    def stop(self) -> None:
        """Stop the audio stream."""
        if not self._is_running:
            return
        
        try:
            if self._stream:
                self._stream.stop()
                self._stream.close()
            self._is_running = False
            log.info("AudioStream stopped")
        except Exception as exc:
            log.error(f"Error stopping stream: {exc}")

    def read_chunk(self) -> np.ndarray:
        """
        Read a single chunk of audio.
        
        Returns:
            numpy array of shape (chunk_size, channels)
        
        Raises:
            JarvisAudioError: If stream not running or read fails
        """
        if not self._is_running or self._stream is None:
            raise JarvisAudioError("Stream not running")
        
        try:
            chunk, overflowed = self._stream.read(self.chunk_size)
            if overflowed:
                log.debug("Audio buffer overflow (data lost)")
            return chunk
        except Exception as exc:
            log.error(f"Failed to read audio chunk: {exc}")
            raise JarvisAudioError(f"Cannot read audio: {exc}")

    def __enter__(self) -> AudioStream:
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.stop()


class AudioCapture:
    """High-level audio capture with device management and utilities."""

    def __init__(
        self,
        sample_rate: int = VoiceConfig.SAMPLE_RATE,
        channels: int = VoiceConfig.CHANNELS,
        chunk_duration_ms: int = VoiceConfig.CHUNK_DURATION_MS,
        device_index: int | None = VoiceConfig.MICROPHONE_INDEX,
    ) -> None:
        """
        Initialize audio capture.
        
        Args:
            sample_rate: Samples per second
            channels: Number of channels
            chunk_duration_ms: Chunk duration in milliseconds
            device_index: Microphone device index
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_duration_ms = chunk_duration_ms
        self.device_index = device_index
        
        self._stream: AudioStream | None = None

    @staticmethod
    def list_devices() -> dict[int, str]:
        """
        List all available audio input devices.
        
        Returns:
            Dictionary mapping device index to device name
        """
        try:
            devices = sd.query_devices()
            result = {}
            
            if isinstance(devices, dict):
                # Single device
                result[0] = devices.get("name", "Unknown")
            else:
                # Multiple devices
                for idx, dev in enumerate(devices):
                    # Only include input devices
                    if dev.get("max_input_channels", 0) > 0:
                        result[idx] = dev.get("name", f"Device {idx}")
            
            log.info(f"Found {len(result)} audio input devices")
            return result
        except Exception as exc:
            log.error(f"Failed to list audio devices: {exc}")
            return {}

    def stream_chunks(self) -> Generator[np.ndarray, None, None]:
        """
        Generator that yields audio chunks continuously.
        
        Yields:
            numpy arrays of audio data
        
        Raises:
            NoAudioDeviceError: If no device found
            JarvisAudioError: If stream fails
        """
        devices = self.list_devices()
        if not devices:
            raise NoAudioDeviceError("No audio input devices found")
        
        with AudioStream(
            self.sample_rate,
            self.channels,
            self.chunk_duration_ms,
            self.device_index,
        ) as stream:
            log.info("Starting audio stream generator")
            try:
                while True:
                    chunk = stream.read_chunk()
                    yield chunk
            except KeyboardInterrupt:
                log.info("Audio stream interrupted by user")
            except Exception as exc:
                log.error(f"Error in audio stream: {exc}")
                raise JarvisAudioError(f"Stream error: {exc}")

    async def record_until_silence(
        self,
        vad,  # VoiceActivityDetector
        max_seconds: int = 10,
    ) -> np.ndarray:
        """
        Record audio until silence is detected or max duration reached.
        
        Args:
            vad: Voice Activity Detector instance
            max_seconds: Maximum recording duration
        
        Returns:
            Recorded audio as numpy array
        
        Raises:
            JarvisAudioError: If recording fails
        """
        log.info(f"Recording until silence (max {max_seconds}s)")
        
        audio_chunks: list[np.ndarray] = []
        max_chunks = int(self.sample_rate * max_seconds / (self.chunk_duration_ms * 10))
        
        try:
            for i, chunk in enumerate(self.stream_chunks()):
                if i > max_chunks:
                    log.warning("Max recording duration reached")
                    break
                
                audio_chunks.append(chunk)
                
                # Check for silence
                if len(audio_chunks) > 10:  # Need at least 10 chunks for reliable VAD
                    # Concatenate last few chunks
                    recent_audio = np.concatenate(audio_chunks[-10:])
                    if vad.find_speech_end(recent_audio) > 0:
                        log.info("Silence detected, stopping recording")
                        break
                
                # Yield to event loop
                await asyncio.sleep(0)
            
            if not audio_chunks:
                raise JarvisAudioError("No audio captured")
            
            # Concatenate all chunks
            full_audio = np.concatenate(audio_chunks)
            log.info(f"Recording complete: {len(full_audio)} samples, {len(full_audio) / self.sample_rate:.2f}s")
            return full_audio
        
        except KeyboardInterrupt:
            log.info("Recording interrupted")
            if audio_chunks:
                return np.concatenate(audio_chunks)
            raise JarvisAudioError("Recording interrupted by user")

    @staticmethod
    def test_microphone(
        duration_seconds: float = 2.0,
        output_path: Path | None = None,
        sample_rate: int = VoiceConfig.SAMPLE_RATE,
    ) -> bool:
        """
        Test microphone by recording a short sample.
        
        Args:
            duration_seconds: Duration of test recording
            output_path: Optional path to save test audio (.wav)
            sample_rate: Sample rate for recording
        
        Returns:
            True if microphone works, False otherwise
        """
        log.info(f"Testing microphone for {duration_seconds}s")
        
        try:
            # Record audio
            audio = sd.rec(
                int(sample_rate * duration_seconds),
                samplerate=sample_rate,
                channels=1,
                device=None,  # Use default device
            )
            sd.wait()  # Wait for recording to finish
            
            # Verify we got audio
            if audio is None or len(audio) == 0:
                log.error("Microphone test: no audio captured")
                return False
            
            # Check for non-zero audio
            if np.max(np.abs(audio)) < 0.01:
                log.warning("Microphone test: audio detected but very quiet")
            else:
                log.info(f"Microphone test: audio captured (peak: {np.max(np.abs(audio)):.3f})")
            
            # Save test audio if requested
            if output_path:
                sf.write(str(output_path), audio, sample_rate)
                log.info(f"Microphone test: saved to {output_path}")
            
            return True
        
        except Exception as exc:
            log.error(f"Microphone test failed: {exc}")
            return False


# ──────────────────────────────────────────────────────────────────────────────
# Test entry point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    print("\n=== JARVIS Audio Capture Test ===\n")
    
    # Test 1: List devices
    print("Test 1: List audio devices")
    devices = AudioCapture.list_devices()
    if devices:
        for idx, name in devices.items():
            print(f"  [{idx}] {name}")
    else:
        print("  No devices found!")
    print()
    
    # Test 2: Test microphone
    print("Test 2: Test microphone")
    test_output = Path("/tmp/jarvis_mic_test.wav")
    if AudioCapture.test_microphone(duration_seconds=2.0, output_path=test_output):
        print(f"  Microphone OK! Test file: {test_output}")
    else:
        print("  Microphone test FAILED")
    print()
    
    # Test 3: Stream chunks (brief)
    print("Test 3: Stream audio chunks (5 seconds)")
    try:
        capture = AudioCapture()
        chunk_count = 0
        for i, chunk in enumerate(capture.stream_chunks()):
            chunk_count += 1
            if i % 5 == 0:
                rms = np.sqrt(np.mean(chunk**2))
                print(f"  Chunk {i}: {chunk.shape} (RMS: {rms:.4f})")
            if i >= 40:  # ~5 seconds at 80ms chunks
                break
        print(f"  Streamed {chunk_count} chunks successfully")
    except KeyboardInterrupt:
        print("  Interrupted by user")
    except Exception as exc:
        print(f"  Stream test failed: {exc}")
