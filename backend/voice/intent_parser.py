from __future__ import annotations

try:
    from intents.intent_parser import (
        AmbiguousIntentError,
        IntentCandidate,
        normalize_text,
        parse_intent,
        parse_intent_candidate,
        strip_wake_noise,
    )
except ModuleNotFoundError:
    from backend.intents.intent_parser import (
        AmbiguousIntentError,
        IntentCandidate,
        normalize_text,
        parse_intent,
        parse_intent_candidate,
        strip_wake_noise,
    )

__all__ = [
    "AmbiguousIntentError",
    "IntentCandidate",
    "normalize_text",
    "parse_intent",
    "parse_intent_candidate",
    "strip_wake_noise",
]
