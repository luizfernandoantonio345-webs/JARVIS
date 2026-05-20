from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, File, Form, UploadFile, Request
try:
    from fastapi_cache.decorator import cache
except ImportError:
    def cache(*a, **kw):
        def decorator(fn): return fn
        return decorator
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi import Limiter
from fastapi.responses import FileResponse, StreamingResponse
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
_generated_docs: dict[str, Path] = {}


class AttachmentArtifact(BaseModel):
    file_name: str
    file_type: str
    page_count: int = 1
    summary: str = ""
    preview_text: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class GeneratedDocumentArtifact(BaseModel):
    file_name: str
    download_url: str
    mime_type: str = "text/plain"
    size: int = 0


class JarvisResponse(BaseModel):
    status: str
    response: str = ""
    message: str = ""
    source: str = "jarvis_pipeline"
    domain_used: str = "general"
    expert_role: str = "general assistant"
    memory_augmented: bool = False
    sources: list[str] = Field(default_factory=list)
    attachments: list[AttachmentArtifact] = Field(default_factory=list)
    tts_audio_url: str = ""
    tts_mode: str = ""


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
    attachment_artifacts: list[AttachmentArtifact] = []
    if attachments:
        processor = DocumentProcessor()
        analyzer = DocumentAnalyzer()
        parts = []
        base_prompt = expert.get_system_prompt(domain_req.task_type, user_input)
        for attachment in attachments:
            doc = await processor.process(attachment)
            doc_analysis = await analyzer.analyze(doc, user_input, base_prompt, domain_req.detected_domain)
            parts.append(doc_analysis.analysis)
            attachment_artifacts.append(
                AttachmentArtifact(
                    file_name=doc.file_name,
                    file_type=doc.file_type,
                    page_count=doc.page_count,
                    summary=doc_analysis.analysis[:500],
                    preview_text=(doc.extracted_text or "")[:700],
                    metadata=doc.metadata or {},
                )
            )
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
        attachments=attachment_artifacts,
    )


@router.post("/ask", response_model=JarvisResponse)
@cache(expire=30)  # cache de 30s para perguntas idênticas
async def ask(
    request: Request,
    text: str = Form(...),
    audio: Optional[UploadFile] = File(None),
    attachments: Optional[list[UploadFile]] = File(None),
    tts: bool = Form(False),
    tts_summary_only: bool = Form(True),
):
    # Rate limit por IP: 10 req/min
    limiter: Limiter = request.app.state.limiter
    await limiter.limit("10/minute")(lambda req: None)(request)
    audio_bytes = await audio.read() if audio else None
    result = await jarvis_pipeline(text, audio_bytes, attachments or [])

    if tts:
        try:
            from voice.output import speak_silent

            tts_text = result.response
            if tts_summary_only:
                tts_text = result.response[:700]
            tts_file = await speak_silent(tts_text)
            if tts_file:
                result.tts_audio_url = f"/jarvis/tts?path={tts_file}"
                result.tts_mode = "summary" if tts_summary_only else "full"
        except Exception:
            pass

    return result


@router.get("/tts")
@cache(expire=60)
async def tts_from_text(request: Request, text: str = "", lang: str = "pt", path: Optional[str] = None):
    """TTS JARVIS — voz PT-BR configurável via .env (JARVIS_TTS_VOICE/RATE/PITCH)."""
    if path:
        tts_path = Path(path)
        if not tts_path.exists():
            return {"status": "error", "message": "Arquivo de audio nao encontrado"}
        return FileResponse(tts_path, media_type="audio/wav", filename=tts_path.name)

    if not text or not text.strip():
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="text e obrigatorio")

    try:
        import edge_tts
        from backend.config import get_config
        cfg = get_config()

        voice = cfg.tts_voice or "pt-BR-AntonioNeural"
        rate  = cfg.tts_rate  or "-12%"
        pitch = cfg.tts_pitch or "-15Hz"

        communicate = edge_tts.Communicate(
            text.strip()[:600],
            voice,
            rate=rate,
            pitch=pitch,
        )

        async def _stream_audio():
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    yield chunk["data"]

        try:
            from backend.observability.metrics import get_metrics
            from backend.core.event_bus import get_event_bus
            get_metrics().inc("tts.requests")
            import asyncio as _aio
            _aio.create_task(get_event_bus().emit("voice.tts", {"chars": len(text)}))
        except Exception:
            pass

        return StreamingResponse(
            _stream_audio(),
            media_type="audio/mpeg",
            headers={"Cache-Control": "no-store", "X-JARVIS-TTS": "ok"},
        )

    except ImportError:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="edge-tts nao instalado. Execute: pip install edge-tts")
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"Erro TTS: {str(e)}")


@router.post("/generate-document", response_model=GeneratedDocumentArtifact)
async def generate_document(
    content: str = Form(...),
    title: str = Form("jarvis_documento"),
    extension: str = Form("txt"),
):
    safe_ext = (extension or "txt").lower().replace(".", "")
    if safe_ext not in {"txt", "md", "json"}:
        safe_ext = "txt"

    temp_dir = Path(tempfile.gettempdir()) / "jarvis_generated_docs"
    temp_dir.mkdir(parents=True, exist_ok=True)

    file_name = f"{title.strip().replace(' ', '_') or 'jarvis_documento'}.{safe_ext}"
    file_path = temp_dir / file_name
    file_path.write_text(content, encoding="utf-8")

    doc_id = f"{file_path.name}-{int(file_path.stat().st_mtime)}"
    _generated_docs[doc_id] = file_path

    return GeneratedDocumentArtifact(
        file_name=file_name,
        download_url=f"/jarvis/generated-document/{doc_id}",
        mime_type="text/markdown" if safe_ext == "md" else ("application/json" if safe_ext == "json" else "text/plain"),
        size=file_path.stat().st_size,
    )


@router.get("/generated-document/{doc_id}")
async def download_generated_document(doc_id: str):
    file_path = _generated_docs.get(doc_id)
    if not file_path or not file_path.exists():
        return {"status": "error", "message": "Documento nao encontrado"}
    return FileResponse(file_path, media_type="application/octet-stream", filename=file_path.name)
