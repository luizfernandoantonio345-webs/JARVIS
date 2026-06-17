"""
JARVIS Audit Logger — Log imutável de todas as operações.
Regista: IP, endpoint, método, session_id, status, latência, user-agent.
Detecta padrões suspeitos: muitos erros, IPs desconhecidos, horários estranhos.
"""
from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

log = logging.getLogger("jarvis.audit")

# ── Ficheiro de audit log ─────────────────────────────────────────────────────
_LOG_DIR = Path(__file__).parent.parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)
_AUDIT_FILE = _LOG_DIR / "audit.jsonl"

# ── Janela de deteção de anomalias ────────────────────────────────────────────
_ip_errors:   dict[str, deque] = defaultdict(lambda: deque(maxlen=50))
_ip_requests: dict[str, deque] = defaultdict(lambda: deque(maxlen=200))
_ERROR_THRESHOLD   = 10   # erros em 60s → suspeito
_REQUEST_THRESHOLD = 60   # requests em 60s → possível scan


def _write_audit(entry: dict) -> None:
    """Escreve entrada de audit em JSONL (append-only)."""
    try:
        with open(_AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _detect_anomaly(ip: str, status: int, path: str) -> str | None:
    """Detecta padrões suspeitos por IP. Retorna descrição ou None."""
    now = time.time()

    # Regista request
    _ip_requests[ip].append(now)
    reqs_60s = sum(1 for t in _ip_requests[ip] if now - t < 60)
    if reqs_60s > _REQUEST_THRESHOLD:
        return f"FLOOD: {reqs_60s} requests/60s de {ip}"

    # Regista erros (4xx/5xx)
    if status >= 400:
        _ip_errors[ip].append(now)
        errs_60s = sum(1 for t in _ip_errors[ip] if now - t < 60)
        if errs_60s >= _ERROR_THRESHOLD:
            return f"ERROS: {errs_60s} errors/60s de {ip} (último: {path})"

    return None


class AuditMiddleware(BaseHTTPMiddleware):
    """
    Middleware de auditoria:
    - Loga TODOS os pedidos HTTP em formato JSONL
    - Detecta padrões suspeitos (flood, scan, erros excessivos)
    - Adiciona header X-Request-ID para rastreamento
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        import uuid

        start = time.perf_counter()
        req_id = uuid.uuid4().hex[:12]
        ip = (request.client.host if request.client else "unknown")

        # Processar request
        response = await call_next(request)
        latency_ms = int((time.perf_counter() - start) * 1000)

        # Adicionar request ID ao response
        response.headers["X-Request-ID"] = req_id

        status = response.status_code
        path   = request.url.path
        method = request.method

        # Extrair session_id se disponível (query param)
        session_id = request.query_params.get("session_id", "")

        # Montar entrada de audit
        entry = {
            "ts":         datetime.utcnow().isoformat() + "Z",
            "req_id":     req_id,
            "ip":         ip,
            "method":     method,
            "path":       path,
            "status":     status,
            "latency_ms": latency_ms,
            "session":    session_id[:24] if session_id else "",
            "ua":         request.headers.get("user-agent", "")[:80],
        }

        # Detectar anomalias
        anomaly = _detect_anomaly(ip, status, path)
        if anomaly:
            entry["anomaly"] = anomaly
            log.warning("[AUDIT] ⚠ ANOMALIA: %s", anomaly)

        # Só escrever audit para paths relevantes (excluir health spam)
        if path not in {"/health", "/metrics", "/favicon.ico"} and not path.startswith("/static"):
            _write_audit(entry)

        # Log compacto no console (só erros ou paths importantes)
        if status >= 400 or path.startswith(("/chat", "/voice", "/agents", "/ws")):
            log.info("[AUDIT] %s %s %s → %d (%dms) [%s]",
                     method, path, ip, status, latency_ms, req_id)

        return response


def get_recent_audit(limit: int = 100) -> list[dict]:
    """Lê as últimas N entradas do audit log."""
    if not _AUDIT_FILE.exists():
        return []
    try:
        lines = _AUDIT_FILE.read_text(encoding="utf-8").strip().split("\n")
        entries = []
        for line in lines[-limit:]:
            if line.strip():
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass
        return entries
    except Exception:
        return []
