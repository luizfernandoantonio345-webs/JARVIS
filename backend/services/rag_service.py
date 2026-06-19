"""
RAG Service — JARVIS v8.0
Retrieval-Augmented Generation via ChromaDB + sentence-transformers.

Uso:
    from services.rag_service import get_rag_context
    context = await get_rag_context("como fazer deploy docker?")
    # Retorna string com trechos relevantes para injetar no prompt

Indexação:
    from services.rag_service import index_document
    await index_document("conteúdo do arquivo", {"source": "arquivo.py"})
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from pathlib import Path
from typing import Optional

log = logging.getLogger("jarvis.rag")

_CHROMA_DIR = Path(__file__).parent.parent / "data" / "chroma"
_COLLECTION = "jarvis_knowledge"
_TOP_K = 4
_MIN_RELEVANCE = 0.35  # score mínimo para incluir no contexto

# Lazy singletons
_client = None
_collection = None
_embedder = None
_available = None  # None = não testado, True/False = resultado


def _is_available() -> bool:
    """Verifica se ChromaDB e sentence-transformers estão disponíveis."""
    global _available
    if _available is not None:
        return _available
    try:
        import chromadb  # noqa: F401
        from sentence_transformers import SentenceTransformer  # noqa: F401
        _available = True
        log.info("[RAG] ChromaDB + sentence-transformers disponíveis")
    except ImportError as e:
        _available = False
        log.info("[RAG] RAG não disponível: %s", e)
    return _available


def _get_client():
    global _client
    if _client is None:
        import chromadb
        _CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(_CHROMA_DIR))
    return _client


def _get_collection():
    global _collection
    if _collection is None:
        client = _get_client()
        _collection = client.get_or_create_collection(
            name=_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        log.info("[RAG] Coleção '%s': %d documentos", _COLLECTION, _collection.count())
    return _collection


def _get_embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        # Modelo pequeno (~22MB) para velocidade
        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
        log.info("[RAG] Embedder carregado: all-MiniLM-L6-v2")
    return _embedder


def _embed(text: str) -> list[float]:
    emb = _get_embedder().encode(text, convert_to_numpy=True)
    return emb.tolist()


# ── Public API ─────────────────────────────────────────────────────────────────

async def get_rag_context(query: str, top_k: int = _TOP_K) -> str:
    """
    Busca os documentos mais relevantes para a query e retorna
    uma string formatada para injetar no prompt do LLM.
    Retorna "" se RAG não disponível ou sem resultados relevantes.
    """
    if not _is_available():
        return ""

    try:
        results = await asyncio.to_thread(_query_sync, query, top_k)
        if not results:
            return ""

        lines = ["[CONTEXTO RELEVANTE DA BASE DE CONHECIMENTO]"]
        for i, (doc, meta, score) in enumerate(results, 1):
            source = meta.get("source", "desconhecido")
            lines.append(f"\n--- Fonte {i}: {source} (relevância: {score:.2f}) ---")
            lines.append(doc[:800])  # limitar tamanho

        context = "\n".join(lines)
        log.debug("[RAG] Contexto: %d caracteres, %d fontes", len(context), len(results))
        return context

    except Exception as e:
        log.warning("[RAG] Erro ao buscar contexto: %s", e)
        return ""


async def index_document(
    content: str,
    metadata: Optional[dict] = None,
    chunk_size: int = 500,
    overlap: int = 50,
) -> int:
    """
    Indexa um documento na base RAG.
    Divide em chunks e cria embeddings para cada um.
    Retorna número de chunks indexados.
    """
    if not _is_available():
        return 0

    try:
        chunks = _chunk_text(content, chunk_size, overlap)
        count = await asyncio.to_thread(_index_chunks_sync, chunks, metadata or {})
        log.info("[RAG] Indexado: %d chunks de %d chars", count, len(content))
        return count
    except Exception as e:
        log.warning("[RAG] Erro ao indexar: %s", e)
        return 0


async def index_file(file_path: str) -> int:
    """Indexa um arquivo de texto/código na base RAG."""
    try:
        path = Path(file_path)
        if not path.exists():
            return 0
        content = path.read_text(encoding="utf-8", errors="ignore")
        return await index_document(
            content,
            metadata={"source": str(path.name), "path": str(path), "type": "file"},
        )
    except Exception as e:
        log.warning("[RAG] Erro ao ler arquivo %s: %s", file_path, e)
        return 0


async def rag_stats() -> dict:
    """Retorna estatísticas da base RAG."""
    if not _is_available():
        return {"available": False, "count": 0}
    try:
        col = _get_collection()
        return {
            "available": True,
            "count": col.count(),
            "collection": _COLLECTION,
            "path": str(_CHROMA_DIR),
        }
    except Exception as e:
        return {"available": True, "count": -1, "error": str(e)}


# ── Sync helpers (rodam em thread pool) ───────────────────────────────────────

def _query_sync(query: str, top_k: int) -> list[tuple[str, dict, float]]:
    col = _get_collection()
    if col.count() == 0:
        return []

    emb = _embed(query)
    results = col.query(
        query_embeddings=[emb],
        n_results=min(top_k, col.count()),
        include=["documents", "metadatas", "distances"],
    )

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    # Converter distância cosine em score de similaridade (1 - dist)
    out = []
    for doc, meta, dist in zip(docs, metas, distances):
        score = max(0.0, 1.0 - float(dist))
        if score >= _MIN_RELEVANCE:
            out.append((doc, meta, score))

    return out


def _index_chunks_sync(chunks: list[str], metadata: dict) -> int:
    col = _get_collection()
    ids, embeddings, documents, metas = [], [], [], []

    for i, chunk in enumerate(chunks):
        chunk_id = hashlib.md5(chunk.encode()).hexdigest()[:16] + f"_{i}"
        ids.append(chunk_id)
        embeddings.append(_embed(chunk))
        documents.append(chunk)
        metas.append({**metadata, "chunk_idx": i})

    if ids:
        col.upsert(ids=ids, embeddings=embeddings, documents=documents, metadatas=metas)

    return len(ids)


def _chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Divide texto em chunks com sobreposição."""
    if len(text) <= size:
        return [text] if text.strip() else []

    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += size - overlap

    return chunks
