from __future__ import annotations

import base64
import json
import os
import shutil
import time
from pathlib import Path

from cryptography.fernet import Fernet
from pydantic import BaseModel, Field


VOICE_DIR = Path(__file__).resolve().parent
PROFILE_PATH = VOICE_DIR / "owner_profile.json"
BACKUP_DIR = VOICE_DIR / "backup"


class VoiceProfile(BaseModel):
    owner_id: str = "primary_owner"
    embeddings: list[list[float]]
    enrollment_ts: float = Field(default_factory=time.time)
    samples_count: int
    threshold: float = 0.82


def _fernet() -> Fernet:
    import hashlib
    raw = os.getenv("JARVIS_VOICE_KEY") or os.getenv("JARVIS_DEV_VOICE_KEY")
    if not raw:
        key_file = VOICE_DIR / ".voice_key"
        if not key_file.exists():
            key_file.write_text(base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"), encoding="utf-8")
        raw = key_file.read_text(encoding="utf-8").strip()
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def extract_embedding(audio: bytes) -> list[float]:
    try:
        from resemblyzer import VoiceEncoder, preprocess_wav
        import numpy as np
        import soundfile as sf
        import io
        wav, sr = sf.read(io.BytesIO(audio))
        wav = preprocess_wav(np.asarray(wav), source_sr=sr)
        encoder = VoiceEncoder()
        return [float(x) for x in encoder.embed_utterance(wav)]
    except Exception:
        return _fallback_embedding(audio)


def _fallback_embedding(audio: bytes, dim: int = 64) -> list[float]:
    import hashlib
    digest = hashlib.sha512(audio).digest()
    vec = [0.0] * dim
    for i, b in enumerate(digest):
        vec[i % dim] += (b / 255.0) * 2.0 - 1.0
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


def save_encrypted_profile(profile: VoiceProfile) -> None:
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    if PROFILE_PATH.exists():
        shutil.copy2(PROFILE_PATH, BACKUP_DIR / f"owner_profile_{int(time.time())}.json")
    encrypted = _fernet().encrypt(profile.model_dump_json().encode("utf-8"))
    PROFILE_PATH.write_bytes(encrypted)


def load_encrypted_profile() -> VoiceProfile | None:
    if not PROFILE_PATH.exists():
        return None
    data = _fernet().decrypt(PROFILE_PATH.read_bytes())
    return VoiceProfile.model_validate(json.loads(data.decode("utf-8")))


def reset_profile() -> None:
    if PROFILE_PATH.exists():
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PROFILE_PATH, BACKUP_DIR / f"owner_profile_reset_{int(time.time())}.json")
        PROFILE_PATH.unlink()


async def enroll_voice(audio_samples: list[bytes], threshold: float = 0.82) -> VoiceProfile:
    if len(audio_samples) < 5:
        raise ValueError("Voice enrollment requires at least 5 audio samples.")
    embeddings = [extract_embedding(sample) for sample in audio_samples]
    profile = VoiceProfile(embeddings=embeddings, samples_count=len(embeddings), threshold=threshold)
    save_encrypted_profile(profile)
    return profile
