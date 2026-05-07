"""
Hybrid LLM service with automatic complexity detection.

Routing strategy:
  force_local=True  → always Ollama (used by router/planner, low-latency ops)
  force_api=True    → always external API
  default           → ComplexityScorer decides

Complexity scoring (0.0 – 1.0):
  > COMPLEX_THRESHOLD  → external API (Claude → OpenAI → Ollama fallback)
  ≤ COMPLEX_THRESHOLD  → local Ollama

Supported API providers (checked in priority order):
  1. Anthropic Claude  (ANTHROPIC_API_KEY)
  2. OpenAI            (OPENAI_API_KEY)

Both keys are optional. If neither is set, all calls go local.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from collections import OrderedDict
from enum import Enum
from functools import lru_cache

import httpx
import ollama

from core.jarvis_persona import inject_system_persona

log = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────

LOCAL_MODEL        = os.getenv("LOCAL_MODEL",    "qwen2:0.5b")
OPENAI_MODEL       = os.getenv("OPENAI_MODEL",   "gpt-4o-mini")
CLAUDE_MODEL       = os.getenv("CLAUDE_MODEL",   "claude-3-haiku-20240307")

_OPENAI_KEY        = os.getenv("OPENAI_API_KEY")
_ANTHROPIC_KEY     = os.getenv("ANTHROPIC_API_KEY")

COMPLEX_THRESHOLD  = float(os.getenv("COMPLEX_THRESHOLD", "0.45"))
API_TIMEOUT        = int(os.getenv("LLM_API_TIMEOUT", "45"))
USE_FINE_TUNED_MODEL = os.getenv("JARVIS_USE_FINE_TUNED_MODEL", "0").lower() in {"1", "true", "yes"}

# ── External API endpoints (configurable via env) ─────────────────────────────
OPENAI_API_URL    = os.getenv("OPENAI_API_URL",    "https://api.openai.com/v1/chat/completions")
ANTHROPIC_API_URL = os.getenv("ANTHROPIC_API_URL", "https://api.anthropic.com/v1/messages")


# ── Response cache (local-only, deterministic calls) ──────────────────────────

_LLM_CACHE_MAX = 128
_llm_cache: OrderedDict[str, str] = OrderedDict()


def _cache_key(messages: list[dict], force_local: bool, force_api: bool) -> str:
    return json.dumps({"m": messages, "l": force_local, "a": force_api}, sort_keys=True)


def _cache_get(key: str) -> str | None:
    if key in _llm_cache:
        _llm_cache.move_to_end(key)   # LRU: most-recently-used at end
        return _llm_cache[key]
    return None


def _cache_put(key: str, value: str) -> None:
    _llm_cache[key] = value
    _llm_cache.move_to_end(key)
    if len(_llm_cache) > _LLM_CACHE_MAX:
        _llm_cache.popitem(last=False)  # evict LRU (oldest)


# ── Complexity scorer ──────────────────────────────────────────────────────────

class ComplexityLevel(str, Enum):
    SIMPLE  = "simple"
    MEDIUM  = "medium"
    COMPLEX = "complex"


# Signals that indicate a complex request
_COMPLEX_SIGNALS: list[tuple[str, float]] = [
    # multi-step reasoning keywords
    (r"\b(design|architect|compare|trade[-\s]?off|pros and cons|when to use)\b", 0.25),
    # large code blocks
    (r"```[\s\S]{300,}```",                                                       0.30),
    # error diagnosis
    (r"\b(traceback|stack.?trace|exception|segfault|memory.?leak)\b",            0.20),
    # multi-question (3+ question marks)
    (r"\?.*\?.*\?",                                                               0.15),
    # explicit complex tasks
    (r"\b(refactor|optimize|migrate|implement|build|create a system)\b",         0.20),
]

_SIMPLE_SIGNALS: list[tuple[str, float]] = [
    # greetings / chitchat
    (r"^(hi|hello|hey|oi|olá|tudo bem|como vai)[^a-z]*$",                        0.40),
    # very short
    (r"^.{1,40}$",                                                                0.20),
    # yes/no questions
    (r"\b(is|are|do|does|can|will|should)\b.{0,60}\?$",                          0.15),
]


def score_complexity(messages: list[dict]) -> float:
    """
    Return a complexity score in [0.0, 1.0].
    Higher = more complex = prefer external API.
    """
    # Build a hashable key and delegate to the cached impl
    text = " ".join(
        m.get("content", "")
        for m in messages
        if m.get("role") == "user"
    )
    total_chars = sum(len(m.get("content", "")) for m in messages)
    return _score_complexity_cached(text, total_chars)


@lru_cache(maxsize=256)
def _score_complexity_cached(text: str, total_chars: int) -> float:
    score = 0.0
    score += min(math.log1p(total_chars) / math.log1p(4000) * 0.35, 0.35)
    for pattern, weight in _COMPLEX_SIGNALS:
        if re.search(pattern, text, re.IGNORECASE):
            score += weight
    for pattern, weight in _SIMPLE_SIGNALS:
        if re.search(pattern, text.strip(), re.IGNORECASE):
            score -= weight
    return max(0.0, min(1.0, score))


def classify_complexity(messages: list[dict]) -> ComplexityLevel:
    score = score_complexity(messages)
    if score >= COMPLEX_THRESHOLD:
        return ComplexityLevel.COMPLEX
    if score >= COMPLEX_THRESHOLD * 0.5:
        return ComplexityLevel.MEDIUM
    return ComplexityLevel.SIMPLE


# ── Provider calls ─────────────────────────────────────────────────────────────

def _call_ollama(messages: list[dict]) -> str:
    result = ollama.chat(model=LOCAL_MODEL, messages=messages)
    return result["message"]["content"]


def _call_openai(messages: list[dict]) -> str:
    resp = httpx.post(
        OPENAI_API_URL,
        headers={"Authorization": f"Bearer {_OPENAI_KEY}"},
        json={"model": OPENAI_MODEL, "messages": messages, "temperature": 0.7},
        timeout=API_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _call_claude(messages: list[dict]) -> str:
    # Claude API uses a separate "system" field
    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    user_messages = [m for m in messages if m["role"] != "system"]

    payload: dict = {
        "model": CLAUDE_MODEL,
        "max_tokens": 4096,
        "messages": user_messages,
    }
    if system_parts:
        payload["system"] = "\n\n".join(system_parts)

    resp = httpx.post(
        ANTHROPIC_API_URL,
        headers={
            "x-api-key":         _ANTHROPIC_KEY or "",
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        },
        json=payload,
        timeout=API_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


# ── Public API ─────────────────────────────────────────────────────────────────

def call_llm(
    messages: list[dict],
    force_local: bool = False,
    force_api: bool = False,
) -> str:
    """
    Route to the appropriate LLM backend.

    Priority chain for external API:
      Claude (if ANTHROPIC_API_KEY set) → OpenAI (if OPENAI_API_KEY set) → Ollama

    Parameters
    ----------
    messages    : OpenAI-format message list
    force_local : skip complexity check, always use local model
    force_api   : skip complexity check, always try external API first
    """
    original_messages = list(messages)
    messages = inject_system_persona(messages)
    # Cache check — only for local (deterministic) calls
    _cache_hit = False
    _ck: str | None = None
    if force_local and not force_api:
        _ck = _cache_key(messages, force_local, force_api)
        cached = _cache_get(_ck)
        if cached is not None:
            log.debug("LLM cache hit (local)")
            return cached
    # Inject boot context into the first LLM call after server restart
    try:
        from core.context_injector import inject_boot_context_if_needed
        messages = inject_boot_context_if_needed(messages)
    except Exception:
        pass  # context injection is best-effort

    # Inject behavior profile preferences
    try:
        from behavior.profile_injector import inject_profile_if_needed, get_task_type_from_messages
        task_type = get_task_type_from_messages(messages)
        messages = inject_profile_if_needed(messages, task_type=task_type)
    except Exception:
        pass  # profile injection is best-effort

    # Inject semantic memory from the optional ChromaDB layer.
    try:
        from memory_v2.memory_manager import get_context_sync
        query = " ".join(m.get("content", "") for m in messages if m.get("role") == "user")
        semantic_context = get_context_sync(query, top_k=3)
        if semantic_context:
            messages = [
                {
                    "role": "system",
                    "content": "Relevant semantic memory:\n" + "\n".join(f"- {item}" for item in semantic_context),
                }
            ] + messages
    except Exception:
        pass

    messages = inject_system_persona(messages)

    # Optional local LoRA adapter. If unavailable, normal routing continues.
    if USE_FINE_TUNED_MODEL and not force_api:
        try:
            from training.model_manager import get_fine_tuned_model_manager
            prompt = "\n".join(f"{m.get('role')}: {m.get('content')}" for m in messages)
            tuned = get_fine_tuned_model_manager().generate(prompt)
            if tuned:
                _store_semantic_interaction(original_messages, tuned)
                return tuned
        except Exception:
            pass

    # Route to preferred LLM based on behavior profile
    try:
        from behavior.profile_manager import get_profile_manager
        preferred = get_profile_manager().get_llm_for_task(
            "code_gen" if force_local else "default"
        )
        if not force_local and not force_api:
            if preferred == "claude":
                force_api = True
            elif preferred in {"gpt-4o-mini", "openai"}:
                force_api = True
            elif preferred == "ollama":
                force_local = True
    except Exception as exc:
        log.debug("[services.llm_service] suppressed exception", exc_info=exc)
        pass

    if force_local:
        result = _call_ollama(messages)
        if _ck is not None:
            _cache_put(_ck, result)
        _store_semantic_interaction(original_messages, result)
        return result

    complexity = classify_complexity(messages)
    use_api = force_api or (complexity == ComplexityLevel.COMPLEX)

    log.debug(
        "LLM routing: complexity=%s score=%.2f use_api=%s",
        complexity.value,
        score_complexity(messages),
        use_api,
    )

    if use_api:
        # Try Claude first (better reasoning), then OpenAI, then local
        if _ANTHROPIC_KEY:
            try:
                result = _call_claude(messages)
                log.debug("LLM: served by Claude (%s)", CLAUDE_MODEL)
                _store_semantic_interaction(original_messages, result)
                return result
            except Exception as exc:
                log.warning("Claude API failed: %s — trying OpenAI", exc)

        if _OPENAI_KEY:
            try:
                result = _call_openai(messages)
                _store_semantic_interaction(original_messages, result)
                return result
            except Exception as exc:
                log.warning("OpenAI API failed: %s — falling back to local", exc)

        if not _ANTHROPIC_KEY and not _OPENAI_KEY:
            log.debug("No API keys configured — using local model")

    result = _call_ollama(messages)
    _store_semantic_interaction(original_messages, result)
    return result


def _store_semantic_interaction(messages: list[dict], response: str) -> None:
    try:
        from memory_v2.memory_manager import store_memory_sync
        user_text = "\n".join(
            m.get("content", "") for m in messages if m.get("role") == "user"
        ).strip()
        if user_text:
            store_memory_sync(
                f"User: {user_text}\nAssistant: {response[:800]}",
                {"type": "interaction"},
            )
    except Exception:
        pass


# ── Model info ─────────────────────────────────────────────────────────────────

def get_model_info() -> dict:
    """Return which providers are available and the active local model."""
    return {
        "local_model":      LOCAL_MODEL,
        "claude_available": bool(_ANTHROPIC_KEY),
        "openai_available": bool(_OPENAI_KEY),
        "claude_model":     CLAUDE_MODEL if _ANTHROPIC_KEY else None,
        "openai_model":     OPENAI_MODEL if _OPENAI_KEY else None,
        "complex_threshold": COMPLEX_THRESHOLD,
    }


# ── Streaming ──────────────────────────────────────────────────────────────────

def _stream_ollama(messages: list[dict]):
    """Yield tokens from local Ollama model, one string at a time."""
    for chunk in ollama.chat(model=LOCAL_MODEL, messages=messages, stream=True):
        token: str = chunk["message"]["content"]
        if token:
            yield token


def _stream_openai(messages: list[dict]):
    """Yield tokens from OpenAI streaming API."""
    with httpx.stream(
        "POST",
        OPENAI_API_URL,
        headers={"Authorization": f"Bearer {_OPENAI_KEY}"},
        json={"model": OPENAI_MODEL, "messages": messages, "temperature": 0.7, "stream": True},
        timeout=API_TIMEOUT,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line or line == "data: [DONE]":
                continue
            if line.startswith("data: "):
                import json as _json
                try:
                    data = _json.loads(line[6:])
                    delta = data["choices"][0]["delta"].get("content", "")
                    if delta:
                        yield delta
                except Exception as exc:
                    log.debug("[services.llm_service] suppressed exception", exc_info=exc)
                    continue


def _stream_claude(messages: list[dict]):
    """Yield tokens from Anthropic Claude streaming API."""
    import json as _json
    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    user_messages = [m for m in messages if m["role"] != "system"]
    payload: dict = {
        "model":      CLAUDE_MODEL,
        "max_tokens": 4096,
        "stream":     True,
        "messages":   user_messages,
    }
    if system_parts:
        payload["system"] = "\n\n".join(system_parts)

    with httpx.stream(
        "POST",
        ANTHROPIC_API_URL,
        headers={
            "x-api-key":         _ANTHROPIC_KEY or "",
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        },
        json=payload,
        timeout=API_TIMEOUT,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            try:
                data = _json.loads(line[6:])
                if data.get("type") == "content_block_delta":
                    delta = data.get("delta", {}).get("text", "")
                    if delta:
                        yield delta
            except Exception as exc:
                log.debug("[services.llm_service] suppressed exception", exc_info=exc)
                continue


def call_llm_stream(
    messages: list[dict],
    force_local: bool = False,
    force_api: bool = False,
):
    """
    Streaming variant of call_llm. Yields text tokens one at a time.

    Routing logic mirrors call_llm. Falls back to local on API failure.
    If API streaming fails mid-stream, an error token is yielded and the
    generator stops; the caller must handle partial output.
    """
    messages = inject_system_persona(messages)

    if force_local:
        yield from _stream_ollama(messages)
        return

    complexity = classify_complexity(messages)
    use_api = force_api or (complexity == ComplexityLevel.COMPLEX)

    if use_api:
        if _ANTHROPIC_KEY:
            try:
                yield from _stream_claude(messages)
                return
            except Exception as exc:
                log.warning("Claude stream failed: %s — trying OpenAI", exc)

        if _OPENAI_KEY:
            try:
                yield from _stream_openai(messages)
                return
            except Exception as exc:
                log.warning("OpenAI stream failed: %s — falling back to local", exc)

    yield from _stream_ollama(messages)

