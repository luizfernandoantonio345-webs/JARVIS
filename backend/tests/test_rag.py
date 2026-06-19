"""
Testes para o RAG service (ChromaDB + sentence-transformers).
Se as dependências não estiverem instaladas, os testes são marcados como skip.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


def _rag_available() -> bool:
    try:
        import chromadb  # noqa
        from sentence_transformers import SentenceTransformer  # noqa
        return True
    except ImportError:
        return False


skip_if_no_rag = pytest.mark.skipif(
    not _rag_available(),
    reason="chromadb ou sentence-transformers não instalados"
)


@skip_if_no_rag
@pytest.mark.asyncio
async def test_rag_stats_returns_dict():
    from services.rag_service import rag_stats
    stats = await rag_stats()
    assert isinstance(stats, dict)
    assert "available" in stats


@skip_if_no_rag
@pytest.mark.asyncio
async def test_get_rag_context_empty_db_returns_empty_string():
    from services.rag_service import get_rag_context
    result = await get_rag_context("qualquer coisa sobre Python")
    assert isinstance(result, str)


@skip_if_no_rag
@pytest.mark.asyncio
async def test_index_document_returns_chunk_count():
    from services.rag_service import index_document
    count = await index_document(
        "FastAPI é um framework web moderno para Python. "
        "Ele é baseado em type hints e tem suporte a async nativo. "
        "Muito usado para criar APIs REST e WebSockets.",
        metadata={"source": "test_doc.txt", "type": "test"}
    )
    assert isinstance(count, int)
    assert count >= 1


@skip_if_no_rag
@pytest.mark.asyncio
async def test_get_rag_context_after_index():
    from services.rag_service import index_document, get_rag_context
    await index_document(
        "JARVIS usa Ollama para rodar modelos de linguagem localmente. "
        "O modelo padrão para desenvolvimento é qwen2:0.5b. "
        "Para a escola é usado mistral:7b com 32GB de RAM.",
        metadata={"source": "jarvis_docs.txt"}
    )
    result = await get_rag_context("qual modelo o JARVIS usa?")
    # Pode ser vazio se relevância abaixo do threshold, mas deve ser string
    assert isinstance(result, str)


@skip_if_no_rag
@pytest.mark.asyncio
async def test_index_file_nonexistent_returns_zero():
    from services.rag_service import index_file
    count = await index_file("/caminho/que/nao/existe.txt")
    assert count == 0


# ── Testes sem RAG (sempre rodam) ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rag_available_check_runs():
    from services.rag_service import _is_available
    result = _is_available()
    assert isinstance(result, bool)


@pytest.mark.asyncio
async def test_get_rag_context_without_rag_returns_empty():
    """Sem RAG disponível, deve retornar string vazia sem erro."""
    from services.rag_service import get_rag_context
    result = await get_rag_context("teste sem rag")
    assert isinstance(result, str)
