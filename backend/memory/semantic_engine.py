from __future__ import annotations

from typing import Any

from memory.semantic_store import get_semantic_memory


class SemanticMemory:
    """Compatibility layer for legacy imports expecting memory.semantic_engine."""

    async def add(self, content: str, metadata: dict[str, Any] | None = None) -> str:
        return await get_semantic_memory().store(content=content, metadata=metadata or {})

    async def search(self, query: str, top_k: int = 5):
        results = await get_semantic_memory().search(query=query, n_results=top_k)
        return [item.model_dump() for item in results]

    async def stats(self) -> dict[str, Any]:
        store = get_semantic_memory()
        return {
            "status": "ok",
            "backend": "semantic_store",
            "collection_ready": bool(getattr(store, "collection", None)),
        }
