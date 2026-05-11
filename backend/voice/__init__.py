"""
JARVIS Voice Engine — Complete voice subsystem for hands-free AI interaction.

Modules:
  - persona.py        : Personality, phrases, and voice configuration
  - audio_capture.py  : Microphone input streaming with noise handling
  - vad.py            : Voice Activity Detection (detects end of speech)
  - wake_word.py      : Wake word detection ("JARVIS" or custom)
  - stt.py            : Speech-to-Text transcription
  - tts.py            : Text-to-Speech voice responses
  - voice_pipeline.py : Main orchestrator loop

Usage:
  from backend.voice import VoicePipeline
  pipeline = VoicePipeline(orchestrator=my_orchestrator)
  await pipeline.start()
"""

from __future__ import annotations

from .persona import (
    JARVIS_NAME,
    JARVIS_LANG,
    JARVIS_USER_TITLE,
    Phrases,
    VoiceConfig,
    Personality,
    format_response,
    abbreviate_response,
)

__all__ = [
    "JARVIS_NAME",
    "JARVIS_LANG",
    "JARVIS_USER_TITLE",
    "Phrases",
    "VoiceConfig",
    "Personality",
    "format_response",
    "abbreviate_response",
]
