"""
Code Analyzer Route — JARVIS v7.0
Analisa arquivos de qualquer linguagem: erros, bugs, qualidade, solução + explicação
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class AnalyzeRequest(BaseModel):
    file_path: str = ""
    query: str = ""
    code_snippet: str = ""
    error_message: str = ""
    language: str = ""


LANG_MAP: dict[str, str] = {
    '.py': 'Python', '.js': 'JavaScript', '.ts': 'TypeScript',
    '.jsx': 'React JSX', '.tsx': 'React TSX', '.java': 'Java',
    '.cpp': 'C++', '.c': 'C', '.cs': 'C#', '.go': 'Go',
    '.rs': 'Rust', '.php': 'PHP', '.rb': 'Ruby', '.swift': 'Swift',
    '.kt': 'Kotlin', '.dart': 'Dart/Flutter', '.html': 'HTML',
    '.css': 'CSS', '.sql': 'SQL', '.sh': 'Shell/Bash',
    '.ps1': 'PowerShell', '.yaml': 'YAML', '.yml': 'YAML',
    '.json': 'JSON', '.xml': 'XML', '.tf': 'Terraform', '.md': 'Markdown',
}


def _detect_language(file_path: str) -> str:
    if not file_path:
        return "Unknown"
    ext = Path(file_path).suffix.lower()
    return LANG_MAP.get(ext, 'Unknown')


def _resolve_file(file_path: str) -> tuple[Path | None, str | None]:
    """Resolve file path relative to common project roots. Returns (path, error)."""
    candidates = [
        Path(file_path),
        Path("backend") / file_path,
        Path("..") / file_path,
        Path("../backend") / file_path,
        Path(os.getcwd()) / file_path,
        Path(os.getcwd()).parent / file_path,
    ]

    # Also try just the filename in common dirs
    fname = Path(file_path).name
    for d in [".", "backend", "frontend", "src", "app"]:
        candidates.append(Path(d) / fname)

    for c in candidates:
        try:
            if c.exists() and c.is_file():
                return c, None
        except Exception:
            continue

    return None, f"Arquivo não encontrado: '{file_path}'"


def _parse_llm_json(raw: str) -> dict:
    """Extract JSON object from LLM response (handles markdown fences, extra text)."""
    # Remove markdown code fences
    raw = re.sub(r'```(?:json)?\s*', '', raw).replace('```', '')
    # Find JSON object
    m = re.search(r'\{[\s\S]+\}', raw)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return {}


@router.post("")
async def analyze_code(req: AnalyzeRequest):
    file_path = req.file_path.strip()
    code = req.code_snippet.strip()
    error_msg = req.error_message.strip()
    query = req.query.strip()

    lang = req.language or _detect_language(file_path)
    lines = 0
    resolved_path = file_path

    # Read file if path provided and no snippet given
    if file_path and not code:
        fpath, err = _resolve_file(file_path)
        if err:
            return {
                "voice_response": f"Não consegui encontrar o arquivo '{file_path}', Senhor. {err}",
                "display_type": "code_analysis",
                "data": {
                    "file": file_path, "language": lang, "lines": 0,
                    "error": err, "issues": [], "solution": "",
                    "explanation": err, "quality_score": 0, "summary": "Arquivo não encontrado",
                },
            }
        resolved_path = str(fpath)
        try:
            code = fpath.read_text(encoding='utf-8', errors='replace')
            lines = code.count('\n') + 1
        except Exception as e:
            return {
                "voice_response": f"Erro ao ler o arquivo, Senhor: {e}",
                "display_type": "code_analysis",
                "data": {"file": file_path, "error": str(e), "issues": [], "solution": "", "explanation": str(e)},
            }

    if not code:
        return {
            "voice_response": "Nenhum código fornecido para análise, Senhor. Especifique um arquivo ou trecho de código.",
            "display_type": "text_result",
            "data": {},
        }

    if not lines:
        lines = code.count('\n') + 1

    # Truncate for LLM (keep representative sample)
    MAX_CHARS = 3500
    code_for_llm = code[:MAX_CHARS]
    if len(code) > MAX_CHARS:
        code_for_llm += f"\n\n... [{len(code) - MAX_CHARS} chars omitidos — análise baseada nas primeiras {MAX_CHARS} chars]"

    from ai.client import get_ai_client
    from core.jarvis_persona import _build_identity

    system = f"""{_build_identity()}

MODO ANALISADOR DE CÓDIGO SÊNIOR (15+ anos de experiência):
Analise o código abaixo e retorne EXATAMENTE este JSON (sem texto extra, sem markdown):

{{
  "issues": [
    {{
      "severity": "critical|warning|info",
      "line": <número inteiro ou null>,
      "description": "<descrição clara do problema em PT>",
      "fix": "<solução concisa em PT>"
    }}
  ],
  "solution": "<código corrigido ou implementação da solução — coloque aqui o código funcional>",
  "explanation": "<explicação de 2-4 frases: qual é o problema principal, por que ocorre, e como a solução resolve>",
  "quality_score": <inteiro 0-100>,
  "summary": "<1 frase resumindo o estado geral do código>"
}}

Linguagem: {lang}
Arquivo: {resolved_path}
{f'Erro reportado pelo Senhor: {error_msg}' if error_msg else ''}
{f'Pergunta específica: {query}' if query else ''}

Regras:
- Detecte TODOS os bugs, erros de lógica, security issues e code smells
- Para critical: import circular, SQL injection, divisão por zero, null pointer, buffer overflow
- Para warning: variáveis não usadas, código morto, má formatação, performance issues
- Para info: sugestões de melhoria, documentação em falta, refatoração sugerida
- Se não há problemas, retorne issues: [] e quality_score: 95+
- Responda APENAS com o JSON válido, sem markdown
"""

    user_msg = f"Analise este código:\n\n```{lang.lower()}\n{code_for_llm}\n```"

    msgs = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_msg},
    ]

    try:
        raw = get_ai_client().call(msgs)
        analysis = _parse_llm_json(raw)

        if not analysis:
            analysis = {
                "issues": [],
                "solution": raw[:600] if raw else "Sem solução gerada",
                "explanation": raw[:300] if raw else "Análise não retornou JSON estruturado",
                "quality_score": 50,
                "summary": "Análise concluída (formato não estruturado)",
            }
    except Exception as e:
        analysis = {
            "issues": [],
            "solution": "",
            "explanation": f"Erro durante análise: {e}",
            "quality_score": 0,
            "summary": "Erro na análise",
        }

    issues = analysis.get("issues", [])
    critical_count = sum(1 for i in issues if i.get("severity") == "critical")
    warning_count = sum(1 for i in issues if i.get("severity") == "warning")
    info_count = sum(1 for i in issues if i.get("severity") == "info")
    score = analysis.get("quality_score", 50)

    if issues:
        voice = (
            f"Análise de '{Path(resolved_path).name}' concluída, Senhor. "
            f"Encontrei {len(issues)} problema{'s' if len(issues) != 1 else ''}: "
            f"{f'{critical_count} crítico' + ('s' if critical_count != 1 else '') + '. ' if critical_count else ''}"
            f"{f'{warning_count} aviso' + ('s' if warning_count != 1 else '') + '.' if warning_count else ''}"
            f" Score de qualidade: {score}/100."
        )
    else:
        voice = (
            f"Análise de '{Path(resolved_path).name}' concluída, Senhor. "
            f"Código parece correto e saudável. Score: {score}/100."
        )

    return {
        "voice_response": voice,
        "display_type": "code_analysis",
        "data": {
            "file": resolved_path,
            "filename": Path(resolved_path).name,
            "language": lang,
            "lines": lines,
            "quality_score": score,
            "issues": issues,
            "critical_count": critical_count,
            "warning_count": warning_count,
            "info_count": info_count,
            "solution": analysis.get("solution", ""),
            "explanation": analysis.get("explanation", ""),
            "summary": analysis.get("summary", ""),
            "raw_preview": code[:300] + "..." if len(code) > 300 else code,
        },
    }


# ── /analyze/explain — Explicar código sem análise de bugs ───────────────────
class ExplainCodeReq(BaseModel):
    file_path: str = ""
    code_snippet: str = ""
    language: str = ""
    question: str = ""
    level: str = "intermediate"  # beginner | intermediate | senior


@router.post("/explain")
async def explain_code(req: ExplainCodeReq):
    from ai.client import get_ai_client
    from core.jarvis_persona import _build_identity

    code = req.code_snippet
    if not code and req.file_path:
        fpath, err = _resolve_file(req.file_path)
        if err:
            return {"voice_response": f"Arquivo não encontrado: {req.file_path}", "display_type": "text_result", "data": {}}
        code = fpath.read_text(encoding="utf-8", errors="replace")[:4000]

    if not code:
        return {"voice_response": "Forneça código para explicar, Senhor.", "display_type": "text_result", "data": {}}

    lang = req.language or _detect_language(req.file_path)
    level_desc = {
        "beginner": "como se o utilizador nunca tivesse programado",
        "intermediate": "para um developer júnior com alguma experiência",
        "senior": "para um engenheiro sênior, com foco em trade-offs e padrões",
    }.get(req.level, "para um developer com experiência moderada")

    question_hint = f"\nPergunta específica do Senhor: {req.question}" if req.question else ""

    system = f"""{_build_identity()}
Explique o código {question_hint}
Nível: {level_desc}.
Retorne JSON: {{"title": "<nome do código>", "purpose": "<o que faz em 1 frase>", "how_it_works": "<explicação passo-a-passo>", "key_concepts": ["<conceito 1>", ...], "design_patterns": ["<padrão usado>"], "data_flow": "<como os dados fluem>", "gotchas": ["<armadilha ou detalhe não óbvio>"], "example_use": "<exemplo de uso>"}}
Sem markdown, JSON válido."""

    try:
        raw = get_ai_client().call([
            {"role": "system", "content": system},
            {"role": "user", "content": f"Explique este {lang}:\n\n```\n{code[:3000]}\n```"},
        ])
        data = _parse_llm_json(raw)
        if not data:
            data = {"purpose": raw[:200], "how_it_works": raw, "key_concepts": [], "design_patterns": [], "gotchas": []}
    except Exception as e:
        data = {"purpose": "Erro na explicação", "how_it_works": str(e), "key_concepts": [], "design_patterns": [], "gotchas": []}

    return {
        "voice_response": f"Explicação pronta, Senhor. {data.get('purpose', '')[:120]}",
        "display_type": "code_explanation",
        "data": {**data, "language": lang, "code_preview": code[:200]},
    }


# ── /analyze/security — Scan focado em segurança ─────────────────────────────
class SecurityScanReq(BaseModel):
    file_path: str = ""
    code_snippet: str = ""
    language: str = ""


@router.post("/security")
async def security_scan(req: SecurityScanReq):
    from ai.client import get_ai_client
    from core.jarvis_persona import _build_identity

    code = req.code_snippet
    if not code and req.file_path:
        fpath, err = _resolve_file(req.file_path)
        if err:
            return {"voice_response": f"Arquivo não encontrado: {req.file_path}", "display_type": "text_result", "data": {}}
        code = fpath.read_text(encoding="utf-8", errors="replace")[:5000]

    if not code:
        return {"voice_response": "Forneça código para scan de segurança, Senhor.", "display_type": "text_result", "data": {}}

    lang = req.language or _detect_language(req.file_path)

    system = f"""{_build_identity()}
MODO: PENETRATION TESTER + SECURITY AUDITOR SÊNIOR (OWASP Top 10, CWE, CVSS).
Analise rigorosamente em busca de: SQL Injection, XSS, CSRF, RCE, IDOR, Path Traversal, XXE, SSRF, Hardcoded Secrets, Insecure Dependencies, Auth Bypass, Data Exposure.
Retorne JSON: {{"risk_score": <0-10>, "risk_level": "critical|high|medium|low|minimal", "vulnerabilities": [{{"cwe": "CWE-XXX", "owasp": "A1-A10", "severity": "critical|high|medium|low", "line": <n or null>, "description": "<vuln>", "exploit": "<como seria explorada>", "fix": "<código seguro>", "references": ["<cve ou link>"]}}], "secure_coding_score": <0-100>, "recommendations": ["<recomendação de segurança>"], "compliance_notes": {{"owasp": "<conformidade>", "pci_dss": "<se aplicável>", "gdpr": "<se aplicável>"}}}}
Sem markdown, JSON válido."""

    try:
        raw = get_ai_client().call([
            {"role": "system", "content": system},
            {"role": "user", "content": f"Faça security scan deste {lang}:\n\n```\n{code[:4000]}\n```"},
        ])
        data = _parse_llm_json(raw)
        if not data:
            data = {"risk_score": 5, "risk_level": "medium", "vulnerabilities": [], "recommendations": [raw[:200]], "secure_coding_score": 50}
    except Exception as e:
        data = {"risk_score": 0, "risk_level": "unknown", "vulnerabilities": [], "recommendations": [f"Erro: {e}"], "secure_coding_score": 0}

    vulns = data.get("vulnerabilities", [])
    critical_v = sum(1 for v in vulns if v.get("severity") == "critical")
    high_v = sum(1 for v in vulns if v.get("severity") == "high")
    risk_level = data.get("risk_level", "unknown")
    risk_score = data.get("risk_score", 0)

    voice = (
        f"Security scan concluído, Senhor. "
        f"Risco: {risk_level.upper()} ({risk_score}/10). "
        f"{len(vulns)} vulnerabilidade{'s' if len(vulns) != 1 else ''} detectada{'s' if len(vulns) != 1 else ''}. "
        f"{f'{critical_v} crítica' + ('s' if critical_v != 1 else '') + '. ' if critical_v else ''}"
        f"{f'{high_v} alta' + ('s' if high_v != 1 else '') + '.' if high_v else ''}"
    )

    return {
        "voice_response": voice,
        "display_type": "security_scan",
        "data": {**data, "language": lang, "lines_scanned": code.count('\n') + 1},
    }


# ── /analyze/complexity — Métricas de complexidade ───────────────────────────
class ComplexityReq(BaseModel):
    file_path: str = ""
    code_snippet: str = ""
    language: str = ""


@router.post("/complexity")
async def analyze_complexity(req: ComplexityReq):
    from ai.client import get_ai_client
    from core.jarvis_persona import _build_identity

    code = req.code_snippet
    if not code and req.file_path:
        fpath, err = _resolve_file(req.file_path)
        if err:
            return {"voice_response": f"Arquivo não encontrado, Senhor.", "display_type": "text_result", "data": {}}
        code = fpath.read_text(encoding="utf-8", errors="replace")[:5000]

    if not code:
        return {"voice_response": "Forneça código para análise de complexidade, Senhor.", "display_type": "text_result", "data": {}}

    lang = req.language or _detect_language(req.file_path)
    lines = code.count('\n') + 1

    system = f"""{_build_identity()}
MODO: ENGENHEIRO DE QUALIDADE DE SOFTWARE.
Analise métricas de complexidade do código.
Retorne JSON: {{"cyclomatic_complexity": <número>, "cognitive_complexity": <número>, "lines_of_code": {lines}, "comment_ratio": "<x%>", "function_count": <n>, "class_count": <n>, "max_nesting_depth": <n>, "avg_function_length": <n>, "maintainability_index": <0-100>, "technical_debt": "<estimativa ex: 2h>", "hotspots": [{{"location": "<função/classe>", "issue": "<problema>", "priority": "high|medium|low"}}], "refactoring_suggestions": ["<sugestão>"]}}
Sem markdown, JSON válido."""

    try:
        raw = get_ai_client().call([
            {"role": "system", "content": system},
            {"role": "user", "content": f"Analise complexidade deste {lang}:\n\n```\n{code[:4000]}\n```"},
        ])
        data = _parse_llm_json(raw)
        if not data:
            data = {"cyclomatic_complexity": 0, "maintainability_index": 50, "hotspots": [], "refactoring_suggestions": [raw[:200]]}
    except Exception as e:
        data = {"error": str(e), "cyclomatic_complexity": 0, "maintainability_index": 0}

    mi = data.get("maintainability_index", 0)
    cc = data.get("cyclomatic_complexity", 0)
    return {
        "voice_response": f"Análise de complexidade concluída, Senhor. Índice de manutenibilidade: {mi}/100. Complexidade ciclomática: {cc}.",
        "display_type": "complexity_report",
        "data": {**data, "language": lang, "lines_of_code": lines},
    }
