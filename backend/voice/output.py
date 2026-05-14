import logging
import asyncio
import tempfile
import os
import importlib
from pathlib import Path

import winsound  # Windows

log = logging.getLogger(__name__)

async def speak(text: str, voice: str = "pt-BR-FranciscaNeural") -> str:
    """Convert text to speech and play async. Returns temp audio path."""
    if not text.strip():
        log.warning("Empty text for TTS")
        return ""
    
    temp_path = tempfile.mktemp(suffix=".wav")
    try:
        edge_tts = importlib.import_module("edge_tts")
    except Exception as exc:
        log.warning("edge_tts unavailable; skipping TTS: %s", exc)
        return ""

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(temp_path)
    
    # Play async on Windows
    def _play():
        try:
            winsound.PlaySound(temp_path, winsound.SND_ASYNC | winsound.SND_FILENAME)
        except Exception as e:
            log.error("TTS playback failed: %s", e)
    
    asyncio.create_task(asyncio.to_thread(_play))
    
    log.info("Speaking: %s (voice=%s, path=%s)", text[:50] + "...", voice, temp_path)
    return temp_path

async def speak_silent(text: str, voice: str = "pt-BR-FranciscaNeural") -> str:
    """Save TTS without playing (for API response)."""
    temp_path = tempfile.mktemp(suffix=".wav")
    try:
        edge_tts = importlib.import_module("edge_tts")
    except Exception as exc:
        log.warning("edge_tts unavailable; skipping TTS save: %s", exc)
        return ""
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(temp_path)
    log.info("TTS saved: %s", temp_path)
    return temp_path
