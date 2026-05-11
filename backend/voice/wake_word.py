"""
Wake Word Detection Module — Detects "JARVIS" wake word in audio stream.

Uses openWakeWord for efficient, offline wake word detection.
- Runs in background thread
- Minimal CPU usage
- Customizable wake word and confidence threshold
- Event callback when wake word detected
- Auto-debouncing to prevent re-triggers

openWakeWord is open-source and works offline on CPU.
"""

from __future__ import annotations

import asyncio
import logging
import numpy as np
import threading
import time
from typing import Callable, Optional

from .persona import VoiceConfig, Phrases

log = logging.getLogger(__name__)

try:
    import openwakeword
    from openwakeword.model import Model
    HAS_OPENWAKEWORD = True
except ImportError:
    HAS_OPENWAKEWORD = False
    log.warning("openwakeword not installed, wake word detection disabled")


class WakeWordDetectedError(Exception):
    """Raised if wake word model fails to load."""
    pass


class WakeWordDetector:
    """
    Detects wake word ("JARVIS") in continuous audio stream.
    
    Runs in background thread, non-blocking.
    """

    def __init__(
        self,
        keyword: str = VoiceConfig.WAKE_WORD,
        threshold: float = VoiceConfig.WAKE_THRESHOLD,
        model_name: str = VoiceConfig.WAKE_MODEL,
        sample_rate: int = VoiceConfig.SAMPLE_RATE,
        on_detected: Optional[Callable] -> None] = None,
    ) -> None:
        """
        Initialize wake word detector.
        
        Args:
            keyword: Wake word (default: "jarvis")
            threshold: Confidence threshold (0.0-1.0)
            model_name: OpenWakeWord model name
            sample_rate: Audio sample rate (16000 Hz standard)
            on_detected: Async callback when wake word detected
        """
        self.keyword = keyword.lower()
        self.threshold = threshold
        self.model_name = model_name
        self.sample_rate = sample_rate
        self.on_detected = on_detected
        
        self._model: Optional[Model] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._last_detection_time = 0.0
        self._debounce_seconds = 2.0  # Prevent rapid re-triggers
        
        log.info(
            f"WakeWordDetector initialized: keyword='{keyword}', "
            f"threshold={threshold}, model='{model_name}'"
        )

    def _init_model(self) -> bool:
        """Initialize openWakeWord model (lazy loading)."""
        if not HAS_OPENWAKEWORD:
            log.error("openWakeWord not installed")
            return False
        
        try:
            log.info(f"Loading openWakeWord model: {self.model_name}")
            self._model = Model(
                wakeword_models=[self.model_name],
                inference_framework="tflite",  # Lightweight
            )
            log.info("openWakeWord model loaded successfully")
            return True
        except Exception as exc:
            log.error(f"Failed to load openWakeWord model: {exc}")
            return False

    async def _emit_event(self, score: float) -> None:
        """Emit wake word detected event."""
        log.info(f"💡 Wake word detected! Score: {score:.3f}")
        
        # Speak acknowledgment
        try:
            from .tts import TextToSpeech
            tts = TextToSpeech()
            # Note: will be non-blocking if TTS supports async
            tts.speak(Phrases.get_ready())
        except Exception as exc:
            log.debug(f"TTS error in wake_word callback: {exc}")
        
        # Call user's callback if provided
        if self.on_detected:
            try:
                if asyncio.iscoroutinefunction(self.on_detected):
                    await self.on_detected(score)
                else:
                    self.on_detected(score)
            except Exception as exc:
                log.error(f"Error in on_detected callback: {exc}")

    def _listen_loop(self) -> None:
        """
        Background thread loop for wake word detection.
        
        Continuously reads from audio stream and checks for wake word.
        """
        try:
            from .audio_capture import AudioCapture
            
            log.info("WakeWordDetector thread started")
            capture = AudioCapture(sample_rate=self.sample_rate)
            
            if not self._init_model():
                log.error("Failed to initialize wake word model")
                return
            
            for chunk in capture.stream_chunks():
                if not self._running:
                    log.info("WakeWordDetector thread stopping")
                    break
                
                try:
                    # Convert chunk to float32 mono
                    if chunk.ndim > 1:
                        chunk = chunk.mean(axis=1)
                    chunk = chunk.astype(np.float32)
                    
                    # Run inference
                    self._model.predict(chunk)
                    scores = self._model.prediction_buffer[self.model_name]
                    
                    if scores is not None and len(scores) > 0:
                        score = float(scores[-1])  # Latest score
                        
                        # Check threshold
                        if score >= self.threshold:
                            now = time.time()
                            # Debounce: ignore if detected recently
                            if now - self._last_detection_time > self._debounce_seconds:
                                self._last_detection_time = now
                                
                                # Queue event for async processing
                                try:
                                    asyncio.run_coroutine_threadsafe(
                                        self._emit_event(score),
                                        asyncio.get_event_loop()
                                    )
                                except Exception as exc:
                                    log.debug(f"Cannot emit event (no event loop): {exc}")
                
                except Exception as exc:
                    log.debug(f"Wake word detection error: {exc}")
        
        except Exception as exc:
            log.error(f"WakeWordDetector thread error: {exc}")
        finally:
            log.info("WakeWordDetector thread ended")

    def start(self) -> None:
        """Start background thread for wake word detection."""
        if self._running:
            log.warning("Wake word detector already running")
            return
        
        if not HAS_OPENWAKEWORD:
            log.error("openWakeWord not available, cannot start detector")
            raise WakeWordDetectedError("openWakeWord not installed")
        
        self._running = True
        self._thread = threading.Thread(
            target=self._listen_loop,
            name="jarvis-wake-word",
            daemon=True,
        )
        self._thread.start()
        log.info("Wake word detector started (background thread)")

    def stop(self) -> None:
        """Stop background thread."""
        if not self._running:
            return
        
        log.info("Stopping wake word detector")
        self._running = False
        
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        
        log.info("Wake word detector stopped")

    def is_running(self) -> bool:
        """Check if detector is running."""
        return self._running

    def set_threshold(self, threshold: float) -> None:
        """Adjust detection threshold at runtime."""
        self.threshold = max(0.0, min(1.0, threshold))
        log.info(f"Wake word threshold adjusted to {self.threshold:.2f}")

    def __enter__(self) -> WakeWordDetector:
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.stop()


# ──────────────────────────────────────────────────────────────────────────────
# Test entry point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    print("\n=== JARVIS Wake Word Detector Test ===\n")
    
    if not HAS_OPENWAKEWORD:
        print("openWakeWord not installed. Install with:")
        print("  pip install openwakeword")
        sys.exit(1)
    
    async def on_wake(score: float) -> None:
        print(f"🎤 Wake word callback triggered! Score: {score:.3f}")
    
    print("Starting wake word detector...")
    print("Say 'JARVIS' or 'Hey JARVIS' to trigger detection")
    print("Press Ctrl+C to stop\n")
    
    try:
        detector = WakeWordDetector(
            keyword="jarvis",
            threshold=0.7,
            on_detected=on_wake,
        )
        detector.start()
        
        # Keep running until interrupted
        while True:
            time.sleep(1.0)
    
    except KeyboardInterrupt:
        print("\n\nStopping...")
        detector.stop()
        print("Done")
    
    except Exception as exc:
        print(f"Error: {exc}")
        sys.exit(1)
