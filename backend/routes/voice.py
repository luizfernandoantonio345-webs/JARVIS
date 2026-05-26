import logging
import tempfile
import os
import asyncio
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from pydantic import BaseModel
from typing import Optional

from voice.controller import process_voice_command
from voice.enrollment import (
    enroll_voice,
    load_encrypted_profile,
    reset_profile,
    save_encrypted_profile,
    authenticate_voice,
    get_auth_log,
)

log = logging.getLogger(__name__)

router = APIRouter(tags=["Voice"])

class VoiceRequest(BaseModel):
    session_id: Optional[str] = "voice_v2"


class ThresholdRequest(BaseModel):
    threshold: float


@router.post("/enroll")
async def enroll(samples: list[UploadFile] = File(...), threshold: float = Form(0.82)):
    audio_samples = [await sample.read() for sample in samples]
    try:
        profile = enroll_voice(audio_samples, threshold=threshold)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"enrolled": True, "samples": profile.samples_count, "threshold": profile.threshold}


@router.post("/verify")
async def verify(audio: UploadFile = File(...)):
    result = authenticate_voice(await audio.read())
    return result


@router.get("/profile/status")
async def profile_status():
    profile = load_encrypted_profile()
    return {
        "enrolled": profile is not None,
        "samples": profile.samples_count if profile else 0,
        "threshold": profile.threshold if profile else None,
    }


@router.get("/auth/log")
async def auth_log():
    return {"attempts": get_auth_log(20)}


@router.post("/profile/reset")
async def profile_reset():
    reset_profile()
    return {"status": "ok", "enrolled": False}


@router.put("/profile/threshold")
async def update_threshold(body: ThresholdRequest):
    profile = load_encrypted_profile()
    if not profile:
        raise HTTPException(404, "voice profile not enrolled")
    profile.threshold = body.threshold
    save_encrypted_profile(profile)
    return {"status": "ok", "threshold": profile.threshold}

@router.post("/command")
async def voice_command(
    audio: UploadFile = File(..., description="Audio file (wav/mp3)"), 
    session_id: str = Form("voice_v2")
):
    """Voice command pipeline: upload audio → transcribe → LLM → TTS → JSON response."""

    if not audio.content_type or "audio" not in audio.content_type:
        raise HTTPException(400, "Arquivo deve ser audio (wav, mp3, etc)")

    # Save uploaded file to temp
    temp_path = tempfile.mktemp(suffix=os.path.splitext(audio.filename)[1] or ".wav")
    try:
        content = await audio.read()
        with open(temp_path, "wb") as f:
            f.write(content)
        log.info("Voice command started: file=%s size=%dB session=%s", 
                 audio.filename, len(content), session_id)
    except Exception as exc:
        raise HTTPException(500, f"Erro salvando audio: {exc}")

    from voice.voice_guard import voice_guard
    guard = await voice_guard(content, "")
    if not guard.allowed:
        return {
            "status": "denied",
            "response": "Acesso nao autorizado. Voz nao reconhecida.",
            "reason": guard.reason,
            "confidence": guard.confidence,
        }

    # Run pipeline (cleanup handled inside)
    result = await process_voice_command(temp_path, session_id)
    
    return result
