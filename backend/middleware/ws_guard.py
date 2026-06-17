"""
JARVIS WebSocket Guard — Validação de origem e throttle de conexões WS.
Impede que IPs desconhecidos na rede local acessem o WebSocket.
"""
from __future__ import annotations

import logging
import os
import time
from collections import defaultdict

log = logging.getLogger("jarvis.ws_guard")

# ── IP Allowlist ──────────────────────────────────────────────────────────────
def _get_allowed_ips() -> set[str]:
    """Lê IPs permitidos de JARVIS_ALLOW_IPS (comma-separated) + sempre localhost."""
    raw = os.getenv("JARVIS_ALLOW_IPS", "")
    ips: set[str] = {"127.0.0.1", "::1", "localhost"}
    if raw:
        for ip in raw.split(","):
            ip = ip.strip()
            if ip:
                ips.add(ip)
    return ips


# ── Throttle de conexões WS por IP ────────────────────────────────────────────
_ws_conn_times: dict[str, list[float]] = defaultdict(list)
_WS_MAX_CONN_PER_MIN = 10  # máximo de conexões WS por IP por minuto


def check_ws_allowed(client_ip: str, origin: str | None = None) -> tuple[bool, str]:
    """
    Verifica se conexão WS é permitida.
    Retorna (permitido, motivo_de_recusa).
    """
    now = time.time()
    allowed_ips = _get_allowed_ips()

    # ── 1. Checar IP allowlist (apenas quando configurado) ────────────────────
    raw_env = os.getenv("JARVIS_ALLOW_IPS", "").strip()
    if raw_env:  # Só aplica allowlist se explicitamente configurado
        if client_ip not in allowed_ips:
            log.warning("[WS_GUARD] IP bloqueado: %s (não está em JARVIS_ALLOW_IPS)", client_ip)
            return False, f"IP {client_ip} não autorizado"

    # ── 2. Throttle: máximo N conexões por minuto por IP ──────────────────────
    times = _ws_conn_times[client_ip]
    # Remove timestamps antigos (mais de 60s)
    _ws_conn_times[client_ip] = [t for t in times if now - t < 60]
    if len(_ws_conn_times[client_ip]) >= _WS_MAX_CONN_PER_MIN:
        log.warning("[WS_GUARD] Throttle WS: %s (%d conn/60s)", client_ip, len(_ws_conn_times[client_ip]))
        return False, "Muitas conexões WebSocket — throttle ativo"

    _ws_conn_times[client_ip].append(now)

    # ── 3. Validar origem (CSRF protection para WS) ───────────────────────────
    if origin:
        allowed_origins_str = os.getenv("JARVIS_CORS_ORIGINS", "*")
        if allowed_origins_str != "*":
            allowed = {o.strip() for o in allowed_origins_str.split(",") if o.strip()}
            # Extrair host da origem
            import re
            origin_host = re.sub(r"^https?://", "", origin).split(":")[0]
            if not any(origin_host in ao for ao in allowed) and origin not in allowed:
                log.warning("[WS_GUARD] Origem WS bloqueada: %s", origin)
                return False, f"Origem {origin} não autorizada"

    log.debug("[WS_GUARD] WS permitido: %s", client_ip)
    return True, ""
