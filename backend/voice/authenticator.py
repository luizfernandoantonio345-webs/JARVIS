from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from pydantic import BaseModel

from .enrollment import VOICE_DIR, extract_embedding, load_encrypted_profile


AUTH_LOG_PATH = VOICE_DIR / "auth_log.json"


class AuthResult(BaseModel):
    authorized: bool
    confidence: float = 0.0
    reason: str


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    denom = ((sum(x*x for x in a) ** 0.5) * (sum(y*y for y in b) ** 0.5)) or 1.0
    return sum(x*y for x, y in zip(a, b)) / denom


def log_attempt(result: AuthResult, audio: bytes) -> None:
    AUTH_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    if AUTH_LOG_PATH.exists():
        try:
            rows = json.loads(AUTH_LOG_PATH.read_text(encoding="utf-8"))
        except Exception:
            rows = []
    rows.append({
        "ts": time.time(),
        "confidence": result.confidence,
        "reason": result.reason,
        "audio_hash": hashlib.sha256(audio).hexdigest()[:16],
    })
    AUTH_LOG_PATH.write_text(json.dumps(rows[-200:], indent=2), encoding="utf-8")


def failed_attempts_in_window(window_s: int = 60) -> int:
    if not AUTH_LOG_PATH.exists():
        return 0
    try:
        rows = json.loads(AUTH_LOG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return 0
    cutoff = time.time() - window_s
    return sum(1 for r in rows if r.get("ts", 0) >= cutoff and r.get("reason") != "voice_match")


async def authenticate_voice(audio_chunk: bytes) -> AuthResult:
    profile = load_encrypted_profile()
    if not profile:
        result = AuthResult(authorized=False, reason="no_profile")
        log_attempt(result, audio_chunk)
        return result
    if failed_attempts_in_window() >= 3:
        result = AuthResult(authorized=False, reason="locked")
        log_attempt(result, audio_chunk)
        return result
    current = extract_embedding(audio_chunk)
    similarities = [cosine_similarity(current, ref) for ref in profile.embeddings]
    max_similarity = max(similarities) if similarities else 0.0
    if max_similarity >= profile.threshold:
        result = AuthResult(authorized=True, confidence=max_similarity, reason="voice_match")
    else:
        result = AuthResult(authorized=False, confidence=max_similarity, reason="voice_mismatch")
    log_attempt(result, audio_chunk)
    return result


def get_auth_log(limit: int = 20) -> list[dict]:
    if not AUTH_LOG_PATH.exists():
        return []
    try:
        rows = json.loads(AUTH_LOG_PATH.read_text(encoding="utf-8"))
        return rows[-limit:]
    except Exception:
        return []

