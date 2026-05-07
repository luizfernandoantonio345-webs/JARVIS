from __future__ import annotations

import logging
import json
import math
import uuid
from pathlib import Path
from typing import Any, List

from memory_v2.embedding_service import get_embedding
from memory_v2.schemas import RetrievedMemory

log = logging.getLogger(__name__)
COLLECTION_NAME = "jarvis_memory"
PERSIST_DIR = Path(__file__).resolve().parents[1] / "chroma_store"
FALLBACK_FILE = Path(__file__).resolve().parents[1] / "semantic_memory_fallback.jsonl"


class VectorStore:
    def __init__(self) -> None:
        self._collection = None
        self._fallback_rows: list[dict[str, Any]] = self._load_fallback()
        try:
            import chromadb
            client = chromadb.PersistentClient(path=str(PERSIST_DIR))
            self._collection = client.get_or_create_collection(COLLECTION_NAME)
        except Exception as exc:
            log.warning("memory_v2.chromadb_unavailable fallback_only error=%s", exc)

    def _load_fallback(self) -> list[dict[str, Any]]:
        if not FALLBACK_FILE.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in FALLBACK_FILE.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
        return rows[-10_000:]

    def add_memory(self, text: str, metadata: dict[str, Any] | None = None, memory_id: str | None = None) -> str:
        memory_id = memory_id or uuid.uuid4().hex
        metadata = metadata or {}
        if self._collection is None:
            row = {
                "id": memory_id,
                "text": text,
                "metadata": metadata,
                "embedding": get_embedding(text),
            }
            self._fallback_rows.append(row)
            try:
                with open(FALLBACK_FILE, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            except Exception as exc:
                log.warning("memory_v2.fallback_persist_failed error=%s", exc)
            return memory_id
        self._collection.add(
            ids=[memory_id],
            documents=[text],
            embeddings=[get_embedding(text)],
            metadatas=[metadata],
        )
        return memory_id

    def query_similar(self, query: str, top_k: int = 5) -> List[RetrievedMemory]:
        if self._collection is None:
            query_embedding = get_embedding(query)
            scored = []
            for row in self._fallback_rows:
                scored.append((_cosine(query_embedding, row.get("embedding", [])), row))
            scored.sort(key=lambda item: item[0], reverse=True)
            return [
                RetrievedMemory(
                    id=row["id"],
                    text=row["text"],
                    metadata=row.get("metadata", {}),
                    distance=1.0 - score,
                )
                for score, row in scored[:top_k]
                if score > 0.05
            ]
        result = self._collection.query(
            query_embeddings=[get_embedding(query)],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        docs = result.get("documents", [[]])[0]
        ids = result.get("ids", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        return [
            RetrievedMemory(id=i, text=d, metadata=m or {}, distance=dist)
            for i, d, m, dist in zip(ids, docs, metas, distances)
        ]


_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore()
    return _store


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0
