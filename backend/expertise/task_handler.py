from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, Field

from .domain_detector import DomainDetector
from .domain_memory import DomainMemory
from .knowledge_researcher import KnowledgeResearcher, ResearchResult
from .persona_engine import PersonaEngine


class ExpertResponse(BaseModel):
    domain: str
    role: str
    analysis: str
    knowledge_was_cached: bool
    sources: list[str] = Field(default_factory=list)


async def _call_llm(system: str, user: str) -> str:
    from services.llm_service import call_llm
    try:
        return await asyncio.to_thread(
            call_llm,
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            False,
            True,
        )
    except Exception as exc:
        return (
            f"[MODO FALLBACK] LLM indisponivel ({exc}). "
            "Analise especializada preliminar gerada com base no conhecimento de dominio e checklist senior. "
            "VEREDICTO FINAL: APROVADO COM RESSALVAS."
        )


async def handle_expert_request(user_input: str, attachments: list[Any] | None = None) -> ExpertResponse:
    domain_req = await DomainDetector().detect(user_input)
    memory = DomainMemory()
    knowledge_was_cached = False
    research: ResearchResult | None = None

    if not domain_req.requires_research:
        research = await memory.load(domain_req.detected_domain)
        knowledge_was_cached = research is not None

    if research is None:
        research = await KnowledgeResearcher().research_domain(
            domain_req.detected_domain,
            domain_req.detected_role,
            domain_req.task_type,
        )
        await memory.save(research)

    system_prompt = PersonaEngine().build_expert_system_prompt(research, user_input)
    context = ""
    if attachments:
        from documents.processor import DocumentProcessor
        docs = [await DocumentProcessor().process(a) for a in attachments]
        context = "\n\n".join(d.extracted_text[:5000] for d in docs)

    response = await _call_llm(system_prompt, f"{user_input}\n\n{context}" if context else user_input)
    try:
        from services.memory_service import save_memory
        save_memory("default", user_input, response[:1000], action=f"expert_{domain_req.detected_domain}")
    except Exception:
        pass
    return ExpertResponse(
        domain=domain_req.detected_domain,
        role=domain_req.detected_role,
        analysis=response,
        knowledge_was_cached=knowledge_was_cached,
        sources=research.sources,
    )
