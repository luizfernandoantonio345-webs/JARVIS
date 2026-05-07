from __future__ import annotations

import asyncio
import time
from typing import Any

from pydantic import BaseModel, Field


class ResearchResult(BaseModel):
    domain: str
    role: str
    knowledge_base: str
    frameworks: list[str] = Field(default_factory=list)
    checklist: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    research_ts: float = Field(default_factory=time.time)


_DOMAIN_PRESETS: dict[str, dict[str, list[str]]] = {
    "civil engineering": {
        "frameworks": ["ABNT NBR 6118", "ABNT NBR 6120", "ABNT NBR 7480", "ART/CREA", "memorial de calculo"],
        "checklist": ["ART presente", "cargas permanentes e acidentais", "dimensionamento de vigas/pilares/fundacoes", "cobrimento minimo", "fck e fator agua/cimento", "rastreabilidade dos calculos"],
        "red_flags": ["ausencia de responsavel tecnico", "calculo estrutural sem memoria", "taxa de armadura fora dos limites", "cargas omitidas", "incompatibilidade entre prancha e memorial"],
    },
    "penetration testing": {
        "frameworks": ["OWASP Top 10", "OWASP ASVS", "PTES", "MITRE ATT&CK", "CVSS"],
        "checklist": ["escopo autorizado", "reconhecimento", "auth/authz", "injecoes", "exposicao de dados", "relatorio com impacto e remediacao"],
        "red_flags": ["RCE", "IDOR", "SQLi exploravel", "secrets expostos", "bypass de autenticacao"],
    },
    "software architecture": {
        "frameworks": ["SOLID", "DDD", "Clean Architecture", "ADR", "CAP theorem"],
        "checklist": ["boundaries", "contratos", "consistencia", "observabilidade", "evolucao e rollback"],
        "red_flags": ["acoplamento circular", "dados compartilhados sem dono", "ausencia de estrategia de migracao"],
    },
}


class KnowledgeResearcher:
    async def research_domain(self, domain: str, role: str, task: str) -> ResearchResult:
        queries = [
            f"{role} checklist {task} best practices",
            f"{domain} senior engineer methodology frameworks",
            f"{domain} common mistakes critical errors",
            f"{domain} {task} standards norms certification",
        ]
        raw_sources: list[str] = []
        snippets: list[str] = []
        for query in queries:
            text = await self._search(query)
            if text:
                snippets.append(text[:1500])
                raw_sources.append(query)

        preset = self._preset_for(domain)
        knowledge_base = await self._synthesize(domain, role, task, snippets, preset)
        return ResearchResult(
            domain=domain,
            role=role,
            knowledge_base=knowledge_base,
            frameworks=preset["frameworks"],
            checklist=preset["checklist"],
            red_flags=preset["red_flags"],
            sources=raw_sources,
        )

    async def _search(self, query: str) -> str:
        def _run() -> str:
            try:
                from actions.web_search import run
                return str(run(query))
            except Exception:
                return ""

        return await asyncio.to_thread(_run)

    async def _synthesize(self, domain: str, role: str, task: str, snippets: list[str], preset: dict[str, list[str]]) -> str:
        prompt = (
            f"Sintetize conhecimento senior para dominio={domain}, role={role}, task={task}.\n"
            f"Frameworks base: {preset['frameworks']}.\n"
            f"Material pesquisado:\n" + "\n\n".join(snippets[:4])
        )
        try:
            from services.llm_service import call_llm
            return await asyncio.to_thread(
                call_llm,
                [
                    {"role": "system", "content": "Voce sintetiza conhecimento tecnico em formato estruturado, sem inventar normas."},
                    {"role": "user", "content": prompt},
                ],
                False,
                True,
            )
        except Exception:
            return (
                f"Conhecimento senior sintetizado para {domain}: aplicar {', '.join(preset['frameworks'])}; "
                f"verificar {', '.join(preset['checklist'])}; evitar {', '.join(preset['red_flags'])}."
            )

    def _preset_for(self, domain: str) -> dict[str, list[str]]:
        lower = domain.lower()
        for key, value in _DOMAIN_PRESETS.items():
            if key in lower or lower in key:
                return value
        return {
            "frameworks": ["best practices do dominio", "normas aplicaveis", "auditoria por checklist", "gestao de risco"],
            "checklist": ["escopo e premissas", "criterios de aceite", "conformidade", "riscos criticos", "evidencias e rastreabilidade"],
            "red_flags": ["ausencia de responsavel", "dados insuficientes", "nao conformidade sem mitigacao", "decisao sem evidencia"],
        }


async def research_domain(domain: str, role: str, task: str) -> ResearchResult:
    return await KnowledgeResearcher().research_domain(domain, role, task)

