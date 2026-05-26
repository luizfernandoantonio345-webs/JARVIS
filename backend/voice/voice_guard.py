from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from .enrollment import authenticate_voice, load_encrypted_profile

log = logging.getLogger(__name__)


@dataclass
class VoiceGuardResult:
    allowed: bool
    reason: str
    confidence: float = 0.0
    mode: str = "open"


def _strict_voice_auth_enabled() -> bool:
    value = os.getenv("JARVIS_STRICT_VOICE_AUTH", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


async def voice_guard(audio_data: bytes | None, user_input: str = "") -> VoiceGuardResult:
    """
    Lightweight gate used before voice-driven actions.

    Fresh installs have no enrolled voice profile, so the default is permissive.
    Set JARVIS_STRICT_VOICE_AUTH=1 to require an enrolled and authenticated voice.
    """
    strict = _strict_voice_auth_enabled()
    profile = load_encrypted_profile()

    if not profile:
        if strict:
            return VoiceGuardResult(
                allowed=False,
                reason="Sem perfil de voz cadastrado",
                confidence=0.0,
                mode="strict",
            )
        return VoiceGuardResult(
            allowed=True,
            reason="Sem perfil de voz cadastrado; autenticacao permissiva",
            confidence=1.0,
            mode="permissive",
        )

    if not audio_data:
        return VoiceGuardResult(
            allowed=not strict,
            reason="Audio ausente para autenticacao de voz",
            confidence=0.0,
            mode="strict" if strict else "permissive",
        )

    try:
        auth = authenticate_voice(audio_data)
    except Exception as exc:
        log.warning("voice_guard authentication failed: %s", exc)
        return VoiceGuardResult(
            allowed=not strict,
            reason=f"Falha na autenticacao de voz: {exc}",
            confidence=0.0,
            mode="strict" if strict else "permissive",
        )

    return VoiceGuardResult(
        allowed=bool(auth.get("allowed")),
        reason=str(auth.get("reason") or "Autenticacao de voz avaliada"),
        confidence=float(auth.get("confidence") or 0.0),
        mode="strict" if strict else "profile",
    )
