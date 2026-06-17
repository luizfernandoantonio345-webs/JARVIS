"""
Generate Route — JARVIS v8.0
15 sub-endpoints: código, testes, docs, regex, diagrams, API spec, Dockerfile,
README, refactor, convert, explain, fix, review, optimize, summarize.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

_LANG_EXTS = {
    'python': '.py', 'javascript': '.js', 'typescript': '.ts',
    'java': '.java', 'go': '.go', 'rust': '.rs', 'php': '.php',
    'ruby': '.rb', 'swift': '.swift', 'kotlin': '.kt', 'dart': '.dart',
    'c#': '.cs', 'csharp': '.cs', 'cpp': '.cpp', 'c': '.c',
    'shell': '.sh', 'bash': '.sh', 'powershell': '.ps1',
    'sql': '.sql', 'html': '.html', 'css': '.css', 'yaml': '.yaml',
}

_LANG_MAP_EXT = {v: k for k, v in _LANG_EXTS.items()}


def _call_llm(system: str, user: str, timeout: int = 90) -> str:
    from ai.client import get_ai_client
    return get_ai_client().call([
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ])


def _detect_lang(code: str, hint: str = "") -> str:
    if hint:
        return hint.lower()
    if "def " in code and "import " in code:
        return "python"
    if "function " in code or "const " in code or "let " in code:
        return "javascript"
    if "public class" in code or "System.out" in code:
        return "java"
    if "func " in code and "package " in code:
        return "go"
    if "fn " in code and "let mut" in code:
        return "rust"
    return "python"


# ── 1. Gerar código a partir de descrição ────────────────────────────────────
class GenerateCodeReq(BaseModel):
    description: str
    language: str = "python"
    framework: str = ""
    style: str = "clean"  # clean | minimal | documented | enterprise


@router.post("/code")
async def generate_code(req: GenerateCodeReq):
    lang_hint = f"Framework: {req.framework}. " if req.framework else ""
    sys_p = f"""Você é um engenheiro sênior. {lang_hint}
Gere código {req.language} de alta qualidade, estilo {req.style}.
Retorne APENAS o código funcional, sem explicações, sem markdown, sem blocos de código.
O código deve ser completo, bem estruturado e pronto para produção."""

    raw = _call_llm(sys_p, f"Implemente: {req.description}")

    # Strip markdown fences if LLM disobeyed
    raw = re.sub(r'```[\w]*\n?', '', raw).replace('```', '').strip()

    return {
        "voice_response": f"Código {req.language} gerado com sucesso, Senhor.",
        "display_type": "generated_code",
        "data": {
            "code": raw,
            "language": req.language,
            "description": req.description,
            "framework": req.framework,
        },
    }


# ── 2. Gerar testes unitários ─────────────────────────────────────────────────
class GenerateTestsReq(BaseModel):
    code: str = ""
    file_path: str = ""
    language: str = ""
    framework: str = ""  # pytest | jest | junit | go test | etc.


@router.post("/tests")
async def generate_tests(req: GenerateTestsReq):
    code = req.code
    if not code and req.file_path:
        try:
            p = Path(req.file_path)
            if not p.exists():
                p = Path("backend") / req.file_path
            code = p.read_text(encoding="utf-8", errors="replace")[:4000]
        except Exception:
            return {"voice_response": "Não consegui ler o arquivo, Senhor.", "display_type": "text_result", "data": {}}

    if not code:
        return {"voice_response": "Forneça o código ou caminho do arquivo, Senhor.", "display_type": "text_result", "data": {}}

    lang = req.language or _detect_lang(code)
    fw_map = {"python": "pytest", "javascript": "jest", "typescript": "jest",
              "java": "junit", "go": "go test", "rust": "cargo test", "kotlin": "junit"}
    framework = req.framework or fw_map.get(lang, "xunit")

    sys_p = f"""Você é um especialista em testes de software ({framework}).
Gere uma suite de testes COMPLETA e PROFISSIONAL para o código fornecido.
Inclua: testes unitários, edge cases, erros esperados, mocks quando necessário.
Retorne APENAS o código de teste, sem markdown, pronto para executar."""

    raw = _call_llm(sys_p, f"Gere testes {framework} para:\n\n{code[:3000]}")
    raw = re.sub(r'```[\w]*\n?', '', raw).replace('```', '').strip()

    return {
        "voice_response": f"Suite de testes {framework} gerada, Senhor. Pronto para executar.",
        "display_type": "generated_code",
        "data": {
            "code": raw,
            "language": lang,
            "framework": framework,
            "type": "tests",
        },
    }


# ── 3. Gerar documentação ─────────────────────────────────────────────────────
class GenerateDocsReq(BaseModel):
    code: str = ""
    file_path: str = ""
    format: str = "markdown"  # markdown | docstring | jsdoc | swagger
    language: str = ""


@router.post("/docs")
async def generate_docs(req: GenerateDocsReq):
    code = req.code
    if not code and req.file_path:
        try:
            p = Path(req.file_path)
            if not p.exists():
                p = Path("backend") / req.file_path
            code = p.read_text(encoding="utf-8", errors="replace")[:4000]
        except Exception:
            pass

    if not code:
        return {"voice_response": "Forneça código para documentar, Senhor.", "display_type": "text_result", "data": {}}

    lang = req.language or _detect_lang(code)
    sys_p = f"""Você é um technical writer sênior.
Gere documentação {req.format} COMPLETA e PROFISSIONAL para o código.
Inclua: descrição, parâmetros, retornos, exemplos de uso, notas de segurança.
Seja específico e útil, não genérico."""

    raw = _call_llm(sys_p, f"Documente este {lang}:\n\n{code[:3000]}")

    return {
        "voice_response": f"Documentação {req.format} gerada com sucesso, Senhor.",
        "display_type": "generated_code",
        "data": {
            "code": raw,
            "language": req.format,
            "type": "documentation",
        },
    }


# ── 4. Gerar regex ────────────────────────────────────────────────────────────
class GenerateRegexReq(BaseModel):
    description: str
    language: str = "python"
    examples: list[str] = []
    counter_examples: list[str] = []


@router.post("/regex")
async def generate_regex(req: GenerateRegexReq):
    examples_hint = ""
    if req.examples:
        examples_hint += f"\nDeve CASAR: {req.examples}"
    if req.counter_examples:
        examples_hint += f"\nNão deve casar: {req.counter_examples}"

    sys_p = """Você é um especialista em expressões regulares.
Retorne um JSON com: {"pattern": "<regex>", "flags": "<flags se necessário>", "explanation": "<explicação linha por linha>", "examples": ["<exemplo válido 1>", "<exemplo válido 2>"], "python_code": "<código Python completo para usar>", "javascript_code": "<código JS completo para usar>"}
Sem markdown, apenas JSON válido."""

    raw = _call_llm(sys_p, f"Crie regex para: {req.description}{examples_hint}")
    raw = re.sub(r'```[\w]*\n?', '', raw).replace('```', '').strip()

    try:
        data = json.loads(raw)
    except Exception:
        m = re.search(r'\{[\s\S]+\}', raw)
        try:
            data = json.loads(m.group()) if m else {"pattern": raw.strip(), "explanation": "Veja o padrão gerado acima."}
        except Exception:
            data = {"pattern": raw[:200], "explanation": "Padrão gerado."}

    pattern = data.get("pattern", "")
    return {
        "voice_response": f"Regex gerado, Senhor: {pattern[:60]}{'…' if len(pattern) > 60 else ''}",
        "display_type": "generated_code",
        "data": {**data, "language": req.language, "type": "regex"},
    }


# ── 5. Gerar diagrama Mermaid ─────────────────────────────────────────────────
class GenerateDiagramReq(BaseModel):
    description: str
    type: str = "auto"  # flowchart | sequence | class | erd | gantt | mindmap | auto


@router.post("/diagram")
async def generate_diagram(req: GenerateDiagramReq):
    dtype = req.type
    if dtype == "auto":
        d = req.description.lower()
        if any(w in d for w in ["fluxo", "processo", "flow", "etapas"]):
            dtype = "flowchart"
        elif any(w in d for w in ["classe", "class", "herança", "objeto"]):
            dtype = "classDiagram"
        elif any(w in d for w in ["sequência", "api", "request", "response", "chamada"]):
            dtype = "sequenceDiagram"
        elif any(w in d for w in ["banco", "tabela", "entidade", "erd", "database", "schema"]):
            dtype = "erDiagram"
        elif any(w in d for w in ["gantt", "cronograma", "prazo", "sprint"]):
            dtype = "gantt"
        elif any(w in d for w in ["mente", "mapa", "mind"]):
            dtype = "mindmap"
        else:
            dtype = "flowchart"

    sys_p = f"""Você é um especialista em diagramas Mermaid.
Gere um diagrama {dtype} COMPLETO e PROFISSIONAL para o que foi descrito.
Retorne APENAS o código Mermaid válido, sem markdown fences, sem explicações.
O diagrama deve começar com '{dtype}' e ser completamente funcional."""

    raw = _call_llm(sys_p, f"Crie diagrama Mermaid para: {req.description}")
    raw = re.sub(r'```(?:mermaid)?\n?', '', raw).replace('```', '').strip()

    # Ensure starts with diagram type
    if not raw.startswith(dtype) and not any(raw.startswith(t) for t in ["flowchart", "sequenceDiagram", "classDiagram", "erDiagram", "gantt", "mindmap"]):
        raw = f"{dtype} TD\n{raw}"

    return {
        "voice_response": f"Diagrama {dtype} gerado com sucesso, Senhor. Renderizando no painel.",
        "display_type": "mermaid_diagram",
        "data": {
            "mermaid": raw,
            "type": dtype,
            "description": req.description,
        },
    }


# ── 6. Gerar especificação de API REST ────────────────────────────────────────
class GenerateApiReq(BaseModel):
    description: str
    style: str = "rest"  # rest | graphql | grpc
    language: str = "python"
    framework: str = "fastapi"


@router.post("/api")
async def generate_api(req: GenerateApiReq):
    sys_p = f"""Você é um arquiteto de APIs sênior.
Gere uma especificação OpenAPI 3.1 + código {req.framework} ({req.language}) COMPLETO.
Inclua: endpoints, schemas Pydantic, autenticação JWT, exemplos de request/response, error handling.
Retorne JSON com: {{"openapi_spec": {{...}}, "code": "<código {req.framework}>", "endpoints_summary": ["<endpoint 1>", ...]}}
Sem markdown, apenas JSON válido."""

    raw = _call_llm(sys_p, f"Crie API para: {req.description}")
    raw = re.sub(r'```[\w]*\n?', '', raw).replace('```', '').strip()

    try:
        data = json.loads(raw)
    except Exception:
        # Fallback: return raw as code
        data = {"code": raw, "endpoints_summary": ["Ver código gerado"]}

    endpoints = data.get("endpoints_summary", [])
    return {
        "voice_response": f"Especificação {req.style.upper()} gerada, Senhor. {len(endpoints)} endpoint{'s' if len(endpoints) != 1 else ''} definido{'s' if len(endpoints) != 1 else ''}.",
        "display_type": "generated_code",
        "data": {**data, "type": "api_spec", "language": req.language, "framework": req.framework},
    }


# ── 7. Gerar Dockerfile ───────────────────────────────────────────────────────
class GenerateDockerReq(BaseModel):
    description: str
    language: str = "python"
    port: int = 8000
    multi_stage: bool = True
    base_image: str = ""


@router.post("/docker")
async def generate_dockerfile(req: GenerateDockerReq):
    multi_hint = "Multi-stage build (builder + final) para imagem mínima." if req.multi_stage else "Single-stage build."
    base = f"Base: {req.base_image}." if req.base_image else ""

    sys_p = f"""Você é um especialista DevOps/Docker sênior.
{multi_hint} {base}
Gere um Dockerfile PROFISSIONAL para {req.language} na porta {req.port}.
Inclua: .dockerignore recomendado, docker-compose.yml, comando de build/run.
Retorne JSON: {{"dockerfile": "<conteúdo>", "dockerignore": "<conteúdo>", "docker_compose": "<conteúdo>", "commands": {{"build": "<cmd>", "run": "<cmd>", "compose": "<cmd>"}}}}
Sem markdown, JSON válido."""

    raw = _call_llm(sys_p, f"Crie Docker para: {req.description}")
    raw = re.sub(r'```[\w]*\n?', '', raw).replace('```', '').strip()

    try:
        data = json.loads(raw)
    except Exception:
        data = {"dockerfile": raw, "commands": {"build": f"docker build -t app .", "run": f"docker run -p {req.port}:{req.port} app"}}

    return {
        "voice_response": f"Dockerfile {'multi-stage ' if req.multi_stage else ''}gerado para {req.language}, Senhor.",
        "display_type": "generated_code",
        "data": {**data, "type": "docker", "language": req.language, "port": req.port},
    }


# ── 8. Gerar README ───────────────────────────────────────────────────────────
class GenerateReadmeReq(BaseModel):
    project_name: str
    description: str
    language: str = ""
    features: list[str] = []
    has_api: bool = False
    has_docker: bool = False
    license: str = "MIT"


@router.post("/readme")
async def generate_readme(req: GenerateReadmeReq):
    feats = "\n".join(f"- {f}" for f in req.features) if req.features else ""
    extras = []
    if req.has_api:
        extras.append("Inclua seção de API com exemplos de endpoints.")
    if req.has_docker:
        extras.append("Inclua seção de Docker com build/run.")

    sys_p = f"""Você é um technical writer sênior.
Crie um README.md PROFISSIONAL e COMPLETO para o projeto.
Licença: {req.license}. {' '.join(extras)}
Inclua: badges, instalação, uso, configuração, contribuição, licença.
Retorne APENAS o markdown do README, sem explicações."""

    user_msg = f"Projeto: {req.project_name}\nDescrição: {req.description}"
    if feats:
        user_msg += f"\nFeatures:\n{feats}"

    raw = _call_llm(sys_p, user_msg)

    return {
        "voice_response": f"README para '{req.project_name}' gerado com sucesso, Senhor.",
        "display_type": "generated_code",
        "data": {
            "code": raw,
            "language": "markdown",
            "filename": "README.md",
            "type": "readme",
        },
    }


# ── 9. Refatorar código ───────────────────────────────────────────────────────
class RefactorReq(BaseModel):
    code: str
    language: str = ""
    goals: list[str] = []  # ["performance", "readability", "solid", "dry"]
    target_pattern: str = ""  # "clean architecture" | "repository pattern" | etc.


@router.post("/refactor")
async def refactor_code(req: RefactorReq):
    lang = req.language or _detect_lang(req.code)
    goals_hint = f"Objetivos: {', '.join(req.goals)}." if req.goals else ""
    pattern_hint = f"Padrão alvo: {req.target_pattern}." if req.target_pattern else ""

    sys_p = f"""Você é um engenheiro de software sênior especialista em refatoração.
{goals_hint} {pattern_hint}
Refatore o código {lang} seguindo SOLID, Clean Code, DRY, KISS.
Retorne JSON: {{"original_issues": ["<problema 1>", ...], "refactored_code": "<código refatorado completo>", "changes": ["<mudança 1>", ...], "improvement_score": <0-100>}}
Sem markdown, JSON válido."""

    raw = _call_llm(sys_p, f"Refatore:\n\n{req.code[:3000]}")
    raw = re.sub(r'```[\w]*\n?', '', raw).replace('```', '').strip()

    try:
        data = json.loads(raw)
    except Exception:
        data = {"refactored_code": raw, "changes": ["Código refatorado"], "improvement_score": 80}

    changes_count = len(data.get("changes", []))
    score = data.get("improvement_score", 0)
    return {
        "voice_response": f"Refatoração concluída, Senhor. {changes_count} melhorias aplicadas. Score: {score}/100.",
        "display_type": "generated_code",
        "data": {**data, "type": "refactored", "language": lang},
    }


# ── 10. Converter código entre linguagens ─────────────────────────────────────
class ConvertCodeReq(BaseModel):
    code: str
    from_language: str
    to_language: str
    preserve_comments: bool = True
    idiomatic: bool = True  # use target language idioms, not literal translation


@router.post("/convert")
async def convert_code(req: ConvertCodeReq):
    idiomatic_hint = "Use idiomas e padrões nativos da linguagem alvo, não tradução literal." if req.idiomatic else "Tradução próxima do original."
    comments_hint = "Preserve todos os comentários, adaptando-os." if req.preserve_comments else "Não inclua comentários."

    sys_p = f"""Você é um engenheiro poliglota sênior.
{idiomatic_hint} {comments_hint}
Converta de {req.from_language} para {req.to_language} de forma COMPLETA e FUNCIONAL.
Retorne JSON: {{"converted_code": "<código convertido>", "notes": ["<nota 1>", ...], "breaking_changes": ["<mudança significativa>", ...]}}
Sem markdown, JSON válido."""

    raw = _call_llm(sys_p, f"Converta este {req.from_language} para {req.to_language}:\n\n{req.code[:3000]}")
    raw = re.sub(r'```[\w]*\n?', '', raw).replace('```', '').strip()

    try:
        data = json.loads(raw)
    except Exception:
        data = {"converted_code": raw, "notes": [f"Convertido de {req.from_language} para {req.to_language}"], "breaking_changes": []}

    notes_count = len(data.get("notes", []))
    return {
        "voice_response": f"Código convertido de {req.from_language} para {req.to_language}, Senhor. {notes_count} nota{'s' if notes_count != 1 else ''} de conversão.",
        "display_type": "generated_code",
        "data": {**data, "type": "converted", "language": req.to_language, "from": req.from_language},
    }


# ── 11. Explicar conceito / código ────────────────────────────────────────────
class ExplainReq(BaseModel):
    topic: str = ""
    code: str = ""
    level: str = "intermediate"  # beginner | intermediate | senior | expert
    language: str = "pt-BR"


@router.post("/explain")
async def explain_concept(req: ExplainReq):
    content = req.code if req.code else req.topic
    if not content:
        return {"voice_response": "Especifique o que quer explicado, Senhor.", "display_type": "text_result", "data": {}}

    is_code = bool(req.code)
    level_map = {
        "beginner": "Explique como se fosse para alguém que nunca programou. Use analogias simples.",
        "intermediate": "Explique para um desenvolvedor júnior. Balance teoria e prática.",
        "senior": "Explique para um sênior. Foque em trade-offs, performance e arquitetura.",
        "expert": "Explique em nível de especialista. Detalhes de implementação, edge cases, internos do sistema.",
    }

    sys_p = f"""Você é um professor de tecnologia sênior e mentor excepcional.
{level_map.get(req.level, level_map['intermediate'])}
Retorne JSON: {{"summary": "<1-2 frases>", "explanation": "<explicação principal>", "key_concepts": ["<conceito 1>", ...], "examples": ["<exemplo 1>", ...], "common_mistakes": ["<erro comum>", ...], "further_reading": ["<recurso 1>", ...]}}
Responda em {req.language}. Sem markdown, JSON válido."""

    user_msg = f"Explique {'este código' if is_code else 'este conceito'}: {content[:2000]}"
    raw = _call_llm(sys_p, user_msg)
    raw = re.sub(r'```[\w]*\n?', '', raw).replace('```', '').strip()

    try:
        data = json.loads(raw)
    except Exception:
        data = {"summary": content[:100], "explanation": raw[:500], "key_concepts": [], "examples": [], "common_mistakes": [], "further_reading": []}

    summary = data.get("summary", "")
    return {
        "voice_response": f"Explicação pronta, Senhor. {summary[:120]}",
        "display_type": "explanation",
        "data": {**data, "level": req.level, "type": "code_explanation" if is_code else "concept_explanation"},
    }


# ── 12. Corrigir código com erro ──────────────────────────────────────────────
class FixCodeReq(BaseModel):
    code: str
    error: str = ""
    language: str = ""
    context: str = ""


@router.post("/fix")
async def fix_code(req: FixCodeReq):
    lang = req.language or _detect_lang(req.code)
    error_hint = f"\nErro reportado:\n{req.error}" if req.error else ""
    ctx_hint = f"\nContexto: {req.context}" if req.context else ""

    sys_p = f"""Você é um debugger e engenheiro sênior especialista em {lang}.
Corrija o código, explicando cada problema encontrado.
Retorne JSON: {{"fixed_code": "<código corrigido completo>", "issues_found": [{{"line": <n>, "problem": "<problema>", "fix": "<como corrigido>"}}], "root_cause": "<causa raiz principal>", "prevention": "<como evitar no futuro>"}}
Sem markdown, JSON válido."""

    raw = _call_llm(sys_p, f"Corrija este {lang}:{error_hint}{ctx_hint}\n\n{req.code[:3000]}")
    raw = re.sub(r'```[\w]*\n?', '', raw).replace('```', '').strip()

    try:
        data = json.loads(raw)
    except Exception:
        data = {"fixed_code": raw, "issues_found": [], "root_cause": req.error or "Ver código corrigido", "prevention": ""}

    n_issues = len(data.get("issues_found", []))
    return {
        "voice_response": f"Código corrigido, Senhor. {n_issues} problema{'s' if n_issues != 1 else ''} resolvido{'s' if n_issues != 1 else ''}.",
        "display_type": "generated_code",
        "data": {**data, "type": "fixed", "language": lang},
    }


# ── 13. Code review ───────────────────────────────────────────────────────────
class ReviewReq(BaseModel):
    code: str
    language: str = ""
    pr_context: str = ""  # descrição do PR / contexto da mudança
    focus: list[str] = []  # ["security", "performance", "readability", "testing"]


@router.post("/review")
async def code_review(req: ReviewReq):
    lang = req.language or _detect_lang(req.code)
    focus_hint = f"Foco especial em: {', '.join(req.focus)}." if req.focus else ""
    pr_hint = f"Contexto do PR: {req.pr_context}." if req.pr_context else ""

    sys_p = f"""Você é um tech lead sênior fazendo code review rigoroso.
{focus_hint} {pr_hint}
Revise como se fosse aprovar/rejeitar um PR em produção de alto impacto.
Retorne JSON: {{"verdict": "approve|request_changes|needs_discussion", "score": <0-100>, "blocking_issues": [{{"line": <n>, "severity": "critical|major|minor", "issue": "<problema>", "suggestion": "<sugestão>"}}], "non_blocking": [{{"type": "style|optimization|readability", "note": "<nota>"}}], "praise": ["<ponto positivo>"], "overall_feedback": "<parágrafo de feedback geral>"}}
Sem markdown, JSON válido."""

    raw = _call_llm(sys_p, f"Revise este {lang}:\n\n{req.code[:3000]}")
    raw = re.sub(r'```[\w]*\n?', '', raw).replace('```', '').strip()

    try:
        data = json.loads(raw)
    except Exception:
        data = {"verdict": "needs_discussion", "score": 70, "blocking_issues": [], "non_blocking": [], "praise": [], "overall_feedback": raw[:300]}

    verdict = data.get("verdict", "needs_discussion")
    score = data.get("score", 0)
    blocking = len(data.get("blocking_issues", []))
    verdict_voice = {"approve": "APROVADO", "request_changes": "SOLICITA MUDANÇAS", "needs_discussion": "PRECISA DISCUSSÃO"}.get(verdict, verdict)

    return {
        "voice_response": f"Code review concluído, Senhor. Veredicto: {verdict_voice}. Score: {score}/100. {blocking} issue{'s' if blocking != 1 else ''} bloqueante{'s' if blocking != 1 else ''}.",
        "display_type": "code_review",
        "data": {**data, "language": lang, "type": "review"},
    }


# ── 14. Optimizar código ──────────────────────────────────────────────────────
class OptimizeReq(BaseModel):
    code: str
    language: str = ""
    target: str = "balanced"  # performance | memory | readability | bundle_size | balanced
    constraints: str = ""


@router.post("/optimize")
async def optimize_code(req: OptimizeReq):
    lang = req.language or _detect_lang(req.code)
    target_map = {
        "performance": "Maximize velocidade de execução. Profile mental, O(n) → O(log n) onde possível.",
        "memory": "Minimize uso de memória. Prefira iteradores, lazy evaluation, evite cópias.",
        "readability": "Maximize legibilidade. SOLID, Clean Code, nomes expressivos, funções pequenas.",
        "bundle_size": "Minimize tamanho do bundle. Tree-shaking, imports específicos, sem deps desnecessárias.",
        "balanced": "Balance entre performance, legibilidade e manutenibilidade.",
    }

    sys_p = f"""Você é um engenheiro de performance sênior.
Objetivo: {target_map.get(req.target, target_map['balanced'])}
{f'Restrições: {req.constraints}.' if req.constraints else ''}
Retorne JSON: {{"optimized_code": "<código otimizado completo>", "optimizations": [{{"type": "<tipo>", "description": "<o que mudou>", "impact": "high|medium|low"}}], "performance_gain": "<estimativa %/fator>", "complexity_before": "<O(?)>", "complexity_after": "<O(?)>"}}
Sem markdown, JSON válido."""

    raw = _call_llm(sys_p, f"Otimize este {lang} para {req.target}:\n\n{req.code[:3000]}")
    raw = re.sub(r'```[\w]*\n?', '', raw).replace('```', '').strip()

    try:
        data = json.loads(raw)
    except Exception:
        data = {"optimized_code": raw, "optimizations": [], "performance_gain": "desconhecido", "complexity_before": "?", "complexity_after": "?"}

    n_opts = len(data.get("optimizations", []))
    gain = data.get("performance_gain", "")
    return {
        "voice_response": f"Código otimizado para {req.target}, Senhor. {n_opts} otimização{'ões' if n_opts != 1 else ''} aplicada{'s' if n_opts != 1 else ''}. Ganho: {gain}.",
        "display_type": "generated_code",
        "data": {**data, "type": "optimized", "language": lang, "target": req.target},
    }


# ── 15. Resumir texto / código / documento ────────────────────────────────────
class SummarizeReq(BaseModel):
    text: str = ""
    file_path: str = ""
    length: str = "medium"  # brief | medium | detailed
    format: str = "bullets"  # bullets | paragraph | structured


@router.post("/summarize")
async def summarize_text(req: SummarizeReq):
    content = req.text
    if not content and req.file_path:
        try:
            p = Path(req.file_path)
            if not p.exists():
                p = Path("backend") / req.file_path
            content = p.read_text(encoding="utf-8", errors="replace")[:6000]
        except Exception:
            pass

    if not content:
        return {"voice_response": "Forneça texto ou caminho para resumir, Senhor.", "display_type": "text_result", "data": {}}

    length_map = {
        "brief": "Máximo 3 bullet points ou 2 frases. Extremamente conciso.",
        "medium": "5-8 bullet points ou 1 parágrafo. Balance detail e brevidade.",
        "detailed": "10+ pontos ou 3 parágrafos. Capture todos os pontos importantes.",
    }

    format_map = {
        "bullets": "Formato: lista de bullet points com •",
        "paragraph": "Formato: parágrafos contínuos",
        "structured": "Formato: JSON com {\"tldr\": \"...\", \"key_points\": [...], \"action_items\": [...], \"conclusion\": \"...\"}",
    }

    sys_p = f"""Você é um especialista em síntese de informação.
{length_map.get(req.length, length_map['medium'])}
{format_map.get(req.format, format_map['bullets'])}
{'Retorne apenas o JSON, sem markdown.' if req.format == 'structured' else 'Retorne apenas o resumo, sem prefixos ou explicações.'}"""

    raw = _call_llm(sys_p, f"Resuma:\n\n{content[:5000]}")

    if req.format == "structured":
        raw_clean = re.sub(r'```[\w]*\n?', '', raw).replace('```', '').strip()
        try:
            data = json.loads(raw_clean)
        except Exception:
            data = {"tldr": raw_clean[:150], "key_points": [raw_clean], "action_items": [], "conclusion": ""}
        return {
            "voice_response": f"Resumo estruturado pronto, Senhor. {data.get('tldr', '')[:120]}",
            "display_type": "structured_summary",
            "data": {**data, "format": req.format, "length": req.length},
        }

    return {
        "voice_response": f"Resumo pronto, Senhor. {raw[:120]}{'…' if len(raw) > 120 else ''}",
        "display_type": "text_result",
        "data": {"summary": raw, "format": req.format, "length": req.length, "original_length": len(content)},
    }
