"""
Voice Pipeline — Main orchestrator loop for hands-free voice interaction.

Workflow:
  1. IDLE → Wait for wake word "JARVIS"
  2. LISTENING → Record user speech until silence
  3. PROCESSING → Run STT + Orchestrator  
  4. SPEAKING → Play response via TTS
  5. IDLE → Repeat

All operations are non-blocking and emit WebSocket events.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

from .audio_capture import AudioCapture, JarvisAudioError
from .vad import VoiceActivityDetector
from .wake_word import WakeWordDetector
from .stt import SpeechToText, SpeechToTextError
from .tts import TextToSpeech, TextToSpeechError
from .persona import Phrases, format_response, abbreviate_response, VoiceConfig

log = logging.getLogger(__name__)


class VoiceState(Enum):
    """Voice pipeline state machine."""
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    ERROR = "error"


@dataclass
class VoiceEvent:
    """Event emitted by voice pipeline (for WebSocket broadcast)."""
    event_type: str  # "voice_state", "voice_text", "voice_error"
    state: Optional[VoiceState] = None
    text: str = ""
    error: str = ""
    timestamp: float = 0.0
    
    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        result = asdict(self)
        result["state"] = self.state.value if self.state else None
        return result


class VoicePipeline:
    """
    Main voice interaction loop.
    
    Runs continuously, waiting for wake word and processing voice commands.
    All operations are non-blocking and async.
    """

    def __init__(
        self,
        orchestrator: Any,  # CoreOrchestrator or similar
        event_callback: Optional[Callable[[VoiceEvent], None]] = None,
        user_id: str = "default",
    ) -> None:
        """
        Initialize voice pipeline.
        
        Args:
            orchestrator: Main orchestrator (for processing voice commands)
            event_callback: Callback for voice events (e.g., WebSocket emit)
            user_id: User identifier for logging
        """
        self.orchestrator = orchestrator
        self.event_callback = event_callback
        self.user_id = user_id
        
        # State
        self._state = VoiceState.IDLE
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # Components
        self._audio = AudioCapture()
        self._vad = VoiceActivityDetector()
        self._stt = SpeechToText()
        self._tts = TextToSpeech()
        self._wake = WakeWordDetector(on_detected=self._on_wake_detected)
        
        # Event queue
        self._event_queue: asyncio.Queue[VoiceEvent] = asyncio.Queue()
        
        log.info(f"VoicePipeline initialized for user={user_id}")

    @property
    def state(self) -> VoiceState:
        """Current voice state."""
        return self._state

    def _set_state(self, new_state: VoiceState) -> None:
        """Set new state and emit event."""
        if new_state == self._state:
            return
        
        self._state = new_state
        log.info(f"VoicePipeline state: {self._state.value}")
        
        event = VoiceEvent(
            event_type="voice_state",
            state=new_state,
        )
        self._emit_event(event)

    def _emit_event(self, event: VoiceEvent) -> None:
        """Emit event to callback and queue."""
        try:
            if self.event_callback:
                self.event_callback(event)
        except Exception as exc:
            log.error(f"Event callback error: {exc}")

    async def _on_wake_detected(self, score: float) -> None:
        """Callback when wake word detected."""
        log.info(f"Wake word detected (score: {score:.3f})")
        self._set_state(VoiceState.LISTENING)
        
        # Emit text event
        event = VoiceEvent(
            event_type="voice_text",
            text=Phrases.get_ready(),
        )
        self._emit_event(event)

    async def _record_command(self) -> bytes | None:
        """
        Record user speech until silence detected.
        
        Returns:
            Audio bytes or None if failed
        """
        try:
            log.info("Recording user speech...")
            audio = await self._audio.record_until_silence(
                self._vad,
                max_seconds=10,
            )
            log.info(f"Recording complete: {len(audio)} samples")
            return audio
        except asyncio.CancelledError:
            log.info("Recording cancelled")
            return None
        except JarvisAudioError as exc:
            log.error(f"Audio error: {exc}")
            return None

    async def _transcribe(self, audio: bytes) -> tuple[str, float] | None:
        """
        Transcribe recorded audio.
        
        Returns:
            Tuple of (text, confidence) or None if failed
        """
        if not audio or len(audio) == 0:
            log.warning("No audio to transcribe")
            return None
        
        try:
            log.info("Transcribing speech...")
            self._set_state(VoiceState.PROCESSING)
            
            # Emit "thinking" message
            event = VoiceEvent(
                event_type="voice_text",
                text=Phrases.get_thinking(),
            )
            self._emit_event(event)
            
            text, confidence = await self._stt.transcribe_async(audio)
            
            if not text:
                log.warning("STT returned empty text")
                return None
            
            log.info(f"Transcribed: '{text}' (confidence: {confidence:.2%})")
            
            # Emit transcribed text
            event = VoiceEvent(
                event_type="voice_text",
                text=text,
            )
            self._emit_event(event)
            
            return text, confidence
        
        except SpeechToTextError as exc:
            log.error(f"Transcription failed: {exc}")
            return None

    async def _process_command(self, text: str) -> str | None:
        """
        Process transcribed text through orchestrator.
        
        Returns:
            Response text or None if failed
        """
        try:
            log.info(f"Processing command: '{text}'")
            
            # Call orchestrator with source="voice"
            result = await self.orchestrator.process(
                input=text,
                source="voice",  # Mark as voice input
            )
            
            response = result.output if hasattr(result, 'output') else str(result)
            log.info(f"Orchestrator response: '{response[:100]}...'")
            
            return response
        
        except Exception as exc:
            log.error(f"Orchestrator error: {exc}")
            return None

    async def _speak_response(self, response: str) -> None:
        """Speak response via TTS."""
        try:
            if not response or not response.strip():
                log.warning("Empty response, skipping TTS")
                return
            
            self._set_state(VoiceState.SPEAKING)
            
            # Format for voice (short, no markdown)
            voice_text = abbreviate_response(
                response,
                max_length=VoiceConfig.MAX_RESPONSE_CHARS,
                max_sentences=VoiceConfig.MAX_RESPONSE_SENTENCES,
            )
            
            log.info(f"Speaking response: '{voice_text}'")
            
            # Emit response for frontend
            event = VoiceEvent(
                event_type="voice_response",
                text=voice_text,
            )
            self._emit_event(event)
            
            # Speak
            await self._tts.speak(voice_text)
            log.info("Response spoken")
        
        except TextToSpeechError as exc:
            log.error(f"TTS error: {exc}")
        except Exception as exc:
            log.error(f"Error speaking response: {exc}")

    async def _run_loop(self) -> None:
        """Main voice pipeline loop."""
        log.info("Voice pipeline running")
        
        try:
            # Start wake word detection
            self._wake.start()
            
            while self._running:
                try:
                    # ─────────────────────────────────────────────────────
                    # IDLE → Wait for wake word
                    # ─────────────────────────────────────────────────────
                    if self._state == VoiceState.IDLE:
                        await asyncio.sleep(0.1)
                        continue
                    
                    # ─────────────────────────────────────────────────────
                    # LISTENING → Record speech
                    # ─────────────────────────────────────────────────────
                    elif self._state == VoiceState.LISTENING:
                        audio = await self._record_command()
                        if not audio or len(audio) == 0:
                            log.warning("No audio recorded")
                            self._set_state(VoiceState.IDLE)
                            continue
                        
                        # Trim silence
                        audio = self._vad.trim_silence(audio)
                        
                        # ─────────────────────────────────────────────────────
                        # PROCESSING → STT + Orchestrator
                        # ─────────────────────────────────────────────────────
                        result = await self._transcribe(audio)
                        if not result:
                            log.warning("Transcription failed")
                            # Emit error
                            event = VoiceEvent(
                                event_type="voice_error",
                                error=Phrases.get_error_stt(),
                            )
                            self._emit_event(event)
                            
                            # Try to speak error
                            try:
                                await self._tts.speak(Phrases.get_error_stt())
                            except:
                                pass
                            
                            self._set_state(VoiceState.IDLE)
                            continue
                        
                        text, confidence = result
                        
                        # Process through orchestrator
                        response = await self._process_command(text)
                        if not response:
                            log.warning("Orchestrator returned empty response")
                            response = "Desculpe, não consegui processar o comando."
                        
                        # ─────────────────────────────────────────────────────
                        # SPEAKING → TTS
                        # ─────────────────────────────────────────────────────
                        await self._speak_response(response)
                        
                        # Back to IDLE
                        self._set_state(VoiceState.IDLE)
                    
                    # ─────────────────────────────────────────────────────
                    # ERROR → Log and reset
                    # ─────────────────────────────────────────────────────
                    elif self._state == VoiceState.ERROR:
                        await asyncio.sleep(1.0)
                        self._set_state(VoiceState.IDLE)
                
                except asyncio.CancelledError:
                    log.info("Voice loop cancelled")
                    break
                except Exception as exc:
                    log.error(f"Voice loop error: {exc}", exc_info=True)
                    self._set_state(VoiceState.ERROR)
                    await asyncio.sleep(1.0)
        
        finally:
            self._wake.stop()
            log.info("Voice pipeline stopped")

    async def start(self) -> None:
        """Start voice pipeline."""
        if self._running:
            log.warning("Voice pipeline already running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        log.info("Voice pipeline started")

    async def stop(self) -> None:
        """Stop voice pipeline."""
        if not self._running:
            return
        
        log.info("Stopping voice pipeline...")
        self._running = False
        
        # Try to speak goodbye
        try:
            await self._tts.speak(Phrases.get_goodbye())
        except:
            pass
        
        # Cancel task
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        log.info("Voice pipeline stopped")

    def is_running(self) -> bool:
        """Check if pipeline is running."""
        return self._running


# ──────────────────────────────────────────────────────────────────────────────
# Test entry point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    async def main():
        print("\n=== JARVIS Voice Pipeline Test ===\n")
        
        # Mock orchestrator
        class MockOrchestrator:
            async def process(self, input: str, source: str = "text") -> Any:
                from dataclasses import dataclass
                @dataclass
                class Result:
                    output: str
                
                return Result(output=f"You said: {input}")
        
        # Event callback
        def on_voice_event(event: VoiceEvent):
            print(f"[EVENT] {event.event_type}: {event.to_dict()}")
        
        # Create pipeline
        pipeline = VoicePipeline(
            orchestrator=MockOrchestrator(),
            event_callback=on_voice_event,
            user_id="test",
        )
        
        print("Starting voice pipeline...")
        print("Say 'JARVIS' to activate, then speak a command")
        print("Press Ctrl+C to stop\n")
        
        try:
            await pipeline.start()
            
            # Keep running
            while True:
                await asyncio.sleep(1.0)
        
        except KeyboardInterrupt:
            print("\n\nStopping...")
            await pipeline.stop()
            print("Done")
    
    asyncio.run(main())
