"""
Memória como ferramenta do agente.

O sistema já tinha memória boa — memory_service com embeddings e similaridade
de cosseno, rag_service sobre ChromaDB, mais uma dúzia de módulos em memory/.
O que faltava era a mesma coisa que faltava nas actions: nada disso estava
ligado ao agente. Ele começava do zero a cada conversa.

Há duas formas de dar memória a um agente, e as duas são necessárias:

    automática   o contexto relevante entra no prompt antes de ele começar
                 (ver contexto_inicial, usado pelo agent_loop)

    deliberada   ele DECIDE buscar ou gravar no meio da tarefa, com ferramenta
                 (recall / remember / remember_preference)

A automática cobre o caso comum. A deliberada cobre o que importa: lembrar de
algo no meio do trabalho, e registrar uma decisão no momento em que ela é
tomada — não depois, quando o motivo já se perdeu.

Importar este módulo registra as ferramentas no tool_registry.
"""

from __future__ import annotations

import logging
import os

from .tool_registry import tool, truncate

log = logging.getLogger("jarvis.tools.memory")

# Sessão usada quando a ferramenta é chamada fora de um contexto de conversa.
SESSAO_PADRAO = os.getenv("JARVIS_MEMORY_SESSION", "jarvis-global")

# O agent_loop ajusta isto por tarefa, para a memória ficar na sessão certa.
_sessao_atual: str = SESSAO_PADRAO


def definir_sessao(session_id: str | None) -> None:
    global _sessao_atual
    _sessao_atual = session_id or SESSAO_PADRAO


def sessao_atual() -> str:
    return _sessao_atual


# ── Ferramentas ───────────────────────────────────────────────────────────────

@tool(
    name="recall",
    description=(
        "Busca na memória de longo prazo o que já foi conversado, decidido ou "
        "aprendido antes. Use quando o usuário mencionar algo como se você já "
        "soubesse ('aquele projeto', 'como combinamos'), ou antes de perguntar "
        "algo que talvez já tenha sido dito."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "O que você quer lembrar"},
            "limit": {"type": "integer", "description": "Quantos trechos (padrão 5)"},
        },
        "required": ["query"],
    },
    action_type="memory_read",
    read_only=True,
)
def recall(query: str, limit: int = 5) -> str:
    partes: list[str] = []

    try:
        from services.memory_service import (
            get_relevant_memory, get_relevant_preferences,
            get_relevant_project_context,
        )
    except Exception as exc:
        return f"ERRO: memória indisponível: {exc}"

    sid = sessao_atual()

    try:
        prefs = get_relevant_preferences(sid, query, limit=3)
        if prefs:
            partes.append("Preferências:\n" + "\n".join(
                f"  - {k}: {v}" for k, v in prefs.items()))
    except Exception as exc:
        log.debug("[MEM] preferências falharam: %s", exc)

    try:
        proj = get_relevant_project_context(sid, query, limit=3)
        if proj:
            partes.append("Contexto de projeto:\n" + "\n".join(
                f"  - {k}: {v}" for k, v in proj.items()))
    except Exception as exc:
        log.debug("[MEM] contexto de projeto falhou: %s", exc)

    try:
        trechos = get_relevant_memory(sid, query, limit=limit)
        if trechos:
            partes.append("Conversas anteriores:\n" + "\n".join(
                f"  - você: {m}\n    jarvis: {r}" for m, r in trechos))
    except Exception as exc:
        log.debug("[MEM] histórico falhou: %s", exc)

    if not partes:
        return f"Nada na memória sobre: {query}"
    return truncate("\n\n".join(partes), 6_000)


@tool(
    name="remember",
    description=(
        "Grava um fato ou decisão na memória de longo prazo, para sessões "
        "futuras. Use quando algo for decidido, quando o usuário contar algo "
        "sobre si ou sobre um projeto, ou quando você descobrir algo que vai "
        "importar depois. Grave o FATO, não a conversa inteira."
    ),
    parameters={
        "type": "object",
        "properties": {
            "fact": {"type": "string", "description": "O que registrar, em uma ou duas frases"},
            "context": {
                "type": "string",
                "description": "Por que isso importa ou de onde veio (opcional)",
            },
        },
        "required": ["fact"],
    },
    action_type="memory_write",
)
def remember(fact: str, context: str = "") -> str:
    if not fact.strip():
        return "ERRO: nada para gravar."
    try:
        from services.memory_service import save_memory
        save_memory(sessao_atual(), fact.strip(), context.strip() or "(registrado pelo agente)",
                    action="remember")
        return f"OK: gravado — {fact.strip()[:120]}"
    except Exception as exc:
        return f"ERRO ao gravar na memória: {exc}"


@tool(
    name="remember_preference",
    description=(
        "Registra uma preferência DURADOURA de como o usuário quer que você "
        "trabalhe: formato de resposta, nível de detalhe, stack preferida, o "
        "que ele não quer. Diferente de remember, que guarda fatos; isto guarda "
        "o jeito dele. Use quando ele corrigir seu comportamento."
    ),
    parameters={
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "Nome curto, ex: 'formato_resposta'"},
            "value": {"type": "string", "description": "A preferência, nas palavras dele"},
        },
        "required": ["key", "value"],
    },
    action_type="memory_write",
)
def remember_preference(key: str, value: str) -> str:
    if not key.strip() or not value.strip():
        return "ERRO: key e value são obrigatórios."
    try:
        from services.memory_service import set_preference
        set_preference(sessao_atual(), key.strip(), value.strip())
        return f"OK: preferência registrada — {key.strip()}: {value.strip()[:100]}"
    except Exception as exc:
        return f"ERRO ao gravar preferência: {exc}"


@tool(
    name="search_knowledge",
    description=(
        "Busca na base de conhecimento indexada (documentos, código, notas que "
        "foram adicionados ao RAG). Diferente de recall, que olha conversas; "
        "isto olha material indexado. Use para consultar documentação do próprio "
        "projeto."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "O que procurar"},
        },
        "required": ["query"],
    },
    action_type="memory_read",
    read_only=True,
)
def search_knowledge(query: str) -> str:
    try:
        import asyncio
        from services.rag_service import get_rag_context
    except Exception as exc:
        return f"ERRO: RAG indisponível: {exc}"

    try:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            resultado = asyncio.run(get_rag_context(query))
        else:
            # Já dentro de um loop: roda em thread separada para não travar.
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                resultado = pool.submit(asyncio.run, get_rag_context(query)).result(timeout=60)
    except Exception as exc:
        return f"ERRO na busca: {exc}"

    return truncate(resultado, 8_000) if resultado else f"Nada indexado sobre: {query}"


# ── Contexto automático ───────────────────────────────────────────────────────

def contexto_inicial(objetivo: str, session_id: str | None = None) -> str:
    """
    Bloco de contexto para injetar no início de uma tarefa.

    Puxa só o que for relevante ao objetivo — despejar a memória inteira gasta
    contexto e atrapalha mais do que ajuda. Devolve string vazia se não houver
    nada, para o chamador não inserir um bloco oco no prompt.
    """
    definir_sessao(session_id)
    resultado = recall(objetivo, limit=4)
    if resultado.startswith(("Nada na memória", "ERRO")):
        return ""
    return (
        "Contexto do que você já sabe sobre este usuário e este trabalho.\n"
        "Use se ajudar; ignore se não for pertinente.\n\n"
        f"{resultado}"
    )


__all__ = [
    "recall", "remember", "remember_preference", "search_knowledge",
    "contexto_inicial", "definir_sessao", "sessao_atual",
]
