"""STT input — transcrição de áudio via Whisper (faster-whisper ou openai-whisper)."""
import asyncio
import logging
import os
import tempfile

log = logging.getLogger(__name__)

_whisper_model = None
_whisper_type: str | None = None  # 'faster' | 'openai'


def _load_whisper():
    """Carrega o modelo Whisper (lazy, singleton)."""
    global _whisper_model, _whisper_type
    if _whisper_model is not None:
        return _whisper_model

    # Prefere faster-whisper (menor memória, mais rápido em CPU)
    try:
        from faster_whisper import WhisperModel
        model_dir = os.path.join(os.path.dirname(__file__), "..", "..", "models", "whisper")
        _whisper_model = WhisperModel(
            "small",
            device="cpu",
            compute_type="int8",
            download_root=model_dir,
        )
        _whisper_type = "faster"
        log.info("[STT] faster-whisper 'small' carregado")
        return _whisper_model
    except ImportError:
        pass
    except Exception as e:
        log.warning("[STT] faster-whisper falhou ao carregar: %s", e)

    # Fallback: openai-whisper
    try:
        import whisper
        _whisper_model = whisper.load_model("small")
        _whisper_type = "openai"
        log.info("[STT] openai-whisper 'small' carregado")
        return _whisper_model
    except ImportError:
        log.warning("[STT] Whisper não instalado. Execute: pip install faster-whisper")
        return None
    except Exception as e:
        log.warning("[STT] openai-whisper falhou ao carregar: %s", e)
        return None


def transcribe(audio_bytes: bytes, language: str = "pt") -> str | None:
    """Transcreve bytes de áudio para texto. Retorna None se STT indisponível."""
    model = _load_whisper()
    if model is None:
        return None

    tmp = tempfile.mktemp(suffix=".wav")
    try:
        with open(tmp, "wb") as f:
            f.write(audio_bytes)

        if _whisper_type == "faster":
            segments, _info = model.transcribe(
                tmp,
                language=language,
                beam_size=5,
                vad_filter=True,
            )
            text = " ".join(seg.text for seg in segments).strip()
        else:
            result = model.transcribe(tmp, language=language)
            text = result.get("text", "").strip()

        if text:
            log.info("[STT] Transcrito: %s", text[:120])
            return text
        return None
    except Exception as e:
        log.warning("[STT] Erro na transcrição: %s", e)
        return None
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass


async def transcribe_async(audio_bytes: bytes, language: str = "pt") -> str | None:
    """Versão assíncrona de transcribe (executa em thread pool)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, transcribe, audio_bytes, language)
