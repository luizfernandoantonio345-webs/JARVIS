"""
Canonical WebSocket message schemas for JARVIS v5.0.

SINGLE SOURCE OF TRUTH — import from here everywhere.
Never send raw dict over WebSocket; always use JarvisWSMessage.model_dump().

Frontend mirror: frontend/src/types/ws.ts
"""
from __future__ import annotations

import time
from enum import Enum
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field


class OrbStatus(str, Enum):
    """
    All valid Orb states. Mirrors TypeScript OrbStatus enum in frontend/src/types/ws.ts.
    Any new state must be added here AND in the TS file simultaneously.
    """
    idle      = "idle"
    listening = "listening"
    thinking  = "thinking"
    speaking  = "speaking"
    error     = "error"
    connecting = "connecting"   # transient — sent by frontend only, never by backend


class RiskSeverity(str, Enum):
    critical = "critical"
    high     = "high"
    medium   = "medium"


class RiskFinding(BaseModel):
    """A single security finding reported by the Sentinel."""
    file    : str
    line    : int
    pattern : str
    severity: RiskSeverity
    snippet : str   # max 80 chars, secret never expanded


class JarvisWSMessage(BaseModel):
    """
    Canonical WebSocket message. Every broadcast() call must use:
        await manager.broadcast(JarvisWSMessage(...).model_dump())

    Frontend reads: status, message, audio_url, data, ts, source
    """
    status   : OrbStatus
    message  : Optional[str]              = None
    audio_url: Optional[str]              = None
    data     : Optional[Any]              = None          # arbitrary agent payload
    ts       : float = Field(default_factory=time.time)  # Unix timestamp (UTC)
    source   : Optional[str]              = None          # agent/component that sent this
    task_id  : Optional[str]              = None          # correlates with a running task


# ── Convenience constructors ────────────────────────────────────────────────────

def idle_msg(message: str = "Pronto.", source: str = "system") -> dict:
    return JarvisWSMessage(status=OrbStatus.idle, message=message, source=source).model_dump()

def thinking_msg(message: str, source: str = "system") -> dict:
    return JarvisWSMessage(status=OrbStatus.thinking, message=message, source=source).model_dump()

def listening_msg(message: str, source: str = "system") -> dict:
    return JarvisWSMessage(status=OrbStatus.listening, message=message, source=source).model_dump()

def speaking_msg(message: str, audio_url: Optional[str] = None, source: str = "voice") -> dict:
    return JarvisWSMessage(
        status=OrbStatus.speaking, message=message,
        audio_url=audio_url, source=source,
    ).model_dump()

def error_msg(
    message: str,
    findings: Optional[List[RiskFinding]] = None,
    source: str = "system",
    task_id: Optional[str] = None,
) -> dict:
    return JarvisWSMessage(
        status=OrbStatus.error,
        message=message,
        data={"findings": [f.model_dump() for f in findings]} if findings else None,
        source=source,
        task_id=task_id,
    ).model_dump()
