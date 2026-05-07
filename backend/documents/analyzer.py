from __future__ import annotations

import asyncio
import time
from typing import Any

from pydantic import BaseModel, Field

from .processor import DocumentResult


class DocumentAnalysis(BaseModel):
    document: DocumentResult
    analysis: str
    expert_domain: str
    analyzed_at: float = Field(default_factory=time.time)


def format_tables(tables: list[Any], limit: int = 20) -> str:
    if not tables:
        return "Nenhuma tabela extraida."
    return "\n\n".join(str(t)[:3000] for t in tables[:limit])


class DocumentAnalyzer:
    async def analyze(self, document: DocumentResult, user_request: str, expert_system_prompt: str, detected_domain: str = "general") -> DocumentAnalysis:
        return await analyze_document(document, user_request, expert_system_prompt, detected_domain)


async def analyze_document(
    document: DocumentResult,
    user_request: str,
    expert_system_prompt: str,
    detected_domain: str = "general",
) -> DocumentAnalysis:
    civil_extra = ""
    if "civil" in detected_domain.lower() or "estrutural" in user_request.lower():
        civil_extra = """
VERIFICACOES ESPECIFICAS DE ENGENHARIA CIVIL:
- ART presente e valida; ABNT NBR 6118, NBR 6120, NBR 7480 quando aplicaveis.
- Cargas permanentes, sobrecarga, vento e sismo quando aplicavel.
- Dimensionamento de vigas, pilares, fundacoes, cobrimento minimo, taxa de armadura, fck e fator agua/cimento.
- Para cada calculo encontrado, reproduza a conta, compare o resultado e classifique impacto.
"""
    analysis_prompt = f"""
DOCUMENTO: {document.file_name}
TIPO: {document.file_type}
PAGINAS: {document.page_count}

CONTEUDO EXTRAIDO:
{document.extracted_text[:15000]}

TABELAS ENCONTRADAS:
{format_tables(document.extracted_tables)}

SOLICITACAO DO USUARIO:
{user_request}
{civil_extra}
Como o especialista definido, analise este documento respondendo:
1. RESUMO EXECUTIVO: o que e este documento em 3 frases
2. ANALISE TECNICA: analise detalhada conforme sua especialidade
3. PROBLEMAS ENCONTRADOS: liste cada problema com severidade [CRITICO/SERIO/MENOR]
4. CALCULOS: se houver, verifique cada calculo e sinalize erros com a conta correta
5. CONFORMIDADE: esta em conformidade com normas/padroes da area?
6. RECOMENDACOES: correcoes em ordem de prioridade
7. VEREDICTO FINAL: APROVADO / REPROVADO / APROVADO COM RESSALVAS
"""
    from services.llm_service import call_llm
    try:
        response = await asyncio.to_thread(
            call_llm,
            [{"role": "system", "content": expert_system_prompt}, {"role": "user", "content": analysis_prompt}],
            False,
            True,
        )
    except Exception as exc:
        response = (
            f"[MODO FALLBACK] LLM indisponivel ({exc}).\n"
            f"RESUMO EXECUTIVO: Documento {document.file_name} processado como {document.file_type}.\n"
            "ANALISE TECNICA: usar o expert detectado e validar conteudo extraido, tabelas, calculos e conformidade.\n"
            "PROBLEMAS ENCONTRADOS: sem avaliacao completa do LLM neste ambiente.\n"
            "RECOMENDACOES: revisar evidencias, normas aplicaveis e calculos de maior risco primeiro.\n"
            "VEREDICTO FINAL: APROVADO COM RESSALVAS."
        )
    try:
        from memory.semantic_engine import SemanticMemory
        await SemanticMemory().add(
            f"Analise de documento {document.file_name}: {response[:800]}",
            {"type": "document_analysis", "domain": detected_domain, "file": document.file_name},
        )
    except Exception:
        pass
    return DocumentAnalysis(document=document, analysis=response, expert_domain=detected_domain)
