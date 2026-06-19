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

    async def delete(self, session_id: str) -> bool:
        """Delete all semantic memory entries for a given session_id."""
        try:
            store = get_semantic_memory()
            if hasattr(store, "delete_by_session"):
                await store.delete_by_session(session_id)
                return True
            # Try ChromaDB-style deletion via where filter
            collection = getattr(store, "collection", None)
            if collection is not None:
                collection.delete(where={"session_id": session_id})
                return True
            return False
        except Exception:
            return False

    async def list_sessions(self) -> list[str]:
        """Return a list of unique session_ids stored in semantic memory."""
        try:
            store = get_semantic_memory()
            if hasattr(store, "list_sessions"):
                return await store.list_sessions()
            collection = getattr(store, "collection", None)
            if collection is not None:
                result = collection.get(include=["metadatas"])
                sessions = {
                    m.get("session_id")
                    for m in (result.get("metadatas") or [])
                    if m and m.get("session_id")
                }
                return sorted(sessions)
            return []
        except Exception:
            return []
