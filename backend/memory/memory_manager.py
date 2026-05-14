"""
Memory manager — optimized with:
  - LRU query cache (avoid re-embedding identical queries, TTL=60s)
  - Write deduplication (hash-based, skip near-duplicate content)
  - Async-first: all public functions are async
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections import OrderedDict
from datetime import datetime
from typing import Any

from memory.memory_indexer import should_store
from memory.memory_retriever import retrieve_context
from memory.vector_store import get_vector_store

log = logging.getLogger(__name__)
MAX_ITEMS = 10_000

# ── Query cache (avoid re-embedding identical queries) ────────────────────────
_QUERY_CACHE_MAX = 128
_QUERY_CACHE_TTL = 60.0   # seconds
_query_cache: OrderedDict[str, tuple[float, list[str]]] = OrderedDict()


def _qcache_get(query: str, top_k: int) -> list[str] | None:
    key = f"{query}:{top_k}"
    if key not in _query_cache:
        return None
    ts, results = _query_cache[key]
    if time.monotonic() - ts > _QUERY_CACHE_TTL:
        del _query_cache[key]
        return None
    _query_cache.move_to_end(key)
    return results


def _qcache_put(query: str, top_k: int, results: list[str]) -> None:
    key = f"{query}:{top_k}"
    _query_cache[key] = (time.monotonic(), results)
    _query_cache.move_to_end(key)
    if len(_query_cache) > _QUERY_CACHE_MAX:
        _query_cache.popitem(last=False)


# ── Write deduplication (hash-based) ─────────────────────────────────────────
_WRITE_DEDUP_MAX = 500
_write_hashes: OrderedDict[str, float] = OrderedDict()  # hash → stored_ts
_WRITE_DEDUP_TTL = 3600.0   # 1 hour: same content within this window is skipped


def _is_duplicate_write(text: str) -> bool:
    h = hashlib.sha1(text.strip().lower().encode()).hexdigest()[:20]
    if h in _write_hashes:
        age = time.monotonic() - _write_hashes[h]
        if age < _WRITE_DEDUP_TTL:
            return True
        del _write_hashes[h]
    _write_hashes[h] = time.monotonic()
    _write_hashes.move_to_end(h)
    if len(_write_hashes) > _WRITE_DEDUP_MAX:
        _write_hashes.popitem(last=False)
    return False


# ── Public API ─────────────────────────────────────────────────────────────────

async def store_memory(text: str, metadata: dict[str, Any] | None = None) -> str | None:
    return await asyncio.to_thread(store_memory_sync, text, metadata)


def store_memory_sync(text: str, metadata: dict[str, Any] | None = None) -> str | None:
    if not should_store(text):
        return None
    if _is_duplicate_write(text):
        log.debug("memory_v2.dedup_skip len=%d", len(text))
        return None
    metadata = {"type": "semantic", "timestamp": datetime.utcnow().isoformat(), **(metadata or {})}
    try:
        return get_vector_store().add_memory(text=text, metadata=metadata)
    except Exception as exc:
        log.warning("memory_v2.store_failed error=%s", exc)
        return None


async def get_context(query: str, top_k: int = 5) -> list[str]:
    # Cache hit — no embedding call needed
    cached = _qcache_get(query, top_k)
    if cached is not None:
        log.debug("memory_v2.cache_hit query_len=%d", len(query))
        return cached
    results = await asyncio.to_thread(get_context_sync, query, top_k)
    _qcache_put(query, top_k, results)
    return results


def get_context_sync(query: str, top_k: int = 5) -> list[str]:
    try:
        return retrieve_context(query, top_k=top_k)
    except Exception as exc:
        log.warning("memory_v2.retrieve_failed error=%s", exc)
        return []


