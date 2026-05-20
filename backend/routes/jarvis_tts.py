from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
import asyncio, tempfile, uuid, os, logging
from backend.config import get_config

router = APIRouter()
log = logging.getLogger("jarvis.tts")

@router.get("/tts")
async def tts(
    text: str = Query(..., description="Texto para sintetizar"),
    lang: str = Query("pt")
):
    """Voz JARVIS Iron Man - PT-BR, grave."""
    if not text or not text.strip():
        raise HTTPException(400, "text obrigatorio")

    cfg = get_config()
    text = text.strip()[:500]

    try:
        import edge_tts
    except ImportError:
        raise HTTPException(503, "edge-tts nao instalado: pip install edge-tts")

    try:
        path = os.path.join(tempfile.gettempdir(), f"jarvis_{uuid.uuid4().hex}.mp3")
        comm = edge_tts.Communicate(text, cfg.tts_voice, rate=cfg.tts_rate, pitch=cfg.tts_pitch)
        await comm.save(path)

        if not os.path.exists(path) or os.path.getsize(path) < 100:
            raise Exception("Audio invalido ou muito pequeno")

        with open(path, "rb") as f:
            data = f.read()
        try:
            os.unlink(path)
        except Exception:
            pass

        try:
            from backend.observability.metrics import get_metrics
            get_metrics().inc("tts.requests")
            get_metrics().inc("tts.chars", len(text))
        except Exception:
            pass

        try:
            from backend.core.event_bus import get_event_bus
            asyncio.create_task(get_event_bus().emit("voice.tts", {"chars": len(text)}))
        except Exception:
            pass

        return Response(
            content=data,
            media_type="audio/mpeg",
            headers={"Cache-Control": "no-cache", "X-JARVIS-TTS": "ok", "X-Chars": str(len(text))}
        )
    except HTTPException:
        raise
    except Exception as e:
        log.error("[TTS] Erro: %s", e)
        raise HTTPException(500, f"TTS erro: {e}")
