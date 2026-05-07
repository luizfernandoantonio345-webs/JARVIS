from __future__ import annotations

import json
import math
import sqlite3
import struct
import time
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from config import get_config


class MemoryResult(BaseModel):
    id: str
    content: str
    metadata: dict = Field(default_factory=dict)
    score: float
    date: str


class SemanticMemory:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or get_config().memory_db_path
        self._init()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path), check_same_thread=False)

    def _init(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS semantic_memory (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    score REAL DEFAULT 1.0,
                    access_count INTEGER DEFAULT 0,
                    archived INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_accessed REAL DEFAULT 0
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_semantic_archived ON semantic_memory(archived)")
            conn.commit()

    async def add(self, content: str, metadata: dict) -> str:
        memory_id = str(uuid4())
        embedding = self._embed(content)
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO semantic_memory(id, content, metadata_json, embedding, score, last_accessed) VALUES (?, ?, ?, ?, 1.0, ?)",
                (memory_id, content, json.dumps(metadata, ensure_ascii=True), self._vec_to_blob(embedding), time.time()),
            )
            conn.commit()
        return memory_id

    async def search(self, query: str, top_k: int = 5) -> list[MemoryResult]:
        q = self._embed(query)
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, content, metadata_json, embedding, score, created_at FROM semantic_memory WHERE archived=0"
            ).fetchall()
        scored: list[tuple[float, tuple]] = []
        for row in rows:
            sim = self._cosine(q, self._blob_to_vec(row[3])) * float(row[4] or 1.0)
            scored.append((sim, row))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [
            MemoryResult(id=r[0], content=r[1], metadata=json.loads(r[2] or "{}"), score=score, date=r[5])
            for score, r in scored[:top_k]
            if score > 0.05
        ]
        if results:
            with self._conn() as conn:
                for result in results:
                    conn.execute(
                        "UPDATE semantic_memory SET access_count=access_count+1, last_accessed=?, score=MIN(1.0, score+0.05) WHERE id=?",
                        (time.time(), result.id),
                    )
                conn.commit()
        return results

    async def get_relevant_context(self, query: str) -> str:
        results = await self.search(query, top_k=3)
        if not results:
            return ""
        context = "\n\n".join(f"[Memoria de {r.date}]: {r.content}" for r in results)
        return f"CONTEXTO RELEVANTE DA MEMORIA:\n{context}"

    async def delete(self, memory_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM semantic_memory WHERE id=?", (memory_id,))
            conn.commit()
            return cur.rowcount > 0

    async def stats(self) -> dict:
        with self._conn() as conn:
            total, archived = conn.execute(
                "SELECT COUNT(*), SUM(CASE WHEN archived=1 THEN 1 ELSE 0 END) FROM semantic_memory"
            ).fetchone()
            by_type = conn.execute("SELECT metadata_json FROM semantic_memory WHERE archived=0").fetchall()
        counts: dict[str, int] = {}
        for (raw,) in by_type:
            try:
                typ = json.loads(raw or "{}").get("type", "unknown")
            except Exception:
                typ = "unknown"
            counts[typ] = counts.get(typ, 0) + 1
        return {"total": total or 0, "archived": archived or 0, "active": (total or 0) - (archived or 0), "by_type": counts}

    def _embed(self, text: str) -> list[float]:
        try:
            from sentence_transformers import SentenceTransformer
            if not hasattr(self, "_encoder"):
                self._encoder = SentenceTransformer("intfloat/multilingual-e5-small")
            return list(map(float, self._encoder.encode(text)))
        except Exception:
            return self._embed_fallback(text)

    def _embed_fallback(self, text: str, dim: int = 384) -> list[float]:
        vec = [0.0] * dim
        for token in text.lower().split():
            vec[hash(token) % dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def _vec_to_blob(self, vec: list[float]) -> bytes:
        return struct.pack(f"{len(vec)}f", *vec)

    def _blob_to_vec(self, blob: bytes) -> list[float]:
        return list(struct.unpack(f"{len(blob)//4}f", blob))

    def _cosine(self, a: list[float], b: list[float]) -> float:
        if len(a) != len(b):
            return 0.0
        denom = (math.sqrt(sum(x*x for x in a)) * math.sqrt(sum(y*y for y in b))) or 1.0
        return sum(x*y for x, y in zip(a, b)) / denom

