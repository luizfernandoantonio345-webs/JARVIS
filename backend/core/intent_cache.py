"""
Intent Fast-Path + Cache — Phase 1 & 5 optimization layer.

Two-stage system sits BEFORE the LLM:

  Stage 1 — Rule-Based Fast Path
    Handles simple, deterministic intents with regex rules.
    No LLM call, no latency, no token cost.
    Covers 30–50% of common JARVIS requests.

  Stage 2 — LRU Intent Cache
    Normalizes user input, checks if we've parsed an identical/near-identical
    intent recently, and returns the cached result.
    Cache TTL: CACHE_TTL_S seconds. Size: CACHE_MAX_ITEMS entries.

  Stage 3 — (caller) LLM intent parser — only reached if stages 1+2 miss.

All stages are synchronous and have zero I/O cost.
"""
from __future__ import annotations

import hashlib
import re
import time
from collections import OrderedDict
from typing import Any

from intents.schemas import Intent

# ── Cache config ───────────────────────────────────────────────────────────────
CACHE_MAX_ITEMS = 256
CACHE_TTL_S = 300.0   # 5 min — intents for same input stay valid this long

# ── Rule definitions ──────────────────────────────────────────────────────────
# Each rule: (pattern, action, param_extractor)
# param_extractor(match) -> dict[str, Any]

_URL_PAT = r"https?://[^\s]+"
_APP_PAT = r"(?:the\s+)?(\w[\w\s\-]{1,40})"

_RULES: list[tuple[re.Pattern, str, Any]] = [
    # open browser / go to URL
    (re.compile(
        r"(?:open|go to|navigate to|visit|access)\s+(" + _URL_PAT + r")",
        re.I,
    ), "go_to_url", lambda m: {"url": m.group(1)}),

    # search the web
    (re.compile(
        r"(?:search|google|look up|find|pesquisa[r]?)\s+(?:for\s+)?(.+)",
        re.I,
    ), "go_to_url", lambda m: {"url": f"https://www.google.com/search?q={m.group(1).strip().replace(' ', '+')}"}),

    # open browser without a URL
    (re.compile(
        r"(?:open|launch|start)\s+(?:the\s+)?(?:browser|chrome|firefox|edge|safari)\b",
        re.I,
    ), "open_browser", lambda m: {}),

    # open app
    (re.compile(
        r"(?:open|launch|start|run)\s+" + _APP_PAT,
        re.I,
    ), "open_app", lambda m: {"app": m.group(1).strip()}),

    # run shell command — explicit "run command" phrasing
    (re.compile(
        r"(?:run|execute|exec)\s+(?:command|cmd|shell)?\s*[`\"']?(.+?)[`\"']?\s*$",
        re.I,
    ), "run_shell", lambda m: {"command": m.group(1).strip()}),

    # git clone
    (re.compile(
        r"(?:clone|git clone)\s+(" + _URL_PAT + r")",
        re.I,
    ), "git_clone", lambda m: {"url": m.group(1)}),

    # git commit
    (re.compile(
        r"git\s+commit(?:\s+-m\s+[\"']?(.+?)[\"']?)?\s*$",
        re.I,
    ), "git_commit", lambda m: {"message": m.group(1) or "chore: auto-commit"}),

    # read file
    (re.compile(
        r"(?:read|show|cat|view|display)\s+(?:file\s+)?[\"']?([^\s\"']+)[\"']?\s*$",
        re.I,
    ), "read_file", lambda m: {"path": m.group(1)}),
]


def _normalize(text: str) -> str:
    """Lower-case, collapse whitespace, strip punctuation for cache key."""
    return re.sub(r"\s+", " ", text.lower().strip().rstrip(".,!?"))


def _input_hash(normalized: str) -> str:
    return hashlib.sha1(normalized.encode()).hexdigest()[:16]


# ── Intent Cache (LRU) ────────────────────────────────────────────────────────

class _IntentCache:
    def __init__(self) -> None:
        self._store: OrderedDict[str, tuple[float, Intent]] = OrderedDict()

    def get(self, text: str) -> Intent | None:
        key = _input_hash(_normalize(text))
        if key not in self._store:
            return None
        ts, intent = self._store[key]
        if time.monotonic() - ts > CACHE_TTL_S:
            del self._store[key]
            return None
        self._store.move_to_end(key)
        return intent

    def put(self, text: str, intent: Intent) -> None:
        key = _input_hash(_normalize(text))
        self._store[key] = (time.monotonic(), intent)
        self._store.move_to_end(key)
        if len(self._store) > CACHE_MAX_ITEMS:
            self._store.popitem(last=False)

    def stats(self) -> dict[str, int]:
        return {"size": len(self._store), "max": CACHE_MAX_ITEMS}


_cache = _IntentCache()


# ── Public API ─────────────────────────────────────────────────────────────────

def fast_path_intent(user_input: str) -> Intent | None:
    """
    Try to resolve the intent using regex rules only — no LLM, no I/O.
    Returns None if no rule matches (caller should proceed to LLM).
    """
    text = user_input.strip()
    for pattern, action, extractor in _RULES:
        m = pattern.search(text)
        if m:
            try:
                params = extractor(m)
                return Intent(action=action, parameters=params, steps=[], risk_level="low")
            except Exception:
                continue
    return None


def cache_get(user_input: str) -> Intent | None:
    """Return a cached intent for this input, or None."""
    return _cache.get(user_input)


def cache_put(user_input: str, intent: Intent) -> None:
    """Store an LLM-derived intent in the cache."""
    _cache.put(user_input, intent)


def cache_stats() -> dict[str, int]:
    return _cache.stats()
