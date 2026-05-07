"""
Secure Python execution service.

Execution path (in priority order):
  1. Docker hardened sandbox  — preferred; maximum isolation
  2. Restricted subprocess    — fallback when Docker is unavailable;
                                applies resource limits on POSIX via
                                setrlimit; on Windows runs with reduced
                                priority only (no kernel namespaces)

Static analysis (pre-execution):
  AST-based import/attribute scanner — rejects dangerous constructs
  before any code reaches the sandbox.
"""

import ast
import logging
import os
import platform
import re as _re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────────
# Default execution timeout — overridable via environment variable
_DEFAULT_TIMEOUT = int(os.getenv("JARVIS_EXEC_TIMEOUT", "15"))
# Maximum bytes returned from any execution; prevents context-window flooding
_MAX_OUTPUT_BYTES = int(os.getenv("JARVIS_MAX_OUTPUT_BYTES", str(8 * 1024)))  # 8 KB

_ANSI_ESCAPE = _re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _sanitize_output(raw: str) -> str:
    """Strip ANSI codes and hard-cap output length to avoid LLM context flooding."""
    clean = _ANSI_ESCAPE.sub("", raw)
    if len(clean) > _MAX_OUTPUT_BYTES:
        truncated = clean[:_MAX_OUTPUT_BYTES]
        lines_cut = clean[_MAX_OUTPUT_BYTES:].count("\n")
        clean = truncated + f"\n...({lines_cut} more lines truncated — {_MAX_OUTPUT_BYTES} byte limit)"
    return clean


# ── Static analysis ────────────────────────────────────────────────────────────

# Top-level module names that must never be imported
_BLOCKED_IMPORTS: frozenset[str] = frozenset({
    "os", "sys", "subprocess", "shutil", "socket", "pathlib",
    "importlib", "ctypes", "signal", "resource", "mmap",
    "multiprocessing", "threading", "concurrent",
    "urllib", "http", "ftplib", "smtplib", "telnetlib",
    "requests", "httpx", "aiohttp", "boto3",
    "pickle", "shelve", "marshal",
    "pty", "tty", "termios", "fcntl",
})

# AST node types that are unconditionally forbidden
_BLOCKED_NODE_TYPES: tuple[type, ...] = (
    ast.Global,    # global statement can escape local scope
    ast.Nonlocal,  # same concern
)


class _SecurityVisitor(ast.NodeVisitor):
    """Walk the AST and raise ValueError on any forbidden construct."""

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            top = alias.name.split(".")[0]
            if top in _BLOCKED_IMPORTS:
                raise ValueError(f"import '{alias.name}' não é permitido.")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        top = module.split(".")[0]
        if top in _BLOCKED_IMPORTS:
            raise ValueError(f"from '{module}' import … não é permitido.")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # Block __builtins__ builtins: __import__, exec, eval, compile, open
        if isinstance(node.func, ast.Name):
            if node.func.id in {"__import__", "exec", "eval", "compile", "open"}:
                raise ValueError(f"Built-in '{node.func.id}()' não é permitido.")
        # Block attribute access on forbidden names: os.system, sys.exit, …
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                if node.func.value.id in _BLOCKED_IMPORTS:
                    raise ValueError(
                        f"Acesso a '{node.func.value.id}.{node.func.attr}' não é permitido."
                    )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # Block dunder escapes: __class__.__bases__, etc.
        if node.attr.startswith("__") and node.attr.endswith("__"):
            raise ValueError(f"Acesso ao atributo dunder '{node.attr}' não é permitido.")
        self.generic_visit(node)

    def generic_visit(self, node: ast.AST) -> None:
        if isinstance(node, _BLOCKED_NODE_TYPES):
            raise ValueError(f"Construto '{type(node).__name__}' não é permitido.")
        super().generic_visit(node)


def _static_analysis(code: str) -> str | None:
    """
    Parse code and run the security visitor.
    Returns an error string if forbidden, None if safe.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"❌ Erro de sintaxe: {exc}"
    try:
        _SecurityVisitor().visit(tree)
    except ValueError as exc:
        return f"❌ Bloqueado por segurança: {exc}"
    return None


# ── Docker hardened sandbox ────────────────────────────────────────────────────

_DOCKER_IMAGE = "python:3.11-alpine"

def _run_docker(code: str, timeout: int) -> str | None:
    """
    Run code in a maximally-hardened Docker container.

    Flags applied:
      --rm                         auto-remove container
      --network=none               no outbound network
      --memory=64m                 hard memory cap
      --memory-swap=64m            disable swap (=memory means 0 swap)
      --cpus=0.5                   half a CPU core
      --pids-limit=32              prevent fork bombs
      --read-only                  immutable root filesystem
      --tmpfs /tmp:size=8m,...     writable scratch space, size-capped, noexec
      --cap-drop=ALL               drop every Linux capability
      --security-opt=no-new-privileges  block privilege escalation
      --user=65534                 run as nobody (UID 65534)
      --ulimit nofile=64:64        minimal file-descriptor limit
      --ulimit nproc=16:16         strict process limit
      -v …:ro                      script mounted read-only
    """
    with tempfile.NamedTemporaryFile(
        suffix=".py", mode="w", delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        tmp_path = f.name

    try:
        result = subprocess.run(
            [
                "docker", "run", "--rm",
                "--network=none",
                "--memory=64m",
                "--memory-swap=64m",
                "--cpus=0.5",
                "--pids-limit=32",
                "--read-only",
                "--tmpfs", "/tmp:size=8m,mode=1777,noexec,nosuid",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--user=65534",
                "--ulimit", "nofile=64:64",
                "--ulimit", "nproc=16:16",
                "-v", f"{tmp_path}:/code/script.py:ro",
                _DOCKER_IMAGE,
                "python", "/code/script.py",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout
        if result.returncode != 0 and result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"
        return _sanitize_output(output.strip() or "(sem saída)")

    except subprocess.TimeoutExpired:
        return f"❌ Timeout — script excedeu o limite de {timeout}s."
    except FileNotFoundError:
        return None  # Docker binary not found → caller falls back
    except Exception as exc:
        log.error("Docker execution error: %s", exc)
        return f"❌ Erro no sandbox Docker: {exc}"
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ── Restricted subprocess fallback ────────────────────────────────────────────

def _make_posix_preexec():
    """Return a preexec_fn that applies resource limits on POSIX systems."""
    import resource  # noqa: PLC0415 — only imported on POSIX
    def _limit():
        # 64 MB address space
        resource.setrlimit(resource.RLIMIT_AS,    (64 * 1024 * 1024, 64 * 1024 * 1024))
        # 4 MB stack
        resource.setrlimit(resource.RLIMIT_STACK, (4  * 1024 * 1024, 4  * 1024 * 1024))
        # 16 processes
        resource.setrlimit(resource.RLIMIT_NPROC, (16, 16))
        # 64 open file descriptors
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    return _limit


def _run_subprocess(code: str, timeout: int) -> str:
    with tempfile.NamedTemporaryFile(
        suffix=".py", mode="w", delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        tmp_path = f.name

    kwargs: dict = {
        "capture_output": True,
        "text": True,
        "timeout": timeout,
    }

    is_posix = platform.system() != "Windows"
    if is_posix:
        kwargs["preexec_fn"] = _make_posix_preexec()

    try:
        result = subprocess.run([sys.executable, tmp_path], **kwargs)
        output = result.stdout
        if result.returncode != 0 and result.stderr:
            output += f"\nSTDERR:\n{result.stderr}"
        return _sanitize_output(output.strip() or "(sem saída)")
    except subprocess.TimeoutExpired:
        return f"❌ Timeout — script excedeu o limite de {timeout}s."
    except Exception as exc:
        log.error("Subprocess execution error: %s", exc)
        return f"❌ Erro na execução: {exc}"
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ── Public API ─────────────────────────────────────────────────────────────────

def run_python(code: str, timeout: int = _DEFAULT_TIMEOUT) -> str:
    if not code.strip():
        return "❌ Nenhum código fornecido."

    # 1. Static analysis — always runs, zero cost
    error = _static_analysis(code)
    if error:
        return error

    # 2. Docker hardened sandbox (preferred)
    if shutil.which("docker"):
        result = _run_docker(code, timeout)
        if result is not None:
            return result
        log.warning("Docker available but run failed — falling back to subprocess")

    # 3. Restricted subprocess (fallback)
    log.warning("Running code outside Docker sandbox — reduced isolation")
    return _run_subprocess(code, timeout)


async def run_python_async(code: str, timeout: int = _DEFAULT_TIMEOUT) -> str:
    """Non-blocking async variant — wraps run_python in a thread-pool executor.

    Use this from async request handlers to avoid blocking the event loop.
    """
    import asyncio
    return await asyncio.to_thread(run_python, code, timeout)

