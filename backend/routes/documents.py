from __future__ import annotations

from fastapi import APIRouter, File, Form, UploadFile

from documents.analyzer import DocumentAnalysis, DocumentAnalyzer
from documents.processor import DocumentProcessor
from expertise.domain_detector import DomainDetector
from expertise.knowledge_researcher import KnowledgeResearcher
from expertise.persona_engine import PersonaEngine

router = APIRouter()
_history: list[dict] = []


async def _expert_prompt(request: str) -> tuple[str, str]:
    domain_req = await DomainDetector().detect(request)
    try:
        from experts import CORE_EXPERTS
        expert = CORE_EXPERTS.get(domain_req.detected_domain)
        if expert:
            return expert.get_system_prompt(domain_req.task_type, request), domain_req.detected_domain
    except Exception:
        pass
    research = await KnowledgeResearcher().research_domain(
        domain_req.detected_domain, domain_req.detected_role, domain_req.task_type
    )
    return PersonaEngine().build_expert_system_prompt(research, request), domain_req.detected_domain


@router.post("/analyze", response_model=DocumentAnalysis)
async def analyze_document(file: UploadFile = File(...), request: str = Form(...)):
    document = await DocumentProcessor().process(file)
    prompt, domain = await _expert_prompt(request)
    analysis = await DocumentAnalyzer().analyze(document, request, prompt, domain)
    _history.append({
        "file_name": document.file_name,
        "domain": domain,
        "summary": analysis.analysis[:500],
        "analyzed_at": analysis.analyzed_at,
    })
    return analysis


@router.post("/analyze/batch")
async def analyze_batch(files: list[UploadFile] = File(...), request: str = Form(...)):
    prompt, domain = await _expert_prompt(request)
    results = []
    for file in files:
        document = await DocumentProcessor().process(file)
        result = await DocumentAnalyzer().analyze(document, request, prompt, domain)
        results.append(result)
    return {"count": len(results), "results": results}


@router.get("/history")
async def history():
    return {"history": _history[-20:]}

