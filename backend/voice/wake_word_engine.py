"""
Wake Word Engine — Always-listening "JARVIS" detection.
Uses openwakeword + sounddevice for real-time wake word detection.
Runs in daemon thread — never blocks FastAPI.
"""

import asyncio
import logging
import threading
import time
from typing import Callable, Optional

import numpy as np

log = logging.getLogger(__name__)


class WakeWordEngine:
    """
    Real-time wake word detection engine using openwakeword.
    
    Attributes:
        SAMPLE_RATE: Audio sample rate (16kHz)
        CHUNK_MS: Audio chunk size in milliseconds (80ms)
        CHUNK_SIZE: Audio chunk size in samples
    """
    
    SAMPLE_RATE = 16000
    CHUNK_MS = 80
    CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_MS / 1000)  # 1280 samples

    def __init__(
        self,
        keyword: str = "jarvis",
        threshold: float = 0.06,
        on_detected: Optional[Callable] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ):
        """
        Initialize Wake Word Engine.
        
        Args:
            keyword: Wake word keyword (e.g., "jarvis")
            threshold: Detection threshold (0.0-1.0)
            on_detected: Async callback when wake word detected
            loop: Asyncio event loop for callback execution
        """
        self.keyword = keyword
        self.threshold = threshold
        self.callback = on_detected
        self.loop = loop or asyncio.get_event_loop()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._model = None
        self._engine_type: str = "none"  # "openwakeword" | "pocketsphinx"
        self._debounce = 0.0  # Timestamp of last detection (prevent re-trigger)

    def _load_model(self) -> bool:
        """
        Load openwakeword model for wake word detection.
        
        Tries multiple approaches:
        1. openwakeword with hey_jarvis model
        2. openwakeword with default models
        3. pocketsphinx as lightweight fallback
        
        Returns:
            True if model loaded successfully, False otherwise
        """
        # Strategy 1: Try openwakeword
        try:
            from openwakeword import Model
            
            # Try ONNX first to avoid tflite-runtime dependency on Windows.
            try:
                self._model = Model(
                    wakeword_models=["hey_jarvis"],
                    inference_framework="onnx",
                )
                log.info("[WAKE] Modelo 'hey_jarvis' carregado via openwakeword (onnx)")
                self._engine_type = "openwakeword"
                return True
            except Exception as e1:
                log.warning("[WAKE] hey_jarvis via openwakeword falhou: %s", e1)

                # Fallback to openwakeword default
                try:
                    self._model = Model(inference_framework="onnx")
                    log.info("[WAKE] Modelo padrão openwakeword carregado (onnx)")
                    self._engine_type = "openwakeword"
                    return True
                except Exception as e2:
                    log.warning("[WAKE] openwakeword padrão também falhou: %s", e2)

        except ImportError:
            log.warning("[WAKE] openwakeword não disponível")

        # Strategy 2: Try pocketsphinx as lightweight alternative
        try:
            from pocketsphinx import LiveSpeech
            log.info("[WAKE] Fallback para pocketsphinx (lightweight)")
            self._model = "pocketsphinx"
            self._engine_type = "pocketsphinx"
            return True
        except ImportError:
            log.warning("[WAKE] pocketsphinx também não instalado")

        # Strategy 3: Use dummy model for testing
        log.error("[WAKE] Nenhum motor de wake word disponível")
        return False

    def _listen_loop(self) -> None:
        """
        Main listening loop running in daemon thread.
        
        Captures audio via sounddevice, processes with openwakeword model,
        triggers callback when wake word detected (with 2s debounce).
        """
        if not self._load_model():
            log.error("[WAKE] Falha ao carregar modelo — engine não pode iniciar")
            return

        log.info("[WAKE] Escutando wake word '%s' (threshold=%.2f)...", self.keyword, self.threshold)

        if self._engine_type == "pocketsphinx":
            try:
                from pocketsphinx import LiveSpeech

                speech = LiveSpeech(
                    sampling_rate=self.SAMPLE_RATE,
                    keyphrase=self.keyword,
                    kws_threshold=1e-20,
                )
                log.info("[WAKE] Fallback pocketsphinx ativo para keyphrase '%s'", self.keyword)

                for phrase in speech:
                    if not self._running:
                        break

                    hyp = ""
                    try:
                        hyp = phrase.hypothesis() or ""
                    except Exception:
                        hyp = str(phrase) if phrase else ""

                    if not hyp:
                        continue

                    now = time.time()
                    if self.keyword.lower() in hyp.lower() and (now - self._debounce) > 2.0:
                        self._debounce = now
                        log.info("[WAKE] Detectado via pocketsphinx: %s", hyp)
                        if self.callback and self.loop:
                            try:
                                asyncio.run_coroutine_threadsafe(
                                    self.callback(),
                                    self.loop,
                                )
                            except Exception as e:
                                log.error("[WAKE] Erro ao executar callback: %s", e)
                log.info("[WAKE] Listen loop pocketsphinx encerrado")
                return
            except Exception as e:
                log.error("[WAKE] Fallback pocketsphinx falhou: %s", e)
                return

        try:
            import sounddevice as sd

            def audio_callback(indata, frames, time_info, status):
                """Callback for audio stream input."""
                if not self._running:
                    return

                if status:
                    log.debug("[WAKE] Audio callback status: %s", status)

                try:
                    # Extract audio data
                    audio = np.squeeze(indata).astype(np.float32)

                    # Predict wake word score
                    scores = self._model.predict(audio, apply_sigmoid=True)

                    # Get maximum score across all models
                    score = max(scores.values()) if scores else 0.0

                    # Check debounce and threshold
                    now = time.time()
                    if score >= self.threshold and (now - self._debounce) > 2.0:
                        self._debounce = now
                        log.info("[WAKE] Detectado! Score=%.3f (threshold=%.2f)", score, self.threshold)

                        # Call async callback safely
                        if self.callback and self.loop:
                            try:
                                asyncio.run_coroutine_threadsafe(
                                    self.callback(),
                                    self.loop,
                                )
                            except Exception as e:
                                log.error("[WAKE] Erro ao executar callback: %s", e)
                except Exception as e:
                    log.debug("[WAKE] Erro no processamento de áudio: %s", e)

            # Start audio stream
            with sd.InputStream(
                samplerate=self.SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=self.CHUNK_SIZE,
                callback=audio_callback,
            ):
                log.info("[WAKE] Stream de áudio iniciado")
                while self._running:
                    time.sleep(0.1)

        except ImportError:
            log.error("[WAKE] sounddevice não instalado")
        except Exception as e:
            log.error("[WAKE] Erro no stream de áudio: %s", e)

        log.info("[WAKE] Listen loop encerrado")

    def start(self) -> None:
        """
        Start the wake word detection engine in a daemon thread.
        
        Never blocks — runs asynchronously in background.
        """
        if self._running:
            log.warning("[WAKE] Engine já está rodando")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._listen_loop,
            daemon=True,
            name="jarvis-wake-word",
        )
        self._thread.start()
        log.info("[WAKE] Engine iniciada em thread daemon")

    def stop(self) -> None:
        """Stop the wake word detection engine."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        log.info("[WAKE] Engine parada")


# Module-level singleton
_engine: Optional[WakeWordEngine] = None


def get_wake_word_engine() -> Optional[WakeWordEngine]:
    """
    Get the global wake word engine instance.
    
    Returns:
        WakeWordEngine instance or None if not initialized
    """
    return _engine


def start_wake_word(
    on_detected: Callable,
    loop: asyncio.AbstractEventLoop,
    keyword: str = "jarvis",
    threshold: float = 0.06,
) -> Optional[WakeWordEngine]:
    """
    Initialize and start the global wake word engine.
    
    Args:
        on_detected: Async callback when wake word detected
        loop: Asyncio event loop
        keyword: Wake word keyword
        threshold: Detection threshold
        
    Returns:
        WakeWordEngine instance or None if initialization failed
    """
    global _engine

    try:
        _engine = WakeWordEngine(
            keyword=keyword,
            threshold=threshold,
            on_detected=on_detected,
            loop=loop,
        )
        _engine.start()
        return _engine
    except Exception as e:
        log.error("[WAKE] Falha ao inicializar engine: %s", e)
        return None


def stop_wake_word() -> None:
    """Stop the global wake word engine."""
    global _engine
    if _engine:
        _engine.stop()
        _engine = None


__all__ = [
    "WakeWordEngine",
    "get_wake_word_engine",
    "start_wake_word",
    "stop_wake_word",
]
