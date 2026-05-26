"""
turbo_cache — Semantic cache for Modo Turbo  (FASE 13C)

Architecture:
  QueryTier.SIMPLE  → qwen2:0.5b local, no semantic cache needed
  QueryTier.MEDIUM  → check semantic cache first (cosine similarity ≥ 0.92),
                      then local LLM
  QueryTier.COMPLEX → check semantic cache first, then external API

Semantic cache uses sentence-transformers all-MiniLM-L6-v2 embeddings
stored in-memory (numpy) with a maximum of SEMANTIC_CACHE_MAX entries.

Performance targets:
  SIMPLE  → <100ms (pure local)
  MEDIUM  → <300ms (cache hit) / <2s  (cache miss, local)
  COMPLEX → <500ms (cache hit) / full API latency (cache miss)
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
SEMANTIC_CACHE_MAX  = 500
SEMANTIC_CACHE_TTL  = 3600 * 4    # 4 hours
SIMILARITY_THRESHOLD = 0.92

# Simple query signals (exact same as llm_service.py for consistency)
_SIMPLE_RE_PATTERNS = [
    r"^(hi|hello|hey|oi|ol[aá]|tudo bem|como vai)[^a-z]*$",
    r"^.{1,60}$",   # very short message
]

_COMPLEX_RE_PATTERNS = [
    r"```[\s\S]{200,}```",
    r"\b(refactor|implement|build|architect|design|migrate|optimize)\b",
    r"\b(traceback|stack.?trace|exception|segfault)\b",
]


class QueryTier(str, Enum):
    SIMPLE  = "simple"   # <60 chars, greetings, trivial
    MEDIUM  = "medium"   # typical conversation
    COMPLEX = "complex"  # code, multi-step, large context


# ── Tier classifier ────────────────────────────────────────────────────────────

def classify_query(messages: list[dict]) -> QueryTier:
    """Classify a list of messages into a query tier without LLM calls."""
    import re
    user_text = " ".join(
        m.get("content", "") for m in messages if m.get("role") == "user"
    )

    # Force COMPLEX for code blocks or long messages
    for pat in _COMPLEX_RE_PATTERNS:
        if re.search(pat, user_text, re.IGNORECASE):
            return QueryTier.COMPLEX

    # Check SIMPLE signals
    simple_hits = sum(
        1 for pat in _SIMPLE_RE_PATTERNS
        if re.search(pat, user_text.strip(), re.IGNORECASE)
    )
    if simple_hits >= 1 and len(user_text) < 100:
        return QueryTier.SIMPLE

    return QueryTier.MEDIUM


# ── Exact cache (hash-based, for identical messages) ──────────────────────────

_EXACT_CACHE_MAX = 256
_EXACT_CACHE_TTL = 300  # 5 min
_exact_lock = threading.Lock()
_exact_cache: OrderedDict[str, tuple[str, float]] = OrderedDict()


def _exact_key(messages: list[dict]) -> str:
    parts = []
    for m in messages:
        role = m.get("role") or ""
        content = m.get("content", "")
        # Normalize content to a deterministic string
        try:
            if isinstance(content, dict):
                content_str = json.dumps(content, sort_keys=True)
            elif not isinstance(content, str):
                content_str = str(content)
            else:
                content_str = content
            content_str = content_str.strip().lower()
        except Exception:
            content_str = str(content)
        parts.append((role, content_str))
    raw = json.dumps(parts, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def exact_cache_get(messages: list[dict]) -> str | None:
    k = _exact_key(messages)
    with _exact_lock:
        if k not in _exact_cache:
            return None
        val, ts = _exact_cache[k]
        if time.monotonic() - ts > _EXACT_CACHE_TTL:
            del _exact_cache[k]
            return None
        _exact_cache.move_to_end(k)
        return val


def exact_cache_put(messages: list[dict], response: str) -> None:
    k = _exact_key(messages)
    with _exact_lock:
        _exact_cache[k] = (response, time.monotonic())
        _exact_cache.move_to_end(k)
        while len(_exact_cache) > _EXACT_CACHE_MAX:
            _exact_cache.popitem(last=False)


# ── Semantic cache (embedding-based) ──────────────────────────────────────────

_semantic_lock = threading.Lock()
# List of (embedding_vector, response, stored_ts, original_text)
_semantic_entries: list[tuple[Any, str, float, str]] = []
_embed_model: Any = None
_embed_model_loading = False


def _get_embed_model():
    """Lazy-load the sentence-transformer model (first call only)."""
    global _embed_model, _embed_model_loading
    if _embed_model is not None:
        return _embed_model
    if _embed_model_loading:
        return None
    _embed_model_loading = True
    try:
        from sentence_transformers import SentenceTransformer
        _embed_model = SentenceTransformer("all-MiniLM-L6-v2")
        log.info("turbo_cache: embedding model loaded (all-MiniLM-L6-v2)")
    except Exception as exc:
        log.warning("turbo_cache: sentence-transformers not available: %s", exc)
        _embed_model = None
    _embed_model_loading = False
    return _embed_model


def _embed(text: str):
    """Return embedding vector or None."""
    model = _get_embed_model()
    if model is None:
        return None
    try:
        return model.encode(text, normalize_embeddings=True)
    except Exception as exc:
        log.debug("turbo_cache: embed failed: %s", exc)
        return None


def _cosine(a, b) -> float:
    """Cosine similarity for pre-normalized vectors (dot product)."""
    try:
        import numpy as np
        return float(np.dot(a, b))
    except Exception:
        return 0.0


def semantic_cache_get(messages: list[dict]) -> str | None:
    """Return cached response if a semantically similar query exists."""
    user_text = " ".join(
        m.get("content", "") for m in messages if m.get("role") == "user"
    ).strip()
    if len(user_text) < 10:
        return None

    vec = _embed(user_text)
    if vec is None:
        return None

    now = time.monotonic()
    with _semantic_lock:
        for entry_vec, response, ts, _ in _semantic_entries:
            if now - ts > SEMANTIC_CACHE_TTL:
                continue
            sim = _cosine(vec, entry_vec)
            if sim >= SIMILARITY_THRESHOLD:
                log.debug("turbo_cache: semantic hit (sim=%.3f)", sim)
                return response
    return None


def semantic_cache_put(messages: list[dict], response: str) -> None:
    """Store a response in the semantic cache."""
    user_text = " ".join(
        m.get("content", "") for m in messages if m.get("role") == "user"
    ).strip()
    if len(user_text) < 10:
        return

    vec = _embed(user_text)
    if vec is None:
        return

    with _semantic_lock:
        _semantic_entries.append((vec, response, time.monotonic(), user_text))
        # Evict old entries
        now = time.monotonic()
        cutoff = now - SEMANTIC_CACHE_TTL
        expired = [i for i, e in enumerate(_semantic_entries) if e[2] < cutoff]
        for i in reversed(expired):
            _semantic_entries.pop(i)
        # Enforce max size
        while len(_semantic_entries) > SEMANTIC_CACHE_MAX:
            _semantic_entries.pop(0)


def get_cache_stats() -> dict:
    """Return cache statistics for the status endpoint."""
    with _exact_lock:
        exact_size = len(_exact_cache)
    with _semantic_lock:
        semantic_size = len(_semantic_entries)
    return {
        "exact_cache_entries": exact_size,
        "semantic_cache_entries": semantic_size,
        "embed_model_loaded": _embed_model is not None,
        "similarity_threshold": SIMILARITY_THRESHOLD,
    }


# ── Turbo call (public entry point) ───────────────────────────────────────────

def turbo_call(
    messages: list[dict],
    force_local: bool = False,
    force_api: bool = False,
    system: str | None = None,
) -> tuple[str, str, float]:
    """
    Perform an LLM call with turbo routing and caching.

    Returns:
        (response_text, tier_used, latency_ms)

    Tier priorities:
      1. Exact cache hit        → instant
      2. Semantic cache hit     → instant (MEDIUM/COMPLEX only)
      3. SIMPLE tier            → local model directly
      4. MEDIUM/COMPLEX         → LLM call with post-store to semantic cache
    """
    from services.llm_service import call_llm

    t0 = time.monotonic()
    full_messages = ([{"role": "system", "content": system}] + messages) if system else messages

    # 1. Exact cache
    cached = exact_cache_get(full_messages)
    if cached:
        latency = (time.monotonic() - t0) * 1000
        log.debug("turbo_call: exact_cache hit (%.1fms)", latency)
        return cached, "exact_cache", latency

    tier = classify_query(messages)

    # 2. Semantic cache (not for simple — too risky for trivial mismatches)
    if tier != QueryTier.SIMPLE:
        sem_cached = semantic_cache_get(full_messages)
        if sem_cached:
            latency = (time.monotonic() - t0) * 1000
            log.debug("turbo_call: semantic_cache hit tier=%s (%.1fms)", tier, latency)
            return sem_cached, f"semantic_cache_{tier}", latency

    # 3. Actual LLM call
    use_local = force_local or (tier == QueryTier.SIMPLE and not force_api)
    response = call_llm(
        messages=full_messages,
        force_local=use_local,
        force_api=force_api and not use_local,
    )

    latency = (time.monotonic() - t0) * 1000

    # 4. Store in both caches
    exact_cache_put(full_messages, response)
    if tier != QueryTier.SIMPLE:
        semantic_cache_put(full_messages, response)

    log.debug("turbo_call: tier=%s local=%s (%.1fms)", tier, use_local, latency)
    return response, f"llm_{tier}", latency
