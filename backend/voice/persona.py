"""
JARVIS Persona — Personality constants and frases for voice responses.

Defines the personality, tone, and scripted responses for JARVIS voice engine.
All responses are configurable via .env variables (JARVIS_LANG, JARVIS_USER_TITLE, etc).

Language support:
  - "pt-BR" → Portuguese (Brazilian)
  - "en-US" → English (US)

This module ensures JARVIS sounds consistent, confident, and professional.
"""

from __future__ import annotations

import os
import re
from enum import Enum
from typing import Final

# ── Configuration from environment ──────────────────────────────────────────────

JARVIS_NAME: Final[str] = os.getenv("JARVIS_NAME", "JARVIS")
JARVIS_LANG: Final[str] = os.getenv("JARVIS_LANG", "pt-BR")  # "pt-BR" or "en-US"
JARVIS_USER_TITLE: Final[str] = os.getenv("JARVIS_USER_TITLE", "Senhor")  # "Senhor" or "Sir"
JARVIS_VOICE_GENDER: Final[str] = os.getenv("JARVIS_VOICE_GENDER", "male")  # "male" or "female"


# ── Language enum ───────────────────────────────────────────────────────────────

class Language(Enum):
    """Supported languages."""
    PT_BR = "pt-BR"
    EN_US = "en-US"


def _get_lang() -> Language:
    """Get current language from JARVIS_LANG env var."""
    try:
        return Language(JARVIS_LANG)
    except ValueError:
        return Language.PT_BR  # fallback


# ── Scripted responses (multilingual) ────────────────────────────────────────────

class Phrases:
    """All voice phrases for JARVIS, organized by language."""

    READY_PT_BR = f"Ouvindo, {JARVIS_USER_TITLE}."
    READY_EN_US = f"Listening, {JARVIS_USER_TITLE}."

    THINKING_PT_BR = f"Processando, {JARVIS_USER_TITLE}."
    THINKING_EN_US = f"Processing, {JARVIS_USER_TITLE}."

    ERROR_STT_PT_BR = f"Não entendi, {JARVIS_USER_TITLE}. Pode repetir?"
    ERROR_STT_EN_US = f"Pardon, {JARVIS_USER_TITLE}?"

    ERROR_SYSTEM_PT_BR = "Ocorreu uma falha no sistema. Tentando recuperar."
    ERROR_SYSTEM_EN_US = "System failure detected. Attempting recovery."

    GOODBYE_PT_BR = f"Sistema encerrado. Até logo, {JARVIS_USER_TITLE}."
    GOODBYE_EN_US = f"Shutting down. Goodbye, {JARVIS_USER_TITLE}."

    CONFIRM_DESTRUCTIVE_PT_BR = f"Confirma {{action}}, {JARVIS_USER_TITLE}? Responda sim ou não."
    CONFIRM_DESTRUCTIVE_EN_US = f"Confirm {{action}}, {JARVIS_USER_TITLE}? Answer yes or no."

    WAKE_DETECTED_PT_BR = f"{JARVIS_NAME} ativado."
    WAKE_DETECTED_EN_US = f"{JARVIS_NAME} activated."

    MIC_TEST_PASS_PT_BR = "Microfone funcionando corretamente."
    MIC_TEST_PASS_EN_US = "Microphone working correctly."

    MIC_TEST_FAIL_PT_BR = "Falha ao testar microfone. Verifique a conexão."
    MIC_TEST_FAIL_EN_US = "Microphone test failed. Check your connection."

    NO_AUDIO_DEVICE_PT_BR = "Nenhum dispositivo de áudio encontrado."
    NO_AUDIO_DEVICE_EN_US = "No audio device found."

    @staticmethod
    def get_ready() -> str:
        """Get 'ready to listen' phrase."""
        lang = _get_lang()
        return Phrases.READY_PT_BR if lang == Language.PT_BR else Phrases.READY_EN_US

    @staticmethod
    def get_thinking() -> str:
        """Get 'processing' phrase."""
        lang = _get_lang()
        return Phrases.THINKING_PT_BR if lang == Language.PT_BR else Phrases.THINKING_EN_US

    @staticmethod
    def get_error_stt() -> str:
        """Get STT error phrase (didn't understand)."""
        lang = _get_lang()
        return Phrases.ERROR_STT_PT_BR if lang == Language.PT_BR else Phrases.ERROR_STT_EN_US

    @staticmethod
    def get_error_system() -> str:
        """Get system error phrase."""
        lang = _get_lang()
        return Phrases.ERROR_SYSTEM_PT_BR if lang == Language.PT_BR else Phrases.ERROR_SYSTEM_EN_US

    @staticmethod
    def get_goodbye() -> str:
        """Get goodbye/shutdown phrase."""
        lang = _get_lang()
        return Phrases.GOODBYE_PT_BR if lang == Language.PT_BR else Phrases.GOODBYE_EN_US

    @staticmethod
    def get_confirm_destructive(action: str) -> str:
        """Get confirmation prompt for destructive actions."""
        lang = _get_lang()
        template = (
            Phrases.CONFIRM_DESTRUCTIVE_PT_BR
            if lang == Language.PT_BR
            else Phrases.CONFIRM_DESTRUCTIVE_EN_US
        )
        return template.format(action=action)

    @staticmethod
    def get_wake_detected() -> str:
        """Get wake word detected acknowledgment."""
        lang = _get_lang()
        return Phrases.WAKE_DETECTED_PT_BR if lang == Language.PT_BR else Phrases.WAKE_DETECTED_EN_US

    @staticmethod
    def get_mic_test_pass() -> str:
        """Get microphone test pass message."""
        lang = _get_lang()
        return Phrases.MIC_TEST_PASS_PT_BR if lang == Language.PT_BR else Phrases.MIC_TEST_PASS_EN_US

    @staticmethod
    def get_mic_test_fail() -> str:
        """Get microphone test fail message."""
        lang = _get_lang()
        return Phrases.MIC_TEST_FAIL_PT_BR if lang == Language.PT_BR else Phrases.MIC_TEST_FAIL_EN_US

    @staticmethod
    def get_no_audio_device() -> str:
        """Get 'no audio device' error message."""
        lang = _get_lang()
        return Phrases.NO_AUDIO_DEVICE_PT_BR if lang == Language.PT_BR else Phrases.NO_AUDIO_DEVICE_EN_US


# ── Text processing for voice output ────────────────────────────────────────────

def format_response(text: str, max_sentences: int = 3) -> str:
    """
    Format text for voice output.
    
    - Ensures starts with uppercase, ends with period
    - Replaces technical terms with spoken forms
    - Limits to max_sentences (rest goes to silent text)
    - Removes markdown formatting
    
    Args:
        text: Raw response text
        max_sentences: Max sentences to speak (default 3)
    
    Returns:
        Formatted text suitable for TTS
    """
    # Remove markdown formatting
    text = re.sub(r"[*_`#]", "", text)  # Remove *, _, `, #
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # Remove [text](url)
    text = re.sub(r"```[a-z]*\n?", "", text)  # Remove code blocks
    text = text.replace("\n\n", ". ")  # Replace double newlines with period+space
    text = text.replace("\n", " ")  # Replace single newlines with space

    # Replace technical abbreviations with spoken forms
    replacements = {
        r"\bAPI\b": "A P I",
        r"\bJSON\b": "JSON",
        r"\bJSON\b": "Jason",
        r"\bHTML\b": "H T M L",
        r"\bCSS\b": "C S S",
        r"\bURL\b": "U R L",
        r"\bIP\b": "I P",
        r"\bHTTP\b": "H T T P",
        r"\bHTTPS\b": "H T T P S",
        r"\bSSH\b": "S S H",
        r"\bFTP\b": "F T P",
        r"\bSQL\b": "S Q L",
        r"\bPython\b": "Python",
        r"\bJavaScript\b": "Java Script",
        r"\bTypeScript\b": "Type Script",
        r"\bGitHub\b": "GitHub",
        r"\bGit\b": "Git",
        r"\bDocker\b": "Docker",
        r"\bKubernetes\b": "Kubernetes",
    }
    
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # Capitalize first letter
    text = text.strip()
    if text:
        text = text[0].upper() + text[1:]

    # Ensure ends with period
    if text and text[-1] not in ".!?":
        text += "."

    # Limit to max_sentences
    sentences = re.split(r"(?<=[.!?])\s+", text)
    if len(sentences) > max_sentences:
        spoken = ". ".join(sentences[:max_sentences])
        if not spoken.endswith((".", "!", "?")):
            spoken += "."
        return spoken

    return text


def abbreviate_response(text: str, max_length: int = 500, max_sentences: int = 3) -> str:
    """
    Abbreviate response to max_length characters and max_sentences.
    Useful for voice output (we want short, concise answers).
    
    Args:
        text: Full response text
        max_length: Maximum characters
        max_sentences: Maximum sentences
    
    Returns:
        Abbreviated text
    """
    text = format_response(text, max_sentences)
    
    if len(text) > max_length:
        text = text[:max_length].rsplit(" ", 1)[0] + "."
    
    return text


# ── Voice configuration ──────────────────────────────────────────────────────────

class VoiceConfig:
    """Configuration for voice engine (TTS, STT, VAD, wake word)."""

    # Language and voice selection
    LANGUAGE: Final[str] = JARVIS_LANG
    VOICE_GENDER: Final[str] = JARVIS_VOICE_GENDER

    # TTS (Text-to-Speech) configuration
    TTS_ENGINE: Final[str] = os.getenv("JARVIS_TTS_ENGINE", "edge-tts")  # "edge-tts" or "pyttsx3"
    TTS_VOICE_PT_BR: Final[str] = os.getenv("JARVIS_TTS_VOICE_PT_BR", "pt-BR-AntonioNeural")
    TTS_VOICE_EN_US: Final[str] = os.getenv("JARVIS_TTS_VOICE_EN_US", "en-US-GuyNeural")
    TTS_RATE: Final[str] = os.getenv("JARVIS_TTS_RATE", "+0%")  # "+10%" faster, "-10%" slower
    TTS_PITCH: Final[str] = os.getenv("JARVIS_TTS_PITCH", "-10Hz")  # More grave
    TTS_VOLUME: Final[str] = os.getenv("JARVIS_TTS_VOLUME", "+0%")

    # STT (Speech-to-Text) configuration
    STT_ENGINE: Final[str] = os.getenv("JARVIS_STT_ENGINE", "faster-whisper")  # "faster-whisper" or "whisper"
    STT_MODEL_SIZE: Final[str] = os.getenv("JARVIS_STT_MODEL_SIZE", "small")  # "tiny", "small", "medium", "large"
    STT_DEVICE: Final[str] = os.getenv("JARVIS_STT_DEVICE", "cpu")  # "cpu" or "cuda"
    STT_LANGUAGE: Final[str] = JARVIS_LANG.split("-")[0]  # "pt" or "en"

    # VAD (Voice Activity Detection) configuration
    VAD_ENGINE: Final[str] = os.getenv("JARVIS_VAD_ENGINE", "silero-vad")
    VAD_THRESHOLD: Final[float] = float(os.getenv("JARVIS_VAD_THRESHOLD", "0.5"))
    VAD_MIN_SILENCE_MS: Final[int] = int(os.getenv("JARVIS_VAD_MIN_SILENCE_MS", "800"))

    # Wake word detection configuration
    WAKE_WORD: Final[str] = os.getenv("JARVIS_WAKE_WORD", "jarvis")
    WAKE_THRESHOLD: Final[float] = float(os.getenv("JARVIS_WAKE_THRESHOLD", "0.7"))
    WAKE_MODEL: Final[str] = os.getenv("JARVIS_WAKE_MODEL", "hey_jarvis")  # openWakeWord model name

    # Audio capture configuration
    SAMPLE_RATE: Final[int] = 16000  # Whisper standard
    CHANNELS: Final[int] = 1
    CHUNK_DURATION_MS: Final[int] = 80
    MAX_RECORD_SECONDS: Final[int] = 10
    MICROPHONE_INDEX: Final[int | None] = None  # None = system default

    # Timeouts and thresholds
    STT_TIMEOUT_SECONDS: Final[int] = 30
    TTS_TIMEOUT_SECONDS: Final[int] = 60
    RECORDING_SILENCE_TIMEOUT_SECONDS: Final[int] = 8

    # Response limits for voice
    MAX_RESPONSE_CHARS: Final[int] = 500
    MAX_RESPONSE_SENTENCES: Final[int] = 3

    @staticmethod
    def get_tts_voice() -> str:
        """Get appropriate TTS voice based on language."""
        lang = _get_lang()
        if lang == Language.PT_BR:
            return VoiceConfig.TTS_VOICE_PT_BR
        else:
            return VoiceConfig.TTS_VOICE_EN_US


# ── Personality tone ────────────────────────────────────────────────────────────

class Personality:
    """JARVIS personality traits and behavior constants."""

    # Tone: confident, professional, helpful
    TONE = "Confident, professional, and helpful"

    # Never hesitant or uncertain
    NEVER_APOLOGIZE = True
    NEVER_HEDGE = True  # No "maybe", "possibly", "I think"

    # Always confirm destructive actions
    CONFIRM_DESTRUCTIVE_ACTIONS = True

    # Response style: short first, details if asked
    SHORT_FIRST_LONG_SECOND = True

    # Politeness level: formal ("Senhor"), never casual
    POLITENESS_LEVEL = "formal"

    # Proactive announcements
    ANNOUNCE_LISTENING = True  # Say "Ouvindo, Senhor" when listening
    ANNOUNCE_PROCESSING = True  # Say "Processando, Senhor" while processing
    ANNOUNCE_ERRORS = True  # Clearly state when something fails

    # Address user by title
    USE_USER_TITLE = True
    USER_TITLE = JARVIS_USER_TITLE


if __name__ == "__main__":
    # Test output
    print(f"JARVIS Persona Configuration")
    print(f"Name: {JARVIS_NAME}")
    print(f"Language: {JARVIS_LANG}")
    print(f"User Title: {JARVIS_USER_TITLE}")
    print()
    print("Sample Phrases:")
    print(f"  Ready: {Phrases.get_ready()}")
    print(f"  Thinking: {Phrases.get_thinking()}")
    print(f"  Error STT: {Phrases.get_error_stt()}")
    print(f"  Goodbye: {Phrases.get_goodbye()}")
    print()
    print("Format Response Examples:")
    test_text = "This is a **bold** text with #markdown and `code` that should be removed."
    print(f"  Input: {test_text}")
    print(f"  Output: {format_response(test_text)}")
    print()
    long_text = "This is the first sentence. This is the second sentence. This is the third sentence. This is the fourth sentence that should be cut off."
    print(f"  Input: {long_text}")
    print(f"  Output: {format_response(long_text, max_sentences=3)}")
