from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel, Field

from documents.analyzer import DocumentAnalyzer
from documents.processor import DocumentProcessor
from expertise.domain_detector import DomainDetector
from expertise.domain_memory import DomainMemory
from expertise.knowledge_researcher import KnowledgeResearcher, ResearchResult
from expertise.persona_engine import PersonaEngine
from memory.context_augmentor import ContextAugmentor
from memory.semantic_engine import SemanticMemory

router = APIRouter()


class JarvisResponse(BaseModel):
    status: str
    response: str = ""
    message: str = ""
    source: str = "jarvis_pipeline"
    domain_used: str = "general"
    expert_role: str = "general assistant"
    memory_augmented: bool = False
    sources: list[str] = Field(default_factory=list)


class DynamicExpert:
    def __init__(self, research: ResearchResult):
        self.research = research

    def get_system_prompt(self, task: str, context: str) -> str:
        return PersonaEngine().build_expert_system_prompt(self.research, context)


async def jarvis_pipeline(
    user_input: str,
    audio: bytes | None = None,
    attachments: list[UploadFile] | None = None,
) -> JarvisResponse:
    attachments = attachments or []
    if audio:
        from voice.voice_guard import voice_guard
        guard = await voice_guard(audio, user_input)
        if not guard.allowed:
            return JarvisResponse(status="error", message="Voz nao autorizada", source="voice_guard")

    domain_req = await DomainDetector().detect(user_input)
    knowledge: ResearchResult | None = None
    sources: list[str] = []

    try:
        from experts import CORE_EXPERTS
        expert = CORE_EXPERTS.get(domain_req.detected_domain)
    except Exception:
        expert = None

    if expert is None:
        memory = DomainMemory()
        if domain_req.requires_research:
            knowledge = await KnowledgeResearcher().research_domain(
                domain_req.detected_domain, domain_req.detected_role, domain_req.task_type
            )
            await memory.save(knowledge)
        else:
            knowledge = await memory.load(domain_req.detected_domain)
            if knowledge is None:
                knowledge = await KnowledgeResearcher().research_domain(
                    domain_req.detected_domain, domain_req.detected_role, domain_req.task_type
                )
                await memory.save(knowledge)
        expert = DynamicExpert(knowledge)
        sources = knowledge.sources

    doc_context = ""
    if attachments:
        processor = DocumentProcessor()
        analyzer = DocumentAnalyzer()
        parts = []
        base_prompt = expert.get_system_prompt(domain_req.task_type, user_input)
        for attachment in attachments:
            doc = await processor.process(attachment)
            doc_analysis = await analyzer.analyze(doc, user_input, base_prompt, domain_req.detected_domain)
            parts.append(doc_analysis.analysis)
        doc_context = "\n\n".join(parts)

    system_prompt = expert.get_system_prompt(domain_req.task_type, user_input)
    system_prompt = await ContextAugmentor().augment(user_input, system_prompt)

    from services.llm_service import call_llm
    try:
        response = await asyncio.to_thread(
            call_llm,
            [{"role": "system", "content": system_prompt}, {"role": "user", "content": f"{user_input}\n\n{doc_context}" if doc_context else user_input}],
            False,
            True,
        )
    except Exception as exc:
        response = (
            f"[MODO FALLBACK] LLM indisponivel ({exc}).\n\n"
            f"Dominio detectado: {domain_req.detected_domain}\n"
            f"Papel: {domain_req.detected_role}\n"
            f"Tarefa: {domain_req.task_type}\n\n"
            "Analise preliminar: aplicar o checklist senior do especialista detectado, "
            "priorizando riscos criticos, conformidade, evidencias e testes. "
            "VEREDICTO FINAL: APROVADO COM RESSALVAS ate validacao por LLM completo."
        )
    await SemanticMemory().add(
        content=f"Pergunta: {user_input[:200]}\nResposta: {response[:500]}",
        metadata={"domain": domain_req.detected_domain, "task": domain_req.task_type, "type": "interaction"},
    )
    return JarvisResponse(
        status="ok",
        response=response,
        domain_used=domain_req.detected_domain,
        expert_role=domain_req.detected_role,
        memory_augmented=True,
        sources=sources,
    )


@router.post("/ask", response_model=JarvisResponse)
async def ask(
    text: str = Form(...),
    audio: Optional[UploadFile] = File(None),
    attachments: Optional[list[UploadFile]] = File(None),
):
    audio_bytes = await audio.read() if audio else None
    return await jarvis_pipeline(text, audio_bytes, attachments or [])
