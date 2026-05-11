import asyncio
import importlib
import logging
import math
import tempfile
import time
import wave
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from .controller import process_voice_command
from .input import WhisperTranscriber
from .output import speak

try:
    from ..core.response_engine import response_engine_transform
except ImportError:
    from core.response_engine import response_engine_transform

log = logging.getLogger(__name__)


class VoiceLoopState(str, Enum):
    LISTENING = "LISTENING"
    WAKE_DETECTED = "WAKE_DETECTED"
    RECORDING = "RECORDING"
    PROCESSING = "PROCESSING"
    SPEAKING = "SPEAKING"


@dataclass
class VoiceLoopConfig:
    wake_word: str = "jarvis"
    language_hint: str = "pt"
    sample_rate: int = 16000
    channels: int = 1
    listen_chunk_s: float = 0.35
    wake_phrase_max_s: float = 4.0
    command_timeout_s: float = 12.0
    silence_end_ms: int = 500
    silence_threshold: float = 0.012
    listen_poll_s: float = 0.05
    tts_tail_s: float = 0.35


class _TTSState:
    """Guard that keeps the microphone muted while playback is active."""

    def __init__(self):
        self._tts_lock = asyncio.Lock()
        self.is_speaking: bool = False

    async def run_tts(self, text: str, *, tail_s: float = 0.35) -> str:
        async with self._tts_lock:
            self.is_speaking = True
            try:
                audio_path = await speak(text)
                await asyncio.sleep(_estimate_audio_duration_s(audio_path, text) + tail_s)
                return audio_path
            finally:
                self.is_speaking = False


_tts_state = _TTSState()


async def speak_assistant(text: str, *, tail_s: float = 0.35) -> str:
    filtered = response_engine_transform(text)
    return await _tts_state.run_tts(filtered, tail_s=tail_s)


def capture_audio_realtime(duration: float, sample_rate: int = 16000):
    """Capture microphone audio and return a mono float32 numpy array."""
    np = importlib.import_module("numpy")
    frames = max(1, int(duration * sample_rate))

    try:
        sd = importlib.import_module("sounddevice")
        recording = sd.rec(frames, samplerate=sample_rate, channels=1, dtype="float32")
        sd.wait()
        return np.asarray(recording, dtype=np.float32).reshape(-1)
    except Exception as sd_exc:
        log.debug("sounddevice capture unavailable, trying pyaudio fallback: %s", sd_exc)

    try:
        pyaudio = importlib.import_module("pyaudio")
        pa = pyaudio.PyAudio()
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=sample_rate,
            input=True,
            frames_per_buffer=1024,
        )
        chunks: list[bytes] = []
        remaining = frames
        while remaining > 0:
            size = min(1024, remaining)
            chunks.append(stream.read(size, exception_on_overflow=False))
            remaining -= size
        stream.stop_stream()
        stream.close()
        pa.terminate()
        audio_i16 = np.frombuffer(b"".join(chunks), dtype=np.int16)
        return (audio_i16.astype(np.float32) / 32768.0).reshape(-1)
    except Exception as pa_exc:
        raise RuntimeError(
            "No microphone backend available. Install sounddevice or pyaudio."
        ) from pa_exc


def detect_speech_energy(audio_chunk, threshold: float = 0.012) -> bool:
    """Simple VAD based on RMS energy."""
    np = importlib.import_module("numpy")
    audio = np.asarray(audio_chunk, dtype=np.float32).reshape(-1)
    if audio.size == 0:
        return False
    rms = float(np.sqrt(np.mean(np.square(audio))))
    return math.isfinite(rms) and rms >= threshold


def record_until_silence(
    silence_threshold: float = 0.012,
    max_duration: float = 12.0,
    *,
    sample_rate: int = 16000,
    silence_end_ms: int = 500,
    chunk_duration: float = 0.2,
    initial_audio=None,
) -> Optional[str]:
    """Record speech until silence is detected and save it as a WAV file."""
    np = importlib.import_module("numpy")
    wavfile = importlib.import_module("scipy.io.wavfile")

    chunks = []
    if initial_audio is not None:
        initial = np.asarray(initial_audio, dtype=np.float32).reshape(-1)
        if initial.size:
            chunks.append(initial)

    started = bool(chunks)
    silence_s = 0.0
    start_time = time.monotonic()

    while time.monotonic() - start_time < max_duration:
        chunk = capture_audio_realtime(chunk_duration, sample_rate)
        has_speech = detect_speech_energy(chunk, silence_threshold)

        if has_speech:
            chunks.append(chunk)
            started = True
            silence_s = 0.0
            continue

        if started:
            chunks.append(chunk)
            silence_s += chunk_duration
            if silence_s >= silence_end_ms / 1000.0:
                break

    if not chunks:
        return None

    audio = np.concatenate(chunks).astype(np.float32)
    if not detect_speech_energy(audio, silence_threshold * 0.65):
        return None

    audio_i16 = np.clip(audio, -1.0, 1.0)
    audio_i16 = (audio_i16 * 32767.0).astype(np.int16)
    path = tempfile.mktemp(prefix="jarvis_voice_", suffix=".wav")
    wavfile.write(path, sample_rate, audio_i16)
    return path


def capture_next_audio_path(config: Optional[VoiceLoopConfig] = None) -> Optional[str]:
    """Listen for the next spoken phrase and return a temporary WAV path."""
    cfg = config or VoiceLoopConfig()
    chunk = capture_audio_realtime(cfg.listen_chunk_s, cfg.sample_rate)
    if not detect_speech_energy(chunk, cfg.silence_threshold):
        return None
    return record_until_silence(
        cfg.silence_threshold,
        cfg.wake_phrase_max_s,
        sample_rate=cfg.sample_rate,
        silence_end_ms=cfg.silence_end_ms,
        initial_audio=chunk,
    )


async def voice_loop_background(
    *,
    session_id: str = "voice_v2",
    voice_state=None,
    config: Optional[VoiceLoopConfig] = None,
    on_state_change: Optional[Callable[[VoiceLoopState], None]] = None,
    stop_event: Optional[asyncio.Event] = None,
):
    """Always-listening voice loop with wake word + low latency pipeline."""
    from .voice_state import VoiceState

    cfg = config or VoiceLoopConfig()
    transcriber = WhisperTranscriber()
    state = VoiceLoopState.LISTENING

    voice_state = voice_state or VoiceState()


    async def set_state(next_state: VoiceLoopState) -> None:
        nonlocal state
        if state == next_state:
            return

        state = next_state
        log.info("voice_loop state=%s session=%s", state.value, session_id)

        # VoiceState global update (listening/speaking + anti-eco)
        if next_state in (VoiceLoopState.RECORDING, VoiceLoopState.PROCESSING):
            voice_state.listening = True
            voice_state.speaking = False
        elif next_state == VoiceLoopState.SPEAKING:
            voice_state.listening = False
            voice_state.speaking = True
        elif next_state == VoiceLoopState.WAKE_DETECTED:
            voice_state.listening = False
            voice_state.speaking = True
        else:
            voice_state.listening = True
            voice_state.speaking = False

        if on_state_change:
            try:
                on_state_change(state)
            except Exception:
                log.exception("voice loop state callback failed")


    log.info("voice_loop_realtime started (session=%s)", session_id)
    await set_state(VoiceLoopState.LISTENING)

    while True:
        if stop_event is not None and stop_event.is_set():
            await set_state(VoiceLoopState.LISTENING)
            log.info("voice_loop_realtime stopped (session=%s)", session_id)
            return

        if getattr(voice_state, "speaking", False):
            await asyncio.sleep(cfg.listen_poll_s)
            continue


        await set_state(VoiceLoopState.LISTENING)

        try:
            wake_audio_path = await asyncio.to_thread(capture_next_audio_path, cfg)
        except Exception as exc:
            log.error("microphone capture failed: %s", exc)
            await asyncio.sleep(1.0)
            continue

        if not wake_audio_path:
            await asyncio.sleep(cfg.listen_poll_s)
            continue

        try:
            wake_text = await transcriber.transcribe_audio(wake_audio_path)
        finally:
            _safe_unlink(wake_audio_path)

        if cfg.wake_word not in (wake_text or "").lower():
            continue

        await set_state(VoiceLoopState.WAKE_DETECTED)
        await speak_assistant("Sim?", tail_s=cfg.tts_tail_s)

        if _tts_state.is_speaking:
            await asyncio.sleep(cfg.listen_poll_s)

        await set_state(VoiceLoopState.RECORDING)
        command_audio_path = await asyncio.to_thread(
            record_until_silence,
            cfg.silence_threshold,
            cfg.command_timeout_s,
            sample_rate=cfg.sample_rate,
            silence_end_ms=cfg.silence_end_ms,
        )

        if not command_audio_path:
            await set_state(VoiceLoopState.SPEAKING)
            await speak_assistant("Nao ouvi o comando.", tail_s=cfg.tts_tail_s)
            continue

        await set_state(VoiceLoopState.PROCESSING)
        result = await process_voice_command(
            command_audio_path,
            session_id=session_id,
            speak_response=False,
        )
        response = result.get("response") if isinstance(result, dict) else None

        if response:
            await set_state(VoiceLoopState.SPEAKING)
            await speak_assistant(response, tail_s=cfg.tts_tail_s)


def _estimate_audio_duration_s(audio_path: str, fallback_text: str) -> float:
    if audio_path:
        path = Path(audio_path)
        if path.exists():
            try:
                with wave.open(str(path), "rb") as wav:
                    return wav.getnframes() / float(wav.getframerate())
            except Exception:
                pass

            try:
                audio_segment = importlib.import_module("pydub").AudioSegment
                return len(audio_segment.from_file(str(path))) / 1000.0
            except Exception:
                pass

    words = max(1, len((fallback_text or "").split()))
    return min(12.0, max(0.8, words / 2.6))


def _safe_unlink(path: str) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except Exception:
        log.debug("failed to delete temp audio path: %s", path, exc_info=True)
