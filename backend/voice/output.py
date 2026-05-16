import logging
import asyncio
import tempfile
import os
import importlib
from pathlib import Path

import winsound

log = logging.getLogger(__name__)

async def speak(text: str, voice: str = "pt-BR-FranciscaNeural") -> str:
    """Convert text to speech and play. Falls back to pyttsx3 if edge_tts fails."""
    if not text.strip():
        log.warning("Empty text for TTS")
        return ""

    clean = text[:300]
    for ch in ["**", "##", "```", "*", "_", "#"]:
        clean = clean.replace(ch, "")
    clean = clean.strip()

    if not clean:
        return ""

    temp_path = tempfile.mktemp(suffix=".wav")
    try:
        edge_tts = importlib.import_module("edge_tts")
        communicate = edge_tts.Communicate(clean, voice)
        await communicate.save(temp_path)

        def _play():
            try:
                winsound.PlaySound(temp_path, winsound.SND_ASYNC | winsound.SND_FILENAME)
            except Exception as e:
                log.error("TTS playback failed: %s", e)

        asyncio.create_task(asyncio.to_thread(_play))
        log.info("Speaking (edge_tts): %s", clean[:50])
        return temp_path

    except Exception as e:
        log.warning("edge_tts failed: %s — trying pyttsx3 fallback", e)
        try:
            pyttsx3 = importlib.import_module("pyttsx3")
            engine = pyttsx3.init()
            engine.setProperty("rate", 160)
            engine.setProperty("volume", 0.9)

            def _say():
                try:
                    engine.say(clean)
                    engine.runAndWait()
                except Exception as e2:
                    log.error("pyttsx3 playback failed: %s", e2)

            asyncio.create_task(asyncio.to_thread(_say))
            log.info("Speaking (pyttsx3): %s", clean[:50])
            return temp_path

        except Exception as e2:
            log.error("pyttsx3 also failed: %s", e2)
            return ""

async def speak_silent(text: str, voice: str = "pt-BR-FranciscaNeural") -> str:
    """Save TTS without playing (for API response)."""
    temp_path = tempfile.mktemp(suffix=".wav")
    try:
        edge_tts = importlib.import_module("edge_tts")
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(temp_path)
        log.info("TTS saved: %s", temp_path)
        return temp_path
    except Exception as e:
        log.warning("edge_tts save failed: %s", e)
        return ""
