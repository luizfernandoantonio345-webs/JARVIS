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
_AUDIT_FILE   = _LOG_DIR / "audit.jsonl"
_MAX_BYTES    = 5 * 1024 * 1024   # 5 MB por arquivo
_BACKUP_COUNT = 7                  # 7 backups → ~35 MB total de audit

# ── Rotação do audit.jsonl ────────────────────────────────────────────────────
def _rotate_if_needed() -> None:
    """Roda audit.jsonl quando passa de _MAX_BYTES (rename simples)."""
    try:
        if not _AUDIT_FILE.exists() or _AUDIT_FILE.stat().st_size < _MAX_BYTES:
            return
        # Shift backups: audit.7.jsonl → remove, 6→7 … 1→2
        for i in range(_BACKUP_COUNT - 1, 0, -1):
            old = _LOG_DIR / f"audit.{i}.jsonl"
            new = _LOG_DIR / f"audit.{i + 1}.jsonl"
            if old.exists():
                old.rename(new)
        _AUDIT_FILE.rename(_LOG_DIR / "audit.1.jsonl")
    except Exception:
        pass

# ── Janela de deteção de anomalias ────────────────────────────────────────────
_ip_errors:   dict[str, deque] = defaultdict(lambda: deque(maxlen=50))
_ip_requests: dict[str, deque] = defaultdict(lambda: deque(maxlen=200))
_ERROR_THRESHOLD   = 10   # erros em 60s → suspeito
_REQUEST_THRESHOLD = 60   # requests em 60s → possível scan


def _write_audit(entry: dict) -> None:
    """Escreve entrada de audit em JSONL (append-only) com rotação automática."""
    try:
        _rotate_if_needed()
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
    """Lê as últimas N entradas do audit log (incluindo backups se necessário)."""
    entries: list[dict] = []

    # Arquivos em ordem mais recente → mais antigo
    candidates = [_AUDIT_FILE] + [
        _LOG_DIR / f"audit.{i}.jsonl" for i in range(1, _BACKUP_COUNT + 1)
    ]

    for path in candidates:
        if not path.exists():
            continue
        try:
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            for line in reversed(lines):
                if line.strip():
                    try:
                        entries.append(json.loads(line))
                    except Exception:
                        pass
                    if len(entries) >= limit:
                        break
        except Exception:
            pass
        if len(entries) >= limit:
            break

    # Retorna em ordem cronológica (mais antigo primeiro)
    entries.reverse()
    return entries[-limit:]


def get_audit_stats() -> dict:
    """Retorna estatísticas do audit log."""
    total_size = 0
    file_count = 0
    candidates = [_AUDIT_FILE] + [
        _LOG_DIR / f"audit.{i}.jsonl" for i in range(1, _BACKUP_COUNT + 1)
    ]
    for path in candidates:
        if path.exists():
            total_size += path.stat().st_size
            file_count += 1
    return {
        "files": file_count,
        "total_size_mb": round(total_size / 1024 / 1024, 2),
        "max_size_mb": round(_MAX_BYTES / 1024 / 1024, 1),
        "backup_count": _BACKUP_COUNT,
        "current_file": str(_AUDIT_FILE),
    }
