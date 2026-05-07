from pydantic import BaseModel, Field
from typing import Optional

class VoiceRequest(BaseModel):
    session_id: str = Field(default="voice_v2", description="Session ID for chat context")

class VoiceResponse(BaseModel):
    transcription: str
    response: str
    status: str = "ok"
    audio_path: Optional[str] = None  # Temp path for playback if needed

class VoiceCommandResult(BaseModel):
    """Internal result for controller."""
    transcription: str
    llm_response: str
