import asyncio

from fastapi import APIRouter, Query

router = APIRouter()


@router.post("/wake")
async def wake_jarvis():
    from main import manager

    await manager.broadcast({"event": "voice_state", "state": "LISTENING"})
    return {"status": "listening"}


@router.post("/sleep")
async def sleep_jarvis():
    from main import manager

    await manager.broadcast({"event": "voice_state", "state": "IDLE"})
    return {"status": "idle"}


@router.post("/say")
async def say(text: str = Query(..., min_length=1, max_length=500)):
    try:
        from voice_v2.output import speak

        asyncio.create_task(speak(text))
        return {"speaking": text[:80]}
    except Exception as exc:
        return {"speaking": None, "fallback": str(exc)[:120]}
