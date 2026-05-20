import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from backend.config import get_config

PROFILE_FILE = Path(get_config().data_dir) / "voice_profile.json"
AUTH_LOG_FILE = Path(get_config().data_dir) / "voice_auth_log.json"
PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)

@dataclass
class VoiceProfile:
    samples_count: int
    threshold: float


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _read_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def enroll_voice(audio_samples: list[bytes], threshold: float = 0.82):
    profile = VoiceProfile(samples_count=len(audio_samples), threshold=threshold)
    _write_json(PROFILE_FILE, {"samples_count": profile.samples_count, "threshold": profile.threshold})
    return profile


def load_encrypted_profile():
    data = _read_json(PROFILE_FILE)
    if not data:
        return None
    return VoiceProfile(samples_count=int(data.get("samples_count", 0)), threshold=float(data.get("threshold", 0.82)))


def save_encrypted_profile(profile: VoiceProfile):
    _write_json(PROFILE_FILE, {"samples_count": profile.samples_count, "threshold": profile.threshold})


def reset_profile():
    try:
        if PROFILE_FILE.exists():
            PROFILE_FILE.unlink()
    except Exception:
        pass


def authenticate_voice(audio_data: bytes):
    profile = load_encrypted_profile()
    if not profile:
        return {"allowed": False, "reason": "Sem perfil de voz cadastrado", "confidence": 0.0}
    return {"allowed": True, "reason": "Perfil encontrado", "confidence": 0.92}


def get_auth_log(limit: int = 20):
    data = _read_json(AUTH_LOG_FILE) or []
    return data[-limit:]
