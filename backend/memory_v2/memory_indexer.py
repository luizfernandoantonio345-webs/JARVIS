from __future__ import annotations

IMPORTANT_MARKERS = {
    "i prefer", "prefiro", "preferencia", "preferência", "gosto de",
    "i am building", "estou construindo", "projeto", "project",
    "decidi", "decision", "importante", "remember", "lembre",
    "sempre", "usually", "costumo",
}

REJECT_MARKERS = {"oi", "olá", "hello", "thanks", "obrigado", "ok", "sim", "não"}


def should_store(text: str) -> bool:
    cleaned = " ".join(text.lower().split())
    if len(cleaned) < 24:
        return False
    if cleaned in REJECT_MARKERS:
        return False
    return any(marker in cleaned for marker in IMPORTANT_MARKERS)

