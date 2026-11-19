from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
import asyncio, tempfile, uuid, os, logging
try:
    from backend.config import get_config
except ImportError:
    from config import get_config

router = APIRouter()
log = logging.getLogger("jarvis.tts")

@router.get("/tts")
async def tts(
    text: str = Query(..., description="Texto para sintetizar"),
    lang: str = Query("pt"),
    profile: str | None = Query(None, description="Perfil de voz: jarvis, ultron, operacional, neutro"),
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
        # Perfil de voz ("jarvis", "ultron", ...) com a voz validada contra a
        # lista real do servico. Cai na config antiga se o modulo nao existir.
        try:
            from voice_v2.voice_profiles import parametros_de_fala
            vp = await parametros_de_fala(profile or cfg.tts_profile)
        except Exception:
            vp = {"voice": cfg.tts_voice, "rate": cfg.tts_rate, "pitch": cfg.tts_pitch}
        comm = edge_tts.Communicate(text, vp["voice"], rate=vp["rate"], pitch=vp["pitch"])
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


@router.get("/profiles")
async def listar_perfis_de_voz():
    """
    Perfis disponíveis e quais deles funcionam nesta máquina.

    Para ouvir cada um:
        /tts-iron/tts?text=Sistemas%20operacionais&profile=jarvis
        /tts-iron/tts?text=Sistemas%20operacionais&profile=ultron
    """
    from voice_v2.voice_profiles import listar_perfis, listar_vozes, perfil, resolver_voz

    disponiveis = await listar_vozes()
    perfis = []
    for item in listar_perfis():
        p = perfil(item["nome"])
        item["voz_efetiva"] = await resolver_voz(p)
        item["voz_existe"] = (not disponiveis) or item["voz_efetiva"] in disponiveis
        item["preview"] = (
            f"/tts-iron/tts?text=Sistemas+operacionais,+senhor&profile={item['nome']}"
        )
        perfis.append(item)

    return {
        "perfis": perfis,
        "vozes_no_servico": len(disponiveis),
        "aviso": None if disponiveis else "Não foi possível listar as vozes (sem rede?).",
    }
