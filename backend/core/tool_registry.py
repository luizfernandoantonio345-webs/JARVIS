"""
Tool registry — expõe as capacidades do JARVIS como ferramentas que o modelo
pode ESCOLHER e CHAMAR, em vez de prompts que só trocam o system message.

Diferença em relação ao sistema de `actions`:

    actions/  →  preset de prompt. O classificador escolhe, o modelo gera texto.
    tools     →  função com schema JSON. O MODELO decide chamar, nós executamos,
                 o resultado volta para ele, e o laço continua.

É essa volta — executar e devolver o resultado — que permite ao agente corrigir
o próprio erro e concluir uma tarefa de verdade.

Cada ferramenta declara:
    name        identificador estável usado pelo modelo
    description quando usar (o modelo só tem isto para decidir)
    parameters  JSON Schema dos argumentos
    handler     callable(**kwargs) -> str
    action_type chave usada pelo SafetyGate para classificar o risco

Registrar uma ferramenta nova:

    @tool(
        name="minha_ferramenta",
        description="Faz X. Use quando Y.",
        parameters={"type": "object", "properties": {...}, "required": [...]},
        action_type="file_read",
    )
    def minha_ferramenta(arg: str) -> str:
        ...
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("jarvis.tools")

# ── Limites ───────────────────────────────────────────────────────────────────
MAX_RESULT_CHARS = 20_000  # resultado maior que isto é truncado antes de voltar
COMMAND_TIMEOUT = 120      # segundos


# ── Modelo da ferramenta ──────────────────────────────────────────────────────

@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., str]
    action_type: str = "unknown"
    # Ferramentas que só leem não precisam de confirmação nem do gate.
    read_only: bool = False

    def to_anthropic(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }

    def to_openai(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    # Ollama segue o formato da OpenAI.
    to_ollama = to_openai


_REGISTRY: dict[str, Tool] = {}


def tool(
    *,
    name: str,
    description: str,
    parameters: dict[str, Any],
    action_type: str = "unknown",
    read_only: bool = False,
) -> Callable[[Callable[..., str]], Callable[..., str]]:
    """Decorator que registra uma função como ferramenta."""

    def decorator(fn: Callable[..., str]) -> Callable[..., str]:
        if name in _REGISTRY:
            log.warning("[TOOLS] %r já registrada — substituindo", name)
        _REGISTRY[name] = Tool(
            name=name,
            description=description,
            parameters=parameters,
            handler=fn,
            action_type=action_type,
            read_only=read_only,
        )
        log.debug("[TOOLS] registrada: %s", name)
        return fn

    return decorator


_extras_loaded = False


def _load_extra_tool_modules() -> None:
    """
    Importa os módulos que registram ferramentas adicionais.

    Fica aqui, e não no topo do arquivo, porque esses módulos importam de volta
    deste — o import tardio quebra o ciclo. É idempotente: só roda uma vez.
    """
    global _extras_loaded
    if _extras_loaded:
        return
    _extras_loaded = True
    for module in ("tools_web",):
        try:
            __import__(f"{__package__}.{module}", fromlist=["*"])
        except Exception as exc:  # uma ferramenta opcional não derruba o resto
            log.warning("[TOOLS] módulo %r não carregou: %s", module, exc)


def get_tool(name: str) -> Tool | None:
    _load_extra_tool_modules()
    return _REGISTRY.get(name)


def all_tools() -> list[Tool]:
    _load_extra_tool_modules()
    return list(_REGISTRY.values())


def schemas_for(provider: str) -> list[dict[str, Any]]:
    """Schemas no formato do provedor ('anthropic' | 'openai' | 'ollama')."""
    tools = all_tools()
    if provider == "anthropic":
        return [t.to_anthropic() for t in tools]
    return [t.to_openai() for t in tools]


def truncate(text: str, limit: int = MAX_RESULT_CHARS) -> str:
    """Corta resultado grande preservando início e fim, que é onde está o sinal."""
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-(limit // 2):]
    omitted = len(text) - limit
    return f"{head}\n\n[... {omitted} caracteres omitidos ...]\n\n{tail}"


# ── Raiz de trabalho ──────────────────────────────────────────────────────────

def workspace_root() -> Path:
    """
    Diretório onde o agente pode operar.
    Configurável por JARVIS_WORKSPACE; o padrão é a raiz do projeto.
    """
    env = os.getenv("JARVIS_WORKSPACE")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def _resolve_inside_workspace(relative: str) -> Path:
    """
    Resolve um caminho garantindo que ele fique dentro da raiz de trabalho.

    Isto não é restrição ao usuário: é o que impede uma alucinação do modelo
    de escrever em /etc ou apagar algo fora do projeto.
    """
    root = workspace_root()
    candidate = (root / relative).resolve() if not Path(relative).is_absolute() else Path(relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise PermissionError(
            f"Caminho fora da raiz de trabalho ({root}): {candidate}. "
            f"Ajuste JARVIS_WORKSPACE se a intenção for outra."
        )
    return candidate


# ── Ferramentas de arquivo ────────────────────────────────────────────────────

@tool(
    name="read_file",
    description=(
        "Lê o conteúdo de um arquivo de texto do projeto. "
        "Use antes de editar qualquer arquivo, para saber o que já está lá."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Caminho relativo à raiz do projeto, ex: backend/main.py",
            },
            "start_line": {"type": "integer", "description": "Linha inicial (1-indexed, opcional)"},
            "end_line": {"type": "integer", "description": "Linha final (inclusiva, opcional)"},
        },
        "required": ["path"],
    },
    action_type="file_read",
    read_only=True,
)
def read_file(path: str, start_line: int | None = None, end_line: int | None = None) -> str:
    target = _resolve_inside_workspace(path)
    if not target.is_file():
        return f"ERRO: arquivo não encontrado: {path}"
    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    if start_line or end_line:
        lo = max(1, start_line or 1)
        hi = min(len(lines), end_line or len(lines))
        chunk = lines[lo - 1: hi]
        numbered = [f"{i}\t{l}" for i, l in enumerate(chunk, start=lo)]
    else:
        numbered = [f"{i}\t{l}" for i, l in enumerate(lines, start=1)]
    return truncate("\n".join(numbered))


@tool(
    name="write_file",
    description=(
        "Escreve um arquivo, criando ou sobrescrevendo por completo. "
        "Para alterar um arquivo existente, leia antes com read_file. "
        "Faz backup .bak automático do que for sobrescrito."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Caminho relativo à raiz do projeto"},
            "content": {"type": "string", "description": "Conteúdo completo do arquivo"},
        },
        "required": ["path", "content"],
    },
    action_type="file_write",
)
def write_file(path: str, content: str) -> str:
    target = _resolve_inside_workspace(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        backup = target.with_suffix(target.suffix + ".bak")
        backup.write_text(target.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    target.write_text(content, encoding="utf-8")
    return f"OK: {path} gravado ({len(content)} caracteres)."


@tool(
    name="edit_file",
    description=(
        "Substitui um trecho exato dentro de um arquivo. Prefira esta ferramenta "
        "a write_file quando a alteração for pontual. O trecho em old_text precisa "
        "aparecer exatamente uma vez no arquivo."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "old_text": {"type": "string", "description": "Trecho exato a substituir"},
            "new_text": {"type": "string", "description": "Texto que entra no lugar"},
        },
        "required": ["path", "old_text", "new_text"],
    },
    action_type="file_write",
)
def edit_file(path: str, old_text: str, new_text: str) -> str:
    target = _resolve_inside_workspace(path)
    if not target.is_file():
        return f"ERRO: arquivo não encontrado: {path}"
    original = target.read_text(encoding="utf-8", errors="replace")
    occurrences = original.count(old_text)
    if occurrences == 0:
        return "ERRO: old_text não encontrado. Leia o arquivo de novo e use o texto exato."
    if occurrences > 1:
        return (
            f"ERRO: old_text aparece {occurrences} vezes. "
            "Inclua mais contexto em volta para torná-lo único."
        )
    target.with_suffix(target.suffix + ".bak").write_text(original, encoding="utf-8")
    target.write_text(original.replace(old_text, new_text, 1), encoding="utf-8")
    return f"OK: {path} alterado."


@tool(
    name="list_dir",
    description="Lista arquivos e pastas de um diretório do projeto.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Caminho relativo; use '.' para a raiz"},
        },
        "required": ["path"],
    },
    action_type="file_read",
    read_only=True,
)
def list_dir(path: str = ".") -> str:
    target = _resolve_inside_workspace(path)
    if not target.is_dir():
        return f"ERRO: diretório não encontrado: {path}"
    entries = []
    for item in sorted(target.iterdir()):
        if item.name.startswith(".") and item.name not in (".env.example", ".gitignore"):
            continue
        entries.append(f"{'dir ' if item.is_dir() else 'file'}  {item.name}")
    return "\n".join(entries) or "(vazio)"


@tool(
    name="search_code",
    description=(
        "Procura um texto ou expressão regular nos arquivos do projeto. "
        "Use para localizar onde algo está definido antes de ler o arquivo inteiro."
    ),
    parameters={
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Texto ou regex a procurar"},
            "glob": {"type": "string", "description": "Filtro de arquivos, ex: *.py"},
        },
        "required": ["pattern"],
    },
    action_type="file_read",
    read_only=True,
)
def search_code(pattern: str, glob: str = "*") -> str:
    root = workspace_root()
    cmd = ["grep", "-rIn", "--exclude-dir=.git", "--exclude-dir=node_modules",
           "--exclude-dir=__pycache__", "--exclude-dir=venv311", "-E", pattern, str(root)]
    if glob and glob != "*":
        cmd.insert(2, f"--include={glob}")
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout
    except subprocess.TimeoutExpired:
        return "ERRO: busca excedeu o tempo limite."
    if not out.strip():
        return "Nenhuma ocorrência."
    out = out.replace(str(root) + "/", "")
    return truncate(out, 8_000)


# ── Execução de comando ───────────────────────────────────────────────────────

@tool(
    name="run_command",
    description=(
        "Executa um comando de shell na raiz do projeto e devolve stdout, stderr "
        "e código de saída. Use para rodar testes, instalar dependência, usar git, "
        "ou verificar se o que você escreveu realmente funciona. "
        "SEMPRE rode os testes depois de alterar código."
    ),
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Comando completo"},
            "timeout": {"type": "integer", "description": f"Segundos (padrão {COMMAND_TIMEOUT})"},
        },
        "required": ["command"],
    },
    action_type="command_execute",
)
def run_command(command: str, timeout: int = COMMAND_TIMEOUT) -> str:
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(workspace_root()),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"ERRO: comando excedeu {timeout}s e foi interrompido."
    parts = [f"exit_code: {proc.returncode}"]
    if proc.stdout.strip():
        parts.append(f"stdout:\n{proc.stdout}")
    if proc.stderr.strip():
        parts.append(f"stderr:\n{proc.stderr}")
    return truncate("\n\n".join(parts))


__all__ = [
    "Tool",
    "tool",
    "get_tool",
    "all_tools",
    "schemas_for",
    "truncate",
    "workspace_root",
]
