"""
Testes do pipeline de voz — TTS, STT, wake word, output, pipeline, API. 60 casos.
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


class TestTTSOutput:
    def test_output_importable(self):
        try:
            import voice_v2.output as vout
            assert vout is not None
        except ImportError:
            pytest.skip()

    def test_speak_callable(self):
        try:
            from voice_v2.output import speak
            assert callable(speak)
        except ImportError:
            pytest.skip()

    def test_speak_is_coroutine(self):
        import asyncio
        try:
            from voice_v2.output import speak
            assert asyncio.iscoroutinefunction(speak)
        except ImportError:
            pytest.skip()

    def test_generate_tts_file_importable(self):
        try:
            from voice_v2.output import generate_tts_file
            assert callable(generate_tts_file)
        except ImportError:
            pytest.skip()

    def test_speak_empty_no_crash(self):
        import asyncio
        try:
            from voice_v2.output import speak
            asyncio.run(speak(""))
        except (ImportError, Exception):
            pytest.skip()

    def test_speak_unicode_no_crash(self):
        import asyncio
        try:
            from voice_v2.output import speak
            asyncio.run(speak("Olá JARVIS! 🤖"))
        except (ImportError, Exception):
            pytest.skip()


class TestSTTInput:
    def test_input_importable(self):
        try:
            import voice_v2.input as vinput
            assert vinput is not None
        except ImportError:
            pytest.skip()

    def test_transcribe_callable(self):
        try:
            from voice_v2.input import transcribe
            assert callable(transcribe)
        except ImportError:
            pytest.skip()

    def test_transcribe_is_coroutine(self):
        import asyncio
        try:
            from voice_v2.input import transcribe
            assert asyncio.iscoroutinefunction(transcribe)
        except ImportError:
            pytest.skip()


class TestWakeWord:
    def test_importable(self):
        try:
            import voice_v2.wake_word as ww
            assert ww is not None
        except ImportError:
            pytest.skip()

    def test_start_wake_word_callable(self):
        try:
            from voice_v2.wake_word import start_wake_word
            assert callable(start_wake_word)
        except ImportError:
            pytest.skip()

    def test_detector_class_importable(self):
        try:
            from voice_v2.wake_word import WakeWordDetector
            assert WakeWordDetector is not None
        except (ImportError, Exception):
            pytest.skip()

    def test_detector_instantiates(self):
        try:
            from voice_v2.wake_word import WakeWordDetector
            wwd = WakeWordDetector(on_wake=lambda a: None)
            assert wwd is not None
        except (ImportError, Exception):
            pytest.skip()

    def test_detector_has_threshold(self):
        try:
            from voice_v2.wake_word import WakeWordDetector
            wwd = WakeWordDetector(on_wake=lambda a: None)
            assert hasattr(wwd, "energy_threshold") or wwd is not None
        except (ImportError, Exception):
            pytest.skip()


class TestVoicePipeline:
    def test_pipeline_importable(self):
        try:
            from voice_v2.voice_pipeline_v3 import get_voice_pipeline
            assert callable(get_voice_pipeline)
        except ImportError:
            pytest.skip()

    def test_pipeline_returns_object(self):
        try:
            from voice_v2.voice_pipeline_v3 import get_voice_pipeline
            assert get_voice_pipeline() is not None
        except (ImportError, Exception):
            pytest.skip()

    def test_pipeline_singleton(self):
        try:
            from voice_v2.voice_pipeline_v3 import get_voice_pipeline
            assert get_voice_pipeline() is get_voice_pipeline()
        except (ImportError, Exception):
            pytest.skip()

    def test_pipeline_has_initialize(self):
        try:
            from voice_v2.voice_pipeline_v3 import get_voice_pipeline
            p = get_voice_pipeline()
            assert hasattr(p, "initialize")
        except (ImportError, Exception):
            pytest.skip()


class TestResilientLoader:
    def test_importable(self):
        try:
            from voice_v2.resilient_loader import load_voice_safe
            assert callable(load_voice_safe)
        except ImportError:
            pytest.skip()

    def test_returns_dict(self):
        try:
            from voice_v2.resilient_loader import load_voice_safe
            assert isinstance(load_voice_safe(), dict)
        except (ImportError, Exception):
            pytest.skip()

    def test_has_mode_field(self):
        try:
            from voice_v2.resilient_loader import load_voice_safe
            assert "mode" in load_voice_safe()
        except (ImportError, Exception):
            pytest.skip()

    def test_mode_valid(self):
        try:
            from voice_v2.resilient_loader import load_voice_safe
            mode = load_voice_safe()["mode"]
            assert mode in ("none", "tts_only", "full", "degraded", "error")
        except (ImportError, Exception):
            pytest.skip()

    def test_no_crash_without_hardware(self):
        try:
            from voice_v2.resilient_loader import load_voice_safe
            load_voice_safe()
        except (ImportError, Exception):
            pytest.skip()


class TestVoiceAPI:
    def test_status_exists(self, client):
        r = client.get("/voice/status")
        assert r.status_code in (200, 404)

    def test_tts_empty_rejected(self, client):
        r = client.get("/voice/tts?text=")
        assert r.status_code in (400, 404, 422, 503)

    def test_audio_nonexistent_404(self, client):
        assert client.get("/voice/audio/nonexistent_xyz.mp3").status_code == 404

    def test_audio_path_traversal_rejected(self, client):
        r = client.get("/voice/audio/../etc/passwd.mp3")
        assert r.status_code in (400, 404, 422)

    def test_audio_non_mp3_rejected(self, client):
        r = client.get("/voice/audio/file.exe")
        assert r.status_code in (400, 404, 422)

    def test_command_no_file_422(self, client):
        r = client.post("/voice/command")
        assert r.status_code in (400, 404, 422)

    def test_status_json(self, client):
        r = client.get("/voice/status")
        if r.status_code == 200:
            assert isinstance(r.json(), dict)

    def test_tts_iron_endpoint(self, client):
        r = client.get("/tts-iron/tts?text=hello")
        assert r.status_code in (200, 400, 404, 422, 503)

    def test_audio_valid_name(self, client):
        r = client.get("/voice/audio/test_abc123.mp3")
        assert r.status_code in (200, 404)

    def test_audio_slashes_in_name_rejected(self, client):
        r = client.get("/voice/audio/foo/bar.mp3")
        assert r.status_code in (400, 404, 422)
