"""
Performance caching module for JARVIS.
Provides LRU cache for intent classification and LLM responses.
"""
import asyncio
import hashlib
import json
import time
from functools import wraps
from typing import Any, Callable, Dict, Optional, Tuple

from collections import OrderedDict


class LRUCache:
    """
    Least Recently Used cache with TTL support.
    Thread-safe and async-friendly.
    """

    def __init__(self, maxsize: int = 1000, ttl: Optional[float] = None):
        """
        Initialize LRU cache.

        Args:
            maxsize: Maximum number of items to store
            ttl: Time to live in seconds (None = infinite)
        """
        self.maxsize = maxsize
        self.ttl = ttl
        self.cache: Dict[str, Tuple[Any, float]] = OrderedDict()
        self.lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        async with self.lock:
            if key not in self.cache:
                return None

            value, timestamp = self.cache[key]

            # Check TTL
            if self.ttl and (time.time() - timestamp) > self.ttl:
                del self.cache[key]
                return None

            # Move to end (mark as recently used)
            self.cache.move_to_end(key)
            return value

    async def set(self, key: str, value: Any) -> None:
        """Set value in cache."""
        async with self.lock:
            if key in self.cache:
                del self.cache[key]

            self.cache[key] = (value, time.time())

            # Remove oldest if exceeds maxsize
            if len(self.cache) > self.maxsize:
                self.cache.popitem(last=False)

    async def clear(self) -> None:
        """Clear all cache entries."""
        async with self.lock:
            self.cache.clear()

    def get_stats(self) -> dict:
        """Get cache statistics."""
        return {
            "size": len(self.cache),
            "maxsize": self.maxsize,
            "utilization": len(self.cache) / self.maxsize,
            "ttl": self.ttl,
        }


class CacheKey:
    """Helper for generating cache keys."""

    @staticmethod
    def for_intent(text: str) -> str:
        """Generate cache key for intent classification."""
        # Normalize and hash
        normalized = text.lower().strip()
        return f"intent:{hashlib.md5(normalized.encode()).hexdigest()}"

    @staticmethod
    def for_llm(prompt: str, model: str, params: dict) -> str:
        """Generate cache key for LLM response."""
        cache_data = json.dumps(
            {"prompt": prompt, "model": model, "params": params},
            sort_keys=True
        )
        return f"llm:{hashlib.md5(cache_data.encode()).hexdigest()}"

    @staticmethod
    def for_memory(query: str, session_id: str) -> str:
        """Generate cache key for memory retrieval."""
        cache_data = f"{query}:{session_id}"
        return f"mem:{hashlib.md5(cache_data.encode()).hexdigest()}"


class CachedFunction:
    """Decorator for caching async functions."""

    def __init__(self, cache: LRUCache, key_func: Optional[Callable] = None):
        self.cache = cache
        self.key_func = key_func

    def __call__(self, func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            # Generate cache key
            if self.key_func:
                cache_key = self.key_func(*args, **kwargs)
            else:
                cache_key = f"{func.__name__}:{args}:{kwargs}"

            # Try cache
            cached_value = await self.cache.get(cache_key)
            if cached_value is not None:
                return cached_value

            # Execute and cache
            result = await func(*args, **kwargs)
            await self.cache.set(cache_key, result)
            return result

        return wrapper


class PerformanceMonitor:
    """Monitor performance metrics."""

    def __init__(self):
        self.metrics: Dict[str, list] = {}

    async def track(self, name: str, duration: float) -> None:
        """Track operation duration."""
        if name not in self.metrics:
            self.metrics[name] = []

        self.metrics[name].append(duration)

        # Keep only last 1000 entries
        if len(self.metrics[name]) > 1000:
            self.metrics[name] = self.metrics[name][-1000:]

    def get_stats(self, name: str) -> dict:
        """Get statistics for an operation."""
        if name not in self.metrics or not self.metrics[name]:
            return {"error": "No data"}

        durations = self.metrics[name]
        return {
            "min": min(durations),
            "max": max(durations),
            "avg": sum(durations) / len(durations),
            "p95": sorted(durations)[int(len(durations) * 0.95)],
            "count": len(durations),
        }

    def get_all_stats(self) -> dict:
        """Get all statistics."""
        return {name: self.get_stats(name) for name in self.metrics}


# Global instances
intent_cache = LRUCache(maxsize=5000, ttl=3600)  # 1 hour
llm_cache = LRUCache(maxsize=1000, ttl=1800)    # 30 minutes
memory_cache = LRUCache(maxsize=2000, ttl=600)  # 10 minutes
perf_monitor = PerformanceMonitor()


# Decorators for easy use
def cached_intent(func: Callable) -> Callable:
    """Decorator for caching intent classification."""
    return CachedFunction(intent_cache, key_func=lambda text, **kw: CacheKey.for_intent(text))(func)


def cached_llm(func: Callable) -> Callable:
    """Decorator for caching LLM responses."""
    def key_func(prompt: str, model: str = "default", **kwargs):
        return CacheKey.for_llm(prompt, model, {k: v for k, v in kwargs.items() if k in ["temperature", "max_tokens"]})
    return CachedFunction(llm_cache, key_func=key_func)(func)


async def measure_time(name: str, coro):
    """Measure execution time of async function."""
    start = time.time()
    try:
        result = await coro
        duration = time.time() - start
        await perf_monitor.track(name, duration)
        return result
    except Exception as e:
        duration = time.time() - start
        await perf_monitor.track(f"{name}:error", duration)
        raise
