import re
from collections import deque
from typing import Deque, Optional

# Response engine: thin post-processing layer for assistant speech.
# Rules enforced here:
# - max 2 sentences
# - pt-BR natural, no unnecessary technical detail
# - confident and human
# - avoid repeating the same phrase twice in a row


class ResponseEngine:
    def __init__(self, history_size: int = 3):
        self._history: Deque[str] = deque(maxlen=history_size)

    def _pick_short_response(self, text: str, *, max_sentences: int = 2) -> str:
        text = (text or "").strip()
        if not text:
            return "Pronto."

        text = re.sub(r"\s+", " ", text)
        parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text) if p.strip()]

        if parts:
            selected = " ".join(parts[:max_sentences]).strip()
        else:
            selected = text

        words = selected.split()
        if len(words) > 22:
            selected = " ".join(words[:22]).strip()

        if selected and selected[-1] not in ".!?":
            selected += "."
        return selected

    def _map_to_natural_phrase(self, text: str) -> str:
        t = (text or "").lower().strip()

        mappings = [
            (r"\b(operacao concluida|operation successful|done|success)\b", "Pronto."),
            (r"\babrindo\b|\bopening\b", "Abrindo."),
            (r"\bnavegando\b|\bnavigat\w*\b|\bindo para\b", "Indo."),
            (r"\bcomando executado\b", "Executado."),
            (r"\bnao consegui executar\b|\berro ao executar\b", "Tive um problema."),
            (r"\bacesso nao autorizado\b|\bvoz nao autorizada\b|\bdenied\b", "Acesso nao autorizado."),
            (r"\btimeout\b", "Demorou demais."),
            (r"\bverificando\b|\bchecando\b", "Vou verificar."),
            (r"\bfalha\b|\berror\b", "Tive um problema."),
            (r"\bmodo fallback\b", "Estou em fallback."),
        ]
        for pattern, phrase in mappings:
            if re.search(pattern, t, flags=re.IGNORECASE):
                return phrase

        return self._pick_short_response(text)

    def respond(self, system_response: str, *, fallback: str = "Tive um problema.") -> str:
        try:
            phrase = self._map_to_natural_phrase(system_response)
        except Exception:
            phrase = fallback

        phrase = (phrase or fallback).strip()
        phrase = self._pick_short_response(phrase)

        if self._history and phrase == self._history[-1]:
            phrase = "Certo." if phrase.lower().startswith("pronto") else "Pronto."

        self._history.append(phrase)
        return phrase


_engine: Optional[ResponseEngine] = None


def get_response_engine() -> ResponseEngine:
    global _engine
    if _engine is None:
        _engine = ResponseEngine(history_size=3)
    return _engine


def response_engine_transform(text: str) -> str:
    """Thin convenience wrapper."""
    return get_response_engine().respond(text)
