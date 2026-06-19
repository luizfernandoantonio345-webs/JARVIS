"""Rotas de voz — STT + TTS via voice_v2."""
import logging
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

_TTS_DIR = Path(__file__).parent.parent / "data" / "tts"

log = logging.getLogger(__name__)
router = APIRouter(tags=["Voice"])


@router.post("/command")
async def voice_command(
    audio: UploadFile = File(..., description="Arquivo de áudio (wav/mp3/webm)"),
    session_id: str = Form("voice"),
    language: str = Form("pt"),
):
    """
    Pipeline de voz completo:
      1. Recebe áudio do cliente
      2. Transcreve com Whisper (STT)
      3. Processa com orchestrator (LLM)
      4. Gera resposta em áudio (TTS)
      5. Retorna JSON com transcript, response e audio_path
    """
    if not audio.content_type or "audio" not in audio.content_type:
        # Aceita webm/ogg/mp4 também (gravação de navegador)
        allowed_ext = {".wav", ".mp3", ".webm", ".ogg", ".m4a", ".mp4"}
        ext = os.path.splitext(audio.filename or "")[1].lower()
        if ext not in allowed_ext:
            raise HTTPException(400, f"Formato não suportado: {audio.content_type}")

    try:
        content = await audio.read()
    except Exception as e:
        raise HTTPException(500, f"Erro lendo áudio: {e}")

    if len(content) < 100:
        raise HTTPException(400, "Arquivo de áudio muito pequeno ou vazio")

    log.info("[VOICE] Comando recebido: %dB session=%s lang=%s", len(content), session_id, language)

    try:
        from voice_v2.pipeline import process_audio_pipeline
        result = await process_audio_pipeline(content, session_id=session_id, language=language)
    except Exception as e:
        log.error("[VOICE] Pipeline falhou: %s", e)
        raise HTTPException(500, f"Erro no pipeline de voz: {e}")

    return result


@router.get("/tts")
async def tts_generate(text: str, voice: str | None = None):
    """
    Gera áudio TTS para o texto e retorna o arquivo MP3.
    Útil para o frontend tocar a resposta via <audio>.
    """
    if not text or not text.strip():
        raise HTTPException(400, "Texto vazio")

    try:
        from voice_v2.output import generate_tts_file
        import edge_tts

        cfg_voice = voice
        if not cfg_voice:
            try:
                from config import get_config
                cfg_voice = get_config().tts_voice
            except Exception:
                cfg_voice = "en-GB-RyanNeural"

        path = await generate_tts_file(text)
        if path is None:
            raise HTTPException(503, "TTS indisponível — edge-tts não instalado")

        return FileResponse(
            path,
            media_type="audio/mpeg",
            filename="jarvis_tts.mp3",
            background=None,
        )
    except HTTPException:
        raise
    except Exception as e:
        log.error("[VOICE/TTS] Erro: %s", e)
        raise HTTPException(500, f"Erro TTS: {e}")


@router.get("/audio/{filename}", summary="Serve arquivo TTS gerado pelo pipeline")
async def serve_tts_audio(filename: str):
    """
    Serve arquivos MP3 gerados pelo pipeline de voz.
    Permite que o frontend (incluindo mobile) reproduza a resposta em áudio.
    """
    if not filename.endswith(".mp3") or "/" in filename or "\\" in filename:
        raise HTTPException(400, "Nome de arquivo inválido")

    path = _TTS_DIR / filename
    if not path.exists():
        raise HTTPException(404, "Arquivo de áudio não encontrado ou expirado")

    return FileResponse(str(path), media_type="audio/mpeg", filename=filename)


@router.get("/status")
async def voice_status():
    """Retorna disponibilidade de TTS e STT."""
    try:
        from voice_v2.resilient_loader import load_voice_safe
        info = load_voice_safe()
    except Exception as e:
        info = {"mode": "none", "error": str(e)}
    return info
