from __future__ import annotations

from pydantic import BaseModel

from .authenticator import authenticate_voice


class GuardResult(BaseModel):
    allowed: bool
    reason: str = ""
    confidence: float = 0.0


async def voice_guard(audio: bytes, command: str = "") -> GuardResult:
    auth = await authenticate_voice(audio)
    if not auth.authorized:
        try:
            from main import manager
            from schemas.ws_messages import JarvisWSMessage, OrbStatus
            await manager.broadcast(
                JarvisWSMessage(
                    status=OrbStatus.error,
                    message=f"Acesso negado - confianca: {auth.confidence:.0%}",
                    source="voice_guard",
                ).model_dump()
            )
        except Exception:
            pass
        return GuardResult(allowed=False, reason=auth.reason, confidence=auth.confidence)
    return GuardResult(allowed=True, reason=auth.reason, confidence=auth.confidence)

