"""
Preference extractor — passively mines user preferences from conversation turns.

Runs asynchronously after each successful response (fire-and-forget).
Uses the local LLM with a strict prompt that returns JSON only.

Extractions are idempotent: same key → upsert in preferences table.

Extracted categories:
  language        — programming language preference
  code_style      — e.g. "functional", "OOP", "minimal"
  framework       — FastAPI, React, Django, etc.
  verbosity       — "concise" | "detailed"
  response_lang   — "pt-BR" | "en" | etc.
  stack           — full stack description
  project_type    — e.g. "API", "CLI tool", "web app"
"""

from __future__ import annotations

import json
import logging
import re
import threading

from services.llm_service import call_llm
from services.memory_service import set_preference

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a preference extractor. Analyze the user message and extract any
explicit or implicit preferences about how they work or what they prefer.

Reply with ONLY a JSON object. Keys must be from this list:
  language, code_style, framework, verbosity, response_lang, stack, project_type

Only include keys where you found clear evidence in the message.
If nothing is found, reply with exactly: {}

Example:
{"language": "Python", "framework": "FastAPI", "verbosity": "concise"}

No prose. No markdown. Just the JSON object.\
"""

_EXTRACTABLE_KEYS = frozenset({
    "language", "code_style", "framework", "verbosity",
    "response_lang", "stack", "project_type",
})


def _extract_preferences(message: str) -> dict[str, str]:
    """Call LLM and parse extracted preferences. Returns empty dict on failure."""
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": message},
    ]
    try:
        raw     = call_llm(messages, force_local=True)
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
        data    = json.loads(cleaned)
        if not isinstance(data, dict):
            return {}
        # Filter to only known keys with string values
        return {
            k: str(v).strip()
            for k, v in data.items()
            if k in _EXTRACTABLE_KEYS and v
        }
    except Exception as exc:
        log.debug("Preference extraction failed: %s", exc)
        return {}


def _run_extraction(session_id: str, message: str) -> None:
    """Background thread: extract and persist preferences."""
    prefs = _extract_preferences(message)
    for key, value in prefs.items():
        try:
            set_preference(session_id, key, value, confidence=0.85)
            log.debug("Extracted preference [%s] %r = %r", session_id, key, value)
        except Exception as exc:
            log.warning("Failed to persist preference %r: %s", key, exc)


def extract_async(session_id: str, message: str) -> None:
    """
    Fire-and-forget preference extraction.
    Runs in a daemon thread — never blocks the response path.
    """
    t = threading.Thread(
        target=_run_extraction,
        args=(session_id, message),
        daemon=True,
        name=f"pref-extract-{session_id[:8]}",
    )
    t.start()
