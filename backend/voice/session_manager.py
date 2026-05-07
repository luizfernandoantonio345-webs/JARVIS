from __future__ import annotations

import time
from uuid import uuid4

from pydantic import BaseModel, Field

from .authenticator import AuthResult


class VoiceSession(BaseModel):
    session_id: str
    authorized_at: float
    expires_at: float
    commands_count: int = 0
    last_activity: float = Field(default_factory=time.time)


_active_session: VoiceSession | None = None


async def get_or_create_session(auth: AuthResult) -> VoiceSession | None:
    global _active_session
    now = time.time()
    if not auth.authorized:
        return None
    if _active_session and _active_session.expires_at > now and now - _active_session.last_activity <= 600:
        if auth.confidence < 0.75:
            _active_session = None
        else:
            _active_session.commands_count += 1
            _active_session.last_activity = now
            return _active_session
    _active_session = VoiceSession(session_id=str(uuid4()), authorized_at=now, expires_at=now + 1800, commands_count=1)
    return _active_session


async def close_session() -> None:
    global _active_session
    _active_session = None


def current_session() -> VoiceSession | None:
    if _active_session and _active_session.expires_at > time.time():
        return _active_session
    return None

