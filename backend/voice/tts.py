"""
Text-to-Speech Module — Converts text to voice using edge-tts or pyttsx3.

Primary: edge-tts (Microsoft neural voices, free, requires internet)
Fallback: pyttsx3 (offline, local, limited voice quality)

Features:
- Non-blocking async speech
- Interrupts previous speech
- Configurable voice, rate, pitch, volume
- Graceful fallback if TTS unavailable
"""

from __future__ import annotations

import asyncio
import logging
import io
import tempfile
from pathlib import Path
from typing import Optional

from .persona import VoiceConfig, Phrases

log = logging.getLogger(__name__)

try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False
    log.warning("edge-tts not installed")

try:
    import pyttsx3
    HAS_PYTTSX3 = True
except ImportError:
    HAS_PYTTSX3 = False
    log.warning("pyttsx3 not installed")

try:
    import sounddevice as sd
    import soundfile as sf
    HAS_AUDIO = True
except ImportError:
    HAS_AUDIO = False
    log.warning("sounddevice/soundfile not installed")


class TextToSpeechError(Exception):
    """Raised on TTS errors."""
    pass


class TextToSpeech:
    """
    Converts text to speech and plays it.
    
    Uses edge-tts (neural voices) or pyttsx3 (local) as fallback.
    """

    def __init__(
        self,
        engine: str = VoiceConfig.TTS_ENGINE,
        voice: Optional[str] = None,
        rate: str = VoiceConfig.TTS_RATE,
        pitch: str = VoiceConfig.TTS_PITCH,
        volume: str = VoiceConfig.TTS_VOLUME,
        sample_rate: int = 16000,
    ) -> None:
        """
        Initialize TTS engine.
        
        Args:
            engine: "edge-tts" or "pyttsx3"
            voice: Voice name (e.g., "pt-BR-AntonioNeural")
            rate: Rate adjustment (e.g., "+0%", "+10%")
            pitch: Pitch adjustment (e.g., "-10Hz")
            volume: Volume adjustment (e.g., "+0%")
            sample_rate: Output sample rate
        """
        self.engine_pref = engine
        self.voice = voice or VoiceConfig.get_tts_voice()
        self.rate = rate
        self.pitch = pitch
        self.volume = volume
        self.sample_rate = sample_rate
        
        self._pyttsx3_engine = None
        self._current_task: Optional[asyncio.Task] = None
        
        log.info(
            f"TextToSpeech initialized: engine={engine}, voice={self.voice}, "
            f"rate={rate}, pitch={pitch}"
        )

    def _init_pyttsx3(self) -> bool:
        """Initialize pyttsx3 engine."""
        if not HAS_PYTTSX3:
            return False
        
        try:
            if self._pyttsx3_engine is None:
                self._pyttsx3_engine = pyttsx3.init()
                
                # Set voice
                voices = self._pyttsx3_engine.getProperty("voices")
                if voices:
                    self._pyttsx3_engine.setProperty("voice", voices[0].id)
                
                # Set rate
                try:
                    rate_val = int(self.rate.rstrip("%"))
                    self._pyttsx3_engine.setProperty("rate", 150 + rate_val)
                except:
                    self._pyttsx3_engine.setProperty("rate", 150)
                
                # Set volume
                try:
                    vol_val = int(self.volume.rstrip("%")) / 100.0
                    self._pyttsx3_engine.setProperty("volume", 0.5 + vol_val)
                except:
                    self._pyttsx3_engine.setProperty("volume", 0.5)
            
            return True
        except Exception as exc:
            log.error(f"Failed to initialize pyttsx3: {exc}")
            return False

    async def speak(self, text: str) -> None:
        """
        Speak text using TTS.
        
        Args:
            text: Text to speak
        
        Raises:
            TextToSpeechError: If speech fails
        """
        if not text or not text.strip():
            log.debug("Empty text, skipping TTS")
            return
        
        # Cancel previous speech
        if self._current_task and not self._current_task.done():
            log.debug("Interrupting previous speech")
            self._current_task.cancel()
        
        # Create new speech task
        try:
            self._current_task = asyncio.create_task(self._speak_async(text))
            await self._current_task
        except asyncio.CancelledError:
            log.debug("Speech cancelled")
        except Exception as exc:
            log.error(f"Speech error: {exc}")
            raise TextToSpeechError(f"Speech failed: {exc}")

    async def _speak_async(self, text: str) -> None:
        """Internal async speech implementation."""
        loop = asyncio.get_event_loop()
        
        # Try edge-tts first (neural voices)
        if self.engine_pref == "edge-tts" and HAS_EDGE_TTS:
            try:
                await self._speak_edge_tts(text, loop)
                return
            except Exception as exc:
                log.warning(f"edge-tts failed: {exc}, falling back to pyttsx3")
        
        # Fallback to pyttsx3
        if HAS_PYTTSX3 and self._init_pyttsx3():
            try:
                await loop.run_in_executor(None, self._speak_pyttsx3, text)
                return
            except Exception as exc:
                log.error(f"pyttsx3 also failed: {exc}")
                raise TextToSpeechError("All TTS engines failed")
        
        # No engine available
        log.error("No TTS engine available (edge-tts and pyttsx3 both unavailable)")
        raise TextToSpeechError("No TTS engine available")

    async def _speak_edge_tts(self, text: str, loop: asyncio.AbstractEventLoop) -> None:
        """Use edge-tts (neural Microsoft voices)."""
        if not HAS_EDGE_TTS:
            raise TextToSpeechError("edge-tts not available")
        
        log.info(f"Speaking with edge-tts: '{text[:50]}...'")
        
        try:
            # Generate speech
            communicate = edge_tts.Communicate(
                text=text,
                voice=self.voice,
                rate=self.rate,
                pitch=self.pitch,
                volume=self.volume,
            )
            
            # Save to temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        tmp.write(chunk["data"])
                tmp_path = tmp.name
            
            # Play audio
            if HAS_AUDIO:
                await loop.run_in_executor(None, self._play_audio_file, tmp_path)
            
            # Cleanup
            Path(tmp_path).unlink(missing_ok=True)
        
        except Exception as exc:
            log.error(f"edge-tts error: {exc}")
            raise

    def _speak_pyttsx3(self, text: str) -> None:
        """Use pyttsx3 (offline, local voices)."""
        if not self._init_pyttsx3():
            raise TextToSpeechError("pyttsx3 not available")
        
        log.info(f"Speaking with pyttsx3: '{text[:50]}...'")
        
        try:
            self._pyttsx3_engine.say(text)
            self._pyttsx3_engine.runAndWait()
        except Exception as exc:
            log.error(f"pyttsx3 error: {exc}")
            raise

    def _play_audio_file(self, file_path: str, sample_rate: int = 16000) -> None:
        """Play audio file using sounddevice."""
        if not HAS_AUDIO:
            log.warning("Cannot play audio: sounddevice not installed")
            return
        
        try:
            import soundfile as sf
            data, sr = sf.read(file_path)
            sd.play(data, sr)
            sd.wait()
        except Exception as exc:
            log.error(f"Audio playback error: {exc}")

    async def speak_file(self, text: str, output_path: Path | str) -> None:
        """
        Generate speech and save to file without playing.
        
        Args:
            text: Text to speak
            output_path: Path to save audio (.mp3 for edge-tts, .wav for pyttsx3)
        """
        output_path = Path(output_path)
        
        if self.engine_pref == "edge-tts" and HAS_EDGE_TTS:
            try:
                await self._save_edge_tts(text, output_path)
                return
            except Exception as exc:
                log.warning(f"edge-tts save failed: {exc}")
        
        if HAS_PYTTSX3 and self._init_pyttsx3():
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda: self._pyttsx3_engine.save_to_file(text, str(output_path))
                )
                return
            except Exception as exc:
                log.error(f"pyttsx3 save failed: {exc}")

    async def _save_edge_tts(self, text: str, output_path: Path) -> None:
        """Save edge-tts output to file."""
        if not HAS_EDGE_TTS:
            raise TextToSpeechError("edge-tts not available")
        
        log.info(f"Saving speech to {output_path}")
        
        communicate = edge_tts.Communicate(
            text=text,
            voice=self.voice,
            rate=self.rate,
            pitch=self.pitch,
            volume=self.volume,
        )
        
        with open(output_path, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
        
        log.info(f"Speech saved: {output_path}")

    def get_available_voices(self) -> list[str]:
        """Get list of available voices (for edge-tts, returns common ones)."""
        # Common neural voices
        voices = [
            # Portuguese
            "pt-BR-AntonioNeural",
            "pt-BR-FranciscaNeural",
            # English
            "en-US-GuyNeural",
            "en-US-JennyNeural",
            "en-GB-RyanNeural",
            "en-GB-SoniaNeural",
        ]
        return voices


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
        print("\n=== JARVIS Text-to-Speech Test ===\n")
        
        # Test 1: List voices
        print("Test 1: Available voices")
        tts = TextToSpeech()
        voices = tts.get_available_voices()
        for voice in voices[:5]:
            print(f"  - {voice}")
        print()
        
        # Test 2: Generate speech (edge-tts, with fallback)
        print("Test 2: Generate speech")
        try:
            test_texts = [
                "Olá, eu sou o JARVIS.",
                "Hello, I am JARVIS.",
            ]
            
            for text in test_texts:
                print(f"  Speaking: '{text}'")
                await tts.speak(text)
                await asyncio.sleep(1.0)
        
        except Exception as exc:
            print(f"  Speech error: {exc}")
        
        print("\nTest complete")
    
    asyncio.run(main())
