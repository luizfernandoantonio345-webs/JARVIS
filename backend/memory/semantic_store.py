from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from memory.vector_store import get_vector_store


@dataclass
class MemoryResult:
    id: str
    content: str
    metadata: dict[str, Any]
    score: float

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


class SemanticMemory:
    def __init__(self) -> None:
        self.collection = getattr(get_vector_store(), "_collection", None)

    async def store(self, content: str, metadata: dict[str, Any] | None = None) -> str:
        return await asyncio.to_thread(self.store_sync, content, metadata)

    def store_sync(self, content: str, metadata: dict[str, Any] | None = None) -> str:
        metadata = {
            "type": "conversation",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": "default",
            "tags": [],
            **(metadata or {}),
        }
        return get_vector_store().add_memory(text=content, metadata=metadata)

    async def search(self, query: str, n_results: int = 5) -> list[MemoryResult]:
        return await asyncio.to_thread(self.search_sync, query, n_results)

    def search_sync(self, query: str, n_results: int = 5) -> list[MemoryResult]:
        rows = get_vector_store().query_similar(query, top_k=n_results)
        results: list[MemoryResult] = []
        for row in rows:
            distance = float(row.distance or 0.0)
            score = max(0.0, min(1.0, 1.0 - distance))
            results.append(
                MemoryResult(
                    id=row.id,
                    content=row.text,
                    metadata=row.metadata,
                    score=score,
                )
            )
        return results

    async def get_context_for_prompt(self, query: str) -> str:
        return await asyncio.to_thread(self.get_context_for_prompt_sync, query)

    def get_context_for_prompt_sync(self, query: str) -> str:
        results = self.search_sync(query, n_results=5)
        if not results:
            return ""
        lines = []
        for item in results:
            kind = item.metadata.get("type", "memory")
            when = item.metadata.get("timestamp", "")
            lines.append(f"- [{kind} {item.score:.2f} {when}] {item.content[:700]}")
        return "\n".join(lines)


_semantic_memory: SemanticMemory | None = None


def get_semantic_memory() -> SemanticMemory:
    global _semantic_memory
    if _semantic_memory is None:
        _semantic_memory = SemanticMemory()
    return _semantic_memory
