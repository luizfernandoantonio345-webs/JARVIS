from __future__ import annotations

import re

from pydantic import BaseModel


class DomainRequest(BaseModel):
    raw_input: str
    detected_domain: str = "general"
    detected_role: str = "general assistant"
    task_type: str = "analysis"
    confidence: float = 0.0
    requires_research: bool = True


class DomainDetector:
    TASK_PATTERNS = [
        (r"code review|revis[aã]o|review", "code review"),
        (r"analise|analisar|avalie|auditoria|audit", "analysis"),
        (r"implemente|crie|construa|build|implement", "implementation"),
        (r"diagn[oó]stico|debug|corrija|erro", "diagnosis"),
        (r"pentest|seguran[cç]a|vulnerabilidade", "security audit"),
    ]

    ROLE_PATTERNS = [
        (r"s[eê]nior|senior", "senior"),
        (r"especialista", "specialist"),
        (r"auditor", "auditor"),
        (r"consultor", "consultant"),
        (r"engenheiro", "engineer"),
    ]

    async def detect(self, user_input: str) -> DomainRequest:
        text = user_input.strip()
        lower = text.lower()
        domain, role, conf = self._detect_core(lower)
        if not domain:
            domain, role, conf = self._detect_dynamic(lower)
        task = self._detect_task(lower)
        role = self._expand_role(role, domain)
        requires = True
        if conf >= 0.7:
            try:
                from .domain_memory import DomainMemory
                requires = await DomainMemory().load(domain) is None
            except Exception:
                requires = True
        if self._is_core(domain):
            requires = False
        if conf < 0.7:
            requires = True
        return DomainRequest(
            raw_input=text,
            detected_domain=domain or "general",
            detected_role=role or "senior specialist",
            task_type=task,
            confidence=conf,
            requires_research=requires,
        )

    def _detect_core(self, lower: str) -> tuple[str | None, str | None, float]:
        try:
            from experts import CORE_EXPERTS
            for domain, expert in CORE_EXPERTS.items():
                for alias in expert.ALIASES:
                    alias_lower = alias.lower()
                    if len(alias_lower) <= 4:
                        matched = re.search(rf"\b{re.escape(alias_lower)}\b", lower) is not None
                    else:
                        matched = alias_lower in lower
                    if matched:
                        return domain, f"senior {domain} expert", 0.92
        except Exception:
            pass
        return None, None, 0.0

    def _detect_dynamic(self, lower: str) -> tuple[str, str, float]:
        examples = [
            (r"engenharia civil|civil engineering|projeto estrutural", "civil engineering", "senior civil engineer", 0.9),
            (r"pentest|penetration testing", "penetration testing", "senior pentester", 0.9),
            (r"advogado tribut[aá]rio|direito tribut[aá]rio", "tax law", "senior tax lawyer", 0.86),
            (r"laudo m[eé]dico|medicina|m[eé]dico", "medical review", "senior medical specialist", 0.78),
            (r"contrato|jur[ií]dico|advogado", "legal analysis", "senior legal consultant", 0.78),
        ]
        for pattern, domain, role, conf in examples:
            if re.search(pattern, lower):
                return domain, role, conf
        match = re.search(r"seja um(?:a)?\s+(.+?)\s+e\s+(.+)", lower)
        if match:
            domain = match.group(1).strip()
            return domain, f"senior {domain}", 0.75
        match = re.search(r"como\s+(?:engenheiro|especialista|s[eê]nior)\s+de\s+(.+)", lower)
        if match:
            domain = match.group(1).strip()
            return domain, f"senior {domain} specialist", 0.72
        return "general", "general assistant", 0.2

    def _detect_task(self, lower: str) -> str:
        for pattern, task in self.TASK_PATTERNS:
            if re.search(pattern, lower):
                return task
        return "analysis"

    def _expand_role(self, role: str | None, domain: str) -> str:
        if role and role.startswith("senior"):
            return role
        for pattern, name in self.ROLE_PATTERNS:
            if role and re.search(pattern, role):
                return f"{name} {domain}".strip()
        return role or f"senior {domain} expert"

    def _is_core(self, domain: str) -> bool:
        return domain in {"software engineering", "cybersecurity", "quality engineering"}
