"""
Resilient Voice Loader - checks dependencies without crashing on missing packages.
Gracefully degrades functionality based on what's installed.
"""

import subprocess
import sys
import logging
from dataclasses import dataclass
from typing import List, Optional

log = logging.getLogger(__name__)


@dataclass
class VoiceCapability:
    """Voice system capability flags."""
    stt_available: bool          # faster_whisper installed
    tts_available: bool          # edge_tts installed
    audio_available: bool        # sounddevice installed
    ffmpeg_available: bool       # ffmpeg in PATH
    wake_word_available: bool    # openwakeword installed


def _check_import(module_name: str, package_name: Optional[str] = None) -> bool:
    """
    Check if a module can be imported.
    
    Args:
        module_name: The module name to import
        package_name: The pip package name (if different from module_name)
    
    Returns:
        True if module is available, False otherwise
    """
    try:
        # Usar subprocess para checar módulos C-extension pesados (evita forrtl crash)
        if module_name in ("faster_whisper", "sounddevice", "openwakeword"):
            result = subprocess.run(
                [sys.executable, "-c", f"import {module_name}"],
                capture_output=True,
                timeout=30,
            )
            return result.returncode == 0
        __import__(module_name)
        return True
    except ImportError:
        return False


def _check_ffmpeg() -> bool:
    """
    Check if ffmpeg is available in PATH.
    
    Returns:
        True if ffmpeg command exists, False otherwise
    """
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return False


def check_voice_capabilities() -> VoiceCapability:
    """
    Check which voice components are available.
    
    This function NEVER raises exceptions. It always returns a VoiceCapability
    object with the status of each component.
    
    Returns:
        VoiceCapability object with all flags set based on actual availability
    """
    log.info("[VOICE] Checking voice capabilities...")
    
    # Check STT (faster_whisper)
    stt_ok = _check_import("faster_whisper")
    log.info(f"  STT (faster_whisper): {'✓' if stt_ok else '✗'}")
    
    # Check TTS (edge_tts)
    tts_ok = _check_import("edge_tts")
    log.info(f"  TTS (edge_tts): {'✓' if tts_ok else '✗'}")
    
    # Check audio (sounddevice)
    audio_ok = _check_import("sounddevice")
    log.info(f"  Audio (sounddevice): {'✓' if audio_ok else '✗'}")
    
    # Check ffmpeg
    ffmpeg_ok = _check_ffmpeg()
    log.info(f"  FFmpeg: {'✓' if ffmpeg_ok else '✗'}")
    
    # Check wake word (openwakeword)
    wake_ok = _check_import("openwakeword")
    log.info(f"  Wake word (openwakeword): {'✓' if wake_ok else '✗'}")
    
    return VoiceCapability(
        stt_available=stt_ok,
        tts_available=tts_ok,
        audio_available=audio_ok,
        ffmpeg_available=ffmpeg_ok,
        wake_word_available=wake_ok,
    )


def load_voice_safe() -> dict:
    """
    Load voice system safely, determining supported mode based on available deps.
    
    This function NEVER raises an exception. It always returns a dict with:
    - loaded (bool): Whether any voice capability is available
    - capabilities (VoiceCapability): Detailed capability flags
    - mode (str): One of 'none', 'tts_only', 'stt_only', 'full'
    - missing (List[str]): List of pip packages to install for full functionality
    
    Returns:
        dict with voice system load results
    """
    try:
        caps = check_voice_capabilities()
    except Exception as e:
        log.error(f"[VOICE] Failed to check capabilities: {e}")
        return {
            "loaded": False,
            "capabilities": VoiceCapability(False, False, False, False, False),
            "mode": "none",
            "missing": ["edge-tts", "faster-whisper", "sounddevice", "openwakeword"],
        }
    
    # Determine mode based on capabilities
    mode = "none"
    missing = []
    loaded = False
    
    if not caps.tts_available:
        missing.append("edge-tts")
    
    if not caps.stt_available:
        missing.append("faster-whisper")
    
    if not caps.audio_available:
        missing.append("sounddevice")
    
    if not caps.ffmpeg_available:
        missing.append("ffmpeg")  # User needs to install manually
    
    if not caps.wake_word_available:
        missing.append("openwakeword")
    
    # Determine supported mode
    if caps.tts_available and caps.stt_available and caps.audio_available:
        mode = "full"
        loaded = True
        log.info("[VOICE] Full voice mode enabled (STT + TTS + Audio)")
    elif caps.tts_available:
        mode = "tts_only"
        loaded = True
        log.info("[VOICE] TTS-only mode (JARVIS can speak but not listen)")
    elif caps.stt_available and caps.audio_available:
        mode = "stt_only"
        loaded = True
        log.info("[VOICE] STT-only mode (JARVIS can listen but not speak)")
    else:
        mode = "none"
        loaded = False
        log.warning("[VOICE] No voice capabilities available")
    
    # Log missing packages
    if missing:
        log.warning(f"[VOICE] Missing packages: {', '.join(missing)}")
        log.info(f"[VOICE] Install with: pip install {' '.join(missing)}")
    
    result = {
        "loaded": loaded,
        "capabilities": caps,
        "mode": mode,
        "missing": missing,
    }
    
    return result


def get_voice_config():
    """
    Get voice configuration for the system.
    
    Returns a dictionary that can be passed to voice components.
    """
    result = load_voice_safe()
    return {
        "mode": result["mode"],
        "enabled": result["loaded"],
        "capabilities": {
            "stt": result["capabilities"].stt_available,
            "tts": result["capabilities"].tts_available,
            "audio": result["capabilities"].audio_available,
            "ffmpeg": result["capabilities"].ffmpeg_available,
            "wake_word": result["capabilities"].wake_word_available,
        },
    }


__all__ = [
    "VoiceCapability",
    "check_voice_capabilities",
    "load_voice_safe",
    "get_voice_config",
]
