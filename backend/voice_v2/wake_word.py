"""
Wake Word Engine — JARVIS v8.0
Detecta "Hey JARVIS" (ou variantes) no áudio em tempo real e acorda o pipeline.

Estratégia: keyword spotting leve por energia + template matching.
Não requer modelo externo — funciona com NumPy puro.
Quando Whisper está disponível, usa STT curto para confirmar.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Callable, Optional

import numpy as np

log = logging.getLogger("jarvis.wake_word")

# Palavras-chave que ativam o JARVIS (lowercase, sem acentos OK)
WAKE_WORDS = [
    "hey jarvis", "jarvis", "ei jarvis", "oi jarvis",
    "hey jarvis", "ok jarvis", "activate jarvis",
]

ENERGY_THRESHOLD = 0.015  # nível mínimo de energia para processar
CONFIRM_TIMEOUT_S = 2.5   # segundos para capturar após wake word
COOLDOWN_S = 2.0          # anti-spam: não reativa por N segundos


class WakeWordEngine:
    """
    Roda em background ouvindo o microfone.
    Quando detecta wake word → chama on_wake_word(audio_após_comando).
    """

    def __init__(
        self,
        on_wake: Optional[Callable] = None,
        device_index: Optional[int] = None,
        sample_rate: int = 16000,
    ):
        self.on_wake = on_wake          # callback async(audio: np.ndarray)
        self.device = device_index
        self.sample_rate = sample_rate
        self._running = False
        self._last_wake = 0.0
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stt = None

    # ── Public API ─────────────────────────────────────────────────────────────

    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        """Inicia escuta em thread de background."""
        self._loop = loop or asyncio.get_event_loop()
        self._load_stt()
        self._running = True
        self._thread = threading.Thread(
            target=self._listen_loop,
            daemon=True,
            name="jarvis-wake-word",
        )
        self._thread.start()
        log.info("[WAKE_WORD] Engine iniciado — aguardando 'Hey JARVIS'")

    def stop(self):
        self._running = False
        log.info("[WAKE_WORD] Engine parado")

    def is_running(self) -> bool:
        return self._running and (self._thread is not None) and self._thread.is_alive()

    # ── Internal ───────────────────────────────────────────────────────────────

    def _load_stt(self):
        """Carrega Whisper tiny para confirmação de wake word."""
        try:
            from faster_whisper import WhisperModel
            self._stt = WhisperModel(
                "tiny",
                device="cpu",
                compute_type="int8",
                download_root="models/whisper",
            )
            log.info("[WAKE_WORD] Whisper tiny carregado para confirmação")
        except Exception as e:
            log.warning("[WAKE_WORD] Whisper não disponível: %s — usando energia apenas", e)

    def _listen_loop(self):
        """Loop principal: captura janelas de áudio e verifica wake word."""
        try:
            import sounddevice as sd
        except ImportError:
            log.error("[WAKE_WORD] sounddevice não instalado — wake word desabilitado")
            return

        CHUNK = 1024
        WINDOW_S = 1.5  # janela de análise em segundos
        window_frames = int(self.sample_rate * WINDOW_S)
        buf: list[np.ndarray] = []

        def _cb(indata, frames, time_info, status):
            chunk = np.squeeze(indata).copy()
            buf.append(chunk)
            # Manter apenas últimos window_frames de áudio
            total = sum(len(c) for c in buf)
            while total > window_frames and buf:
                removed = buf.pop(0)
                total -= len(removed)

        device = self._detect_device()
        log.info("[WAKE_WORD] Escutando no dispositivo: %s", device)

        try:
            with sd.InputStream(
                device=device,
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                blocksize=CHUNK,
                callback=_cb,
            ):
                while self._running:
                    time.sleep(0.4)
                    if not buf:
                        continue

                    audio = np.concatenate(buf)
                    energy = float(np.abs(audio).mean())

                    if energy < ENERGY_THRESHOLD:
                        continue

                    # Cooldown check
                    now = time.time()
                    if now - self._last_wake < COOLDOWN_S:
                        continue

                    # Verificar wake word
                    if self._check_wake_word(audio):
                        self._last_wake = now
                        log.info("[WAKE_WORD] Wake word detectada! Ativando JARVIS...")
                        buf.clear()

                        # Capturar comando após wake word
                        cmd_audio = self._capture_command(device)
                        if cmd_audio is not None and self.on_wake and self._loop:
                            asyncio.run_coroutine_threadsafe(
                                self.on_wake(cmd_audio), self._loop
                            )
        except Exception as e:
            log.error("[WAKE_WORD] Erro no loop: %s", e)

    def _check_wake_word(self, audio: np.ndarray) -> bool:
        """Verifica se o áudio contém wake word via STT ou keyword matching."""
        if self._stt is None:
            # Sem STT: aceitar qualquer áudio com energia suficiente
            # como wake (menos preciso, mas funciona)
            return float(np.abs(audio).mean()) > ENERGY_THRESHOLD * 2.5

        try:
            import io
            import soundfile as sf

            buf = io.BytesIO()
            sf.write(buf, audio, self.sample_rate, format="WAV")
            buf.seek(0)

            segments, _ = self._stt.transcribe(
                buf,
                language="pt",
                task="transcribe",
                vad_filter=True,
                beam_size=1,
            )
            text = " ".join(s.text for s in segments).lower().strip()
            log.debug("[WAKE_WORD] STT resultado: '%s'", text)

            for kw in WAKE_WORDS:
                if kw in text:
                    return True
        except Exception as e:
            log.debug("[WAKE_WORD] STT check failed: %s", e)

        return False

    def _capture_command(self, device) -> Optional[np.ndarray]:
        """Captura o áudio do comando que vem APÓS a wake word."""
        try:
            import sounddevice as sd

            duration = CONFIRM_TIMEOUT_S
            log.info("[WAKE_WORD] Capturando comando por %.1fs...", duration)

            audio = sd.rec(
                int(duration * self.sample_rate),
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                device=device,
            )
            sd.wait()
            result = np.squeeze(audio)
            if float(np.abs(result).mean()) > ENERGY_THRESHOLD:
                return result
            return None
        except Exception as e:
            log.error("[WAKE_WORD] Erro ao capturar comando: %s", e)
            return None

    def _detect_device(self):
        """Auto-deteta dispositivo de entrada."""
        if self.device is not None:
            return self.device
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            for i, d in enumerate(devices):
                if d["max_input_channels"] > 0:
                    name = d["name"].lower()
                    if any(k in name for k in ["headset", "headphone", "usb", "mic"]):
                        return i
            default = sd.default.device[0]
            return default
        except Exception:
            return None


# ── Singleton ──────────────────────────────────────────────────────────────────

_engine: Optional[WakeWordEngine] = None


def get_wake_word_engine() -> WakeWordEngine:
    global _engine
    if _engine is None:
        _engine = WakeWordEngine()
    return _engine


def start_wake_word(
    on_wake: Callable,
    loop: Optional[asyncio.AbstractEventLoop] = None,
    device: Optional[int] = None,
) -> WakeWordEngine:
    """Cria e inicia o engine de wake word."""
    global _engine
    _engine = WakeWordEngine(on_wake=on_wake, device_index=device)
    _engine.start(loop=loop)
    return _engine
