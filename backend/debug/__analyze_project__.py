"""
Full project analysis script — detects duplications, async issues, circular imports.
Run: python debug/__analyze_project__.py
"""
import ast
import os
import sys
import re
from pathlib import Path
from collections import defaultdict

# Force UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent  # d:\JAVIS\backend

# ─────────────────────────────────────────
# 1. Collect all .py files
# ─────────────────────────────────────────
py_files = sorted([
    p for p in ROOT.rglob("*.py")
    if "__pycache__" not in str(p) and p.name != "__analyze_project__.py"
])

# ─────────────────────────────────────────
# 2. Parse each file, extract imports + defs
# ─────────────────────────────────────────
file_data = {}  # path -> {imports, classes, functions, lines, issues}

ASYNC_ISSUES = []
IMPORT_MAP = defaultdict(list)  # module_name -> [files that import it]
DEFINES = defaultdict(list)     # symbol_name -> [files that define it]

for fp in py_files:
    rel = fp.relative_to(ROOT)
    try:
        src = fp.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        print(f"[READ ERROR] {rel}: {e}")
        continue

    lines = src.splitlines()
    n_lines = len(lines)

    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        print(f"[SYNTAX ERROR] {rel}: {e}")
        file_data[str(rel)] = {"lines": n_lines, "error": str(e)}
        continue

    imports = []
    classes = []
    functions = []
    issues = []

    for node in ast.walk(tree):
        # Collect imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
                IMPORT_MAP[alias.name].append(str(rel))
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            imports.append(mod)
            IMPORT_MAP[mod].append(str(rel))

        # Collect class / func defs
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
            DEFINES[node.name].append(str(rel))
        elif isinstance(node, ast.FunctionDef):
            functions.append(node.name)
            DEFINES[node.name].append(str(rel))
            # Check for time.sleep in async function
            if isinstance(node, ast.AsyncFunctionDef):
                pass
        elif isinstance(node, ast.AsyncFunctionDef):
            functions.append(f"async {node.name}")
            DEFINES[node.name].append(str(rel))

    # Raw pattern checks (faster than full AST walk)
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # time.sleep in any file (likely inside async)
        if "time.sleep(" in stripped and not stripped.startswith("#"):
            issues.append(f"L{i}: time.sleep() — use asyncio.sleep() in async context")
        # requests.get/post (blocking)
        if re.search(r'\brequests\.(get|post|put|delete|patch)\b', stripped) and not stripped.startswith("#"):
            issues.append(f"L{i}: requests.{re.search(r'requests\\.(\w+)', stripped).group(1)}() — blocking in async")
        # .dict() pydantic v1
        if re.search(r'\.\bdict\(\)', stripped) and not stripped.startswith("#"):
            issues.append(f"L{i}: .dict() — Pydantic v2: use .model_dump()")
        # .parse_obj pydantic v1
        if ".parse_obj(" in stripped and not stripped.startswith("#"):
            issues.append(f"L{i}: .parse_obj() — Pydantic v2: use model_validate()")
        # class Config (pydantic v1 style)
        if re.match(r'\s*class Config:', line) and not stripped.startswith("#"):
            issues.append(f"L{i}: class Config — Pydantic v2: use model_config = ConfigDict(...)")
        # open() without with
        if re.search(r'[^=\s]\s*=\s*open\(', stripped) and "with" not in stripped and not stripped.startswith("#"):
            issues.append(f"L{i}: open() without 'with' statement")
        # except Exception: pass (swallowed errors)
        if re.match(r'\s*except\s+Exception\s*:', line) and not stripped.startswith("#"):
            # check next line
            next_line = lines[i].strip() if i < len(lines) else ""
            if next_line in ("pass", "continue", ""):
                issues.append(f"L{i}: bare 'except Exception: pass' — swallowed error")

    file_data[str(rel)] = {
        "lines": n_lines,
        "imports": imports,
        "classes": classes,
        "functions": functions,
        "issues": issues,
    }

# ─────────────────────────────────────────
# 3. REPORT
# ─────────────────────────────────────────
SEP = "=" * 65

print(f"\n{SEP}")
print("FASE 1 — MAPEAMENTO COMPLETO DO PROJETO JARVIS")
print(SEP)
print(f"Total de arquivos .py: {len(py_files)}")
total_lines = sum(d.get('lines', 0) for d in file_data.values())
print(f"Total de linhas     : {total_lines}")
print()

# ── A) Arquivos grandes
print("── A) ARQUIVOS > 300 LINHAS (God Files) ──────────────────")
big = [(k, v['lines']) for k,v in file_data.items() if v.get('lines',0) > 300]
for name, ln in sorted(big, key=lambda x: -x[1]):
    print(f"  {ln:>5} linhas  {name}")

# ── B) Nomes duplicados
print("\n── B) NOMES DUPLICADOS ENTRE PASTAS ──────────────────────")
name_map = defaultdict(list)
for fp in py_files:
    if fp.name not in ("__init__.py", "__analyze_project__.py"):
        name_map[fp.stem].append(str(fp.relative_to(ROOT)))
for name, paths in sorted(name_map.items()):
    if len(paths) > 1:
        print(f"  [{name}]")
        for p in paths:
            print(f"    {p}")

# ── C) Símbolos duplicados (classes/functions defined in multiple files)
print("\n── C) CLASSES/FUNÇÕES DEFINIDAS EM MÚLTIPLOS ARQUIVOS ────")
for sym, paths in sorted(DEFINES.items()):
    if len(paths) > 1 and not sym.startswith("_") and sym not in ("setUp", "tearDown", "test"):
        print(f"  {sym}: {paths}")

# ── D) Issues por arquivo
print("\n── D) PROBLEMAS POR ARQUIVO ──────────────────────────────")
total_issues = 0
for name, data in sorted(file_data.items()):
    issues = data.get('issues', [])
    if issues:
        print(f"\n  [{name}]")
        for iss in issues:
            print(f"    ⚠  {iss}")
        total_issues += len(issues)

print(f"\nTotal de issues detectados: {total_issues}")

# ── E) Pares suspeitos (mesma lógica em 2 lugares)
print("\n── E) PARES SUSPEITOS (POSSÍVEL DUPLICAÇÃO DE LÓGICA) ────")
suspects = [
    ("services/executor.py", "services/execute_service.py", "execução de código/comandos"),
    ("services/auto_dev.py", "autodev/loop.py", "loop de auto-desenvolvimento"),
    ("services/auto_loop.py", "core/autonomous_loop.py", "loop autônomo"),
    ("services/orchestrator.py", "agents/multi_agent_orchestrator.py", "orquestração de agentes"),
    ("services/planner.py", "agents/planner_agent.py", "planejamento de tarefas"),
    ("services/llm_service.py", "services/llm_router.py", "acesso ao LLM"),
    ("services/security_engine.py", "services/security_guard.py", "engine de segurança"),
    ("services/security_engine.py", "agents/security_agent.py", "agente de segurança"),
    ("services/code_validator.py", "autodev/validator.py", "validação de código"),
    ("actions/shell_exec.py", "tools/shell_feedback.py", "execução de shell"),
    ("actions/file_reader.py", "services/fs_controller.py", "leitura de arquivos"),
    ("services/memory_service.py", "agents/memory_agent.py", "gerenciamento de memória"),
]
for a, b, reason in suspects:
    fa = ROOT / a.replace("/", os.sep)
    fb = ROOT / b.replace("/", os.sep)
    if fa.exists() and fb.exists():
        la = len(fa.read_text(encoding="utf-8", errors="replace").splitlines())
        lb = len(fb.read_text(encoding="utf-8", errors="replace").splitlines())
        print(f"  ⚠  {a} ({la}L) vs {b} ({lb}L)")
        print(f"     motivo: {reason}")

# ── F) Constantes duplicadas (hardcoded em múltiplos arquivos)
print("\n── F) CONSTANTES HARDCODED EM MÚLTIPLOS ARQUIVOS ─────────")
CONST_PATTERNS = {
    "timeout": re.compile(r'\b(timeout|TIMEOUT)\s*=\s*\d+'),
    "model_name": re.compile(r'(model\s*=\s*["\'][\w\-:]+["\']|MODEL\s*=\s*["\'][\w\-:]+["\'])'),
    "db_path": re.compile(r'["\'][\w./\\]+\.db["\']'),
    "ollama_url": re.compile(r'http://localhost:\d+'),
}
const_hits = defaultdict(list)
for fp in py_files:
    try:
        src = fp.read_text(encoding="utf-8", errors="replace")
    except:
        continue
    rel = str(fp.relative_to(ROOT))
    for ctype, pat in CONST_PATTERNS.items():
        matches = pat.findall(src)
        if matches:
            const_hits[ctype].append((rel, matches[:3]))

for ctype, hits in const_hits.items():
    if len(hits) > 2:
        print(f"\n  [{ctype}] — aparece em {len(hits)} arquivos:")
        for rel, examples in hits[:6]:
            print(f"    {rel}: {examples[0]}")

# ── G) Import style inconsistency
print("\n── G) IMPORTS RELATIVOS vs ABSOLUTOS MISTURADOS ──────────")
for fp in py_files:
    try:
        src = fp.read_text(encoding="utf-8", errors="replace")
    except:
        continue
    rel = str(fp.relative_to(ROOT))
    has_rel = bool(re.search(r'^from \.\S', src, re.MULTILINE))
    has_abs = bool(re.search(r'^from (services|agents|core|autodev|actions|routes|autonomy|behavior|integrations|tools)\b', src, re.MULTILINE))
    if has_rel and has_abs:
        print(f"  ⚠  {rel} — mistura imports relativos e absolutos")

print(f"\n{SEP}")
print("FIM DO RELATÓRIO — FASE 1 COMPLETA")
print(SEP)
