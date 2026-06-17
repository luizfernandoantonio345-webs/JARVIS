"""
JARVIS Input Guard — Anti-Prompt-Injection + Sanitização
Bloqueia tentativas de manipulação, jailbreak e injection antes de chegarem ao LLM.
"""
from __future__ import annotations
import logging
import re
import time
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

log = logging.getLogger("jarvis.input_guard")

# ── Padrões de prompt injection e jailbreak ─────────────────────────────────
_INJECTION_PATTERNS: list[tuple[str, str]] = [
    # Tentativas clássicas de jailbreak
    (r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?", "jailbreak_ignore_instructions"),
    (r"disregard\s+(?:all\s+)?(?:previous|your)\s+(?:instructions?|rules?|guidelines?)", "jailbreak_disregard"),
    (r"you\s+are\s+(?:now|actually)\s+(?:an?\s+)?(?:evil|unethical|unrestricted|DAN|jailbroken)", "jailbreak_persona"),
    (r"\bDAN\b.*\bjailbreak\b|\bjailbreak\b.*\bDAN\b", "jailbreak_dan"),
    (r"pretend\s+(?:you\s+are|to\s+be)\s+(?:an?\s+)?(?:AI\s+without|unrestricted)", "jailbreak_pretend"),
    (r"act\s+as\s+if\s+you\s+(?:have\s+no\s+restrictions|are\s+unfiltered)", "jailbreak_act_as"),
    (r"your\s+(?:new|real|true)\s+(?:instructions?|programming|purpose)\s+(?:are|is)", "jailbreak_new_instructions"),
    # Tentativas de exfiltração de sistema
    (r"(?:print|show|reveal|output|display)\s+(?:your\s+)?(?:system\s+prompt|instructions?|rules?)", "exfil_system_prompt"),
    (r"what\s+(?:are|were)\s+your\s+(?:exact\s+)?(?:instructions?|rules?|system\s+prompt)", "exfil_rules"),
    # SQL/NoSQL injection em campos de texto
    (r"(?:union\s+select|drop\s+table|insert\s+into|delete\s+from)\s+\w+", "sql_injection"),
    (r"(?:;\s*(?:drop|delete|truncate|alter)\s+)", "sql_injection_chained"),
    # Script injection (XSS via texto)
    (r"<script[^>]*>.*?</script>", "xss_script"),
    (r"javascript:\s*(?:alert|eval|document)", "xss_javascript"),
    # Path traversal em parâmetros de texto
    (r"\.\./\.\./\.\./(?:etc|windows|system)", "path_traversal"),
    # Tentativas de executar comandos via texto
    (r"(?:execute|run|eval)\s*\(\s*['\"](?:rm|del|format|shutdown)", "command_injection"),
]

_COMPILED = [(re.compile(pat, re.IGNORECASE | re.DOTALL), name) for pat, name in _INJECTION_PATTERNS]

# ── Tamanhos máximos ─────────────────────────────────────────────────────────
_MAX_MESSAGE_LEN = 8_000      # chars por mensagem
_MAX_BODY_BYTES  = 5_242_880  # 5MB por request
_MAX_QUERY_LEN   = 512        # chars em query strings

# ── Endpoints que devem verificar o body ─────────────────────────────────────
_CHECK_BODY_PATHS = {"/chat", "/chat/stream", "/chat/process", "/voice/command", "/agents"}


def _scan_text(text: str) -> tuple[bool, str]:
    """Verifica se o texto contém padrão de injection. Retorna (é_suspeito, nome_do_padrão)."""
    for pattern, name in _COMPILED:
        if pattern.search(text):
            return True, name
    return False, ""


class InputGuardMiddleware(BaseHTTPMiddleware):
    """
    Middleware de proteção de input:
    - Limita tamanho de body e query params
    - Detecta prompt injection e jailbreak
    - Detecta SQL/XSS/path traversal injection
    - Loga e bloqueia tentativas suspeitas
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        # ── 1. Verificar tamanho do body ─────────────────────────────────────
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > _MAX_BODY_BYTES:
            log.warning("[GUARD] Body muito grande: %s bytes — %s", content_length, path)
            return JSONResponse(
                {"error": "Payload too large", "max_bytes": _MAX_BODY_BYTES},
                status_code=413,
            )

        # ── 2. Verificar query params ─────────────────────────────────────────
        for key, val in request.query_params.items():
            if len(val) > _MAX_QUERY_LEN:
                log.warning("[GUARD] Query param muito longa: %s — %s", key, path)
                return JSONResponse({"error": "Query parameter too long"}, status_code=400)
            suspicious, pattern = _scan_text(val)
            if suspicious:
                log.warning("[GUARD] Injection em query param [%s]: pattern=%s ip=%s",
                            key, pattern, request.client.host if request.client else "?")
                return JSONResponse(
                    {"error": "Input inválido detectado", "code": "INPUT_GUARD"},
                    status_code=400,
                )

        # ── 3. Verificar body em endpoints relevantes ─────────────────────────
        if any(path.startswith(p) for p in _CHECK_BODY_PATHS):
            try:
                body_bytes = await request.body()
                if len(body_bytes) > _MAX_BODY_BYTES:
                    return JSONResponse({"error": "Payload too large"}, status_code=413)
                if body_bytes:
                    body_str = body_bytes.decode("utf-8", errors="ignore")
                    # Checar mensagem no JSON
                    msg_match = re.search(r'"message"\s*:\s*"((?:[^"\\]|\\.){0,8100})"', body_str)
                    if msg_match:
                        msg_text = msg_match.group(1)
                        if len(msg_text) > _MAX_MESSAGE_LEN:
                            log.warning("[GUARD] Mensagem muito longa: %d chars — %s", len(msg_text), path)
                            return JSONResponse(
                                {"error": "Mensagem excede limite de caracteres",
                                 "max": _MAX_MESSAGE_LEN},
                                status_code=400,
                            )
                        suspicious, pattern = _scan_text(msg_text)
                        if suspicious:
                            ip = request.client.host if request.client else "?"
                            log.warning(
                                "[GUARD] INJECTION DETECTADO: pattern=%s ip=%s path=%s preview=%r",
                                pattern, ip, path, msg_text[:120],
                            )
                            return JSONResponse(
                                {"error": "Tentativa de manipulação detectada. Acesso registado.",
                                 "code": "INJECTION_BLOCKED"},
                                status_code=400,
                            )
            except Exception as e:
                log.debug("[GUARD] Erro ao ler body: %s", e)

        return await call_next(request)
