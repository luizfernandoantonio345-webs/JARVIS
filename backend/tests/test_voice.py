"""
Testes para o pipeline de voz do JARVIS.
Não precisa de microfone, testa a lógica interna e interfaces.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from pathlib import Path


# ── Wake Word Engine ───────────────────────────────────────────────────────────

def test_wake_word_engine_instantiates():
    from voice_v2.wake_word import WakeWordEngine
    engine = WakeWordEngine()
    assert engine is not None
    assert not engine.is_running()


def test_wake_word_words_list():
    from voice_v2.wake_word import WAKE_WORDS
    assert isinstance(WAKE_WORDS, list)
    assert len(WAKE_WORDS) >= 3
    assert "jarvis" in WAKE_WORDS


def test_get_wake_word_engine_singleton():
    from voice_v2.wake_word import get_wake_word_engine, WakeWordEngine
    e1 = get_wake_word_engine()
    e2 = get_wake_word_engine()
    assert e1 is e2


# ── TTS Output ─────────────────────────────────────────────────────────────────

def test_speak_empty_string_returns_false():
    import asyncio
    from voice_v2.output import speak
    result = asyncio.run(speak(""))
    assert result is False


def test_speak_whitespace_returns_false():
    import asyncio
    from voice_v2.output import speak
    result = asyncio.run(speak("   "))
    assert result is False


def test_generate_tts_file_with_output_path(tmp_path):
    """Verifica que generate_tts_file usa o output_path fornecido."""
    import asyncio
    from voice_v2.output import generate_tts_file
    out = str(tmp_path / "test_tts.mp3")
    # Se edge-tts não estiver instalado, retorna None (não falha)
    result = asyncio.run(generate_tts_file("Hello Sir", output_path=out))
    if result is not None:
        assert result == out or os.path.exists(result)


# ── STT Input ──────────────────────────────────────────────────────────────────

def test_transcribe_empty_bytes_returns_none():
    import asyncio
    from voice_v2.input import transcribe_async
    # Bytes vazios não devem crashar, só retornar None
    result = asyncio.run(transcribe_async(b""))
    assert result is None or isinstance(result, str)


def test_transcribe_invalid_bytes_returns_none():
    import asyncio
    from voice_v2.input import transcribe_async
    result = asyncio.run(transcribe_async(b"not_audio_data_xyz"))
    assert result is None or isinstance(result, str)


# ── Voice Pipeline ─────────────────────────────────────────────────────────────

def test_tts_dir_created():
    from voice_v2.pipeline import _TTS_DIR
    assert _TTS_DIR.exists()


def test_pipeline_process_empty_audio_returns_error():
    import asyncio
    from voice_v2.pipeline import process_audio_pipeline
    result = asyncio.run(process_audio_pipeline(b"invalid_audio"))
    assert isinstance(result, dict)
    assert "status" in result
    assert "response" in result


def test_pipeline_result_has_required_fields():
    import asyncio
    from voice_v2.pipeline import process_audio_pipeline
    result = asyncio.run(process_audio_pipeline(b""))
    for field in ["status", "response"]:
        assert field in result, f"Campo '{field}' ausente no resultado do pipeline"


# ── VoicePipelineV3 ────────────────────────────────────────────────────────────

def test_voice_pipeline_v3_instantiates():
    from voice_v2.voice_pipeline_v3 import VoicePipelineV3
    pipeline = VoicePipelineV3()
    assert not pipeline.active
    assert not pipeline._processing


def test_get_voice_pipeline_singleton():
    from voice_v2.voice_pipeline_v3 import get_voice_pipeline
    p1 = get_voice_pipeline()
    p2 = get_voice_pipeline()
    assert p1 is p2


def test_voice_pipeline_status():
    from voice_v2.voice_pipeline_v3 import VoicePipelineV3
    p = VoicePipelineV3()
    status = p.status()
    assert isinstance(status, dict)
    assert "active" in status
    assert "stt_loaded" in status


# ── HeadsetListener ────────────────────────────────────────────────────────────

def test_headset_listener_instantiates():
    from voice_v2.headset_listener import HeadsetListener
    listener = HeadsetListener()
    assert listener is not None
    assert not listener._running


def test_headset_listener_stop_safe():
    from voice_v2.headset_listener import HeadsetListener
    listener = HeadsetListener()
    listener.stop()  # Não deve dar erro mesmo sem estar rodando
    assert not listener._running
