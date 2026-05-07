from __future__ import annotations

from memory_v2.vector_store import get_vector_store

# ChromaDB cosine distance: 0 = identical, 2 = opposite.
# Only return memories with distance < threshold (i.e., cos_similarity > 1 - threshold).
# 0.7 → requires at least ~0.3 cosine similarity — filters irrelevant noise while
# keeping loosely related context.
_DISTANCE_THRESHOLD = 0.7


def retrieve_context(query: str, top_k: int = 5) -> list[str]:
    memories = get_vector_store().query_similar(query, top_k=top_k)
    return [
        memory.text
        for memory in memories
        if memory.text and memory.distance < _DISTANCE_THRESHOLD
    ]

