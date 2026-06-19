"""
JARVIS Guardian — Orquestrador de segurança e auto-defesa.

Conecta AuthManager + ThreatDetector e define a resposta automática:
  - Recebe eventos do ThreatDetector
  - Decide quando banir IPs (com duração progressiva)
  - Transmite alertas via WebSocket para o frontend
  - Mantém log de auditoria persistente
  - Expõe métricas de segurança para o dashboard
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Callable, Optional

from .auth_manager import AuthManager, get_auth_manager
from .threat_detector import ThreatDetector, ThreatEvent, ThreatLevel, init_threat_detector

if TYPE_CHECKING:
    pass

log = logging.getLogger("jarvis.security.guardian")


class JarvisGuardian:
    """
    Ponto central de segurança do JARVIS.
    Instancia auth + detector e coordena as respostas a ameaças.
    """

    def __init__(self, secret_key: str, tailscale_only: bool = False):
        self.auth = AuthManager(secret_key)
        self.detector = init_threat_detector(
            on_threat=self._handle_threat,
            tailscale_only=tailscale_only,
        )
        # Callbacks registrados pelo WebSocket broadcaster
        self._alert_callbacks: list[Callable] = []
        self._started_at = time.time()
        log.info("[GUARDIAN] Defesas do JARVIS ativas.")

    # ── WebSocket alertas ──────────────────────────────────────────────────────

    def register_alert_callback(self, cb: Callable) -> None:
        """Registra callback para broadcast de alertas (chamado pelo WS)."""
        if cb not in self._alert_callbacks:
            self._alert_callbacks.append(cb)

    def unregister_alert_callback(self, cb: Callable) -> None:
        self._alert_callbacks = [c for c in self._alert_callbacks if c != cb]

    # ── Middleware de requisição ───────────────────────────────────────────────

    def check_request(
        self,
        ip: str,
        path: str,
        method: str,
        body: str = "",
        user_agent: str = "",
        token: str = "",
    ) -> tuple[bool, int, str]:
        """
        Ponto único de verificação de segurança.
        Retorna (permitido, http_status, mensagem).
        """
        # 1. IP bloqueado?
        blocked, reason = self.auth.is_ip_blocked(ip)
        if blocked:
            log.warning("[GUARDIAN] IP bloqueado tentou acesso: %s — %s", ip, reason)
            return False, 403, f"Acesso negado: {reason}"

        # 2. Rotas públicas (não exigem token)
        if self._is_public_path(path):
            ok, event = self.detector.inspect_request(
                ip=ip, path=path, method=method,
                body=body, user_agent=user_agent, auth_ok=True
            )
            if not ok and event:
                self._auto_ban(ip, event)
                return False, 429, event.detail
            return True, 200, ""

        # 3. Validar token
        token_ok, device_name = self.auth.validate_token(token, ip)
        ok, event = self.detector.inspect_request(
            ip=ip, path=path, method=method,
            body=body, user_agent=user_agent, auth_ok=token_ok
        )

        if not token_ok:
            should_ban, failures = self.detector.record_auth_failure(ip, path)
            if should_ban:
                self._auto_ban(ip, ThreatEvent(
                    ip=ip, threat_type="brute_force",
                    level=ThreatLevel.CRITICAL,
                    detail=f"Brute force: {failures} falhas de autenticação",
                    path=path,
                ))
                return False, 403, "IP banido por múltiplas tentativas inválidas"
            return False, 401, f"Token inválido (tentativa {failures}/{self.detector.max_auth_failures})"

        if not ok and event:
            self._auto_ban(ip, event)
            status = 429 if event.threat_type == "rate_limit_exceeded" else 403
            return False, status, event.detail

        return True, 200, device_name

    # ── Auto-ban ──────────────────────────────────────────────────────────────

    def _auto_ban(self, ip: str, event: ThreatEvent) -> None:
        """Bane IP com duração progressiva."""
        duration_secs = self.detector.get_ban_duration(ip)
        duration_mins = duration_secs // 60 if duration_secs > 0 else 0
        self.auth.block_ip(ip, event.detail, duration_minutes=duration_mins)
        log.critical(
            "[GUARDIAN] AUTO-BAN: %s por %dmin — %s",
            ip, duration_mins, event.detail
        )

    # ── Manipulador de ameaças ────────────────────────────────────────────────

    def _handle_threat(self, event: ThreatEvent) -> None:
        """Chamado pelo ThreatDetector quando detecta ameaça."""
        payload = {
            "type": "security_alert",
            "level": event.level,
            "threat": event.threat_type,
            "ip": event.ip,
            "detail": event.detail,
            "path": event.path,
            "time": event.timestamp,
        }
        # Broadcast assíncrono para todos os clientes WS conectados
        for cb in list(self._alert_callbacks):
            try:
                if asyncio.iscoroutinefunction(cb):
                    asyncio.create_task(cb(payload))
                else:
                    cb(payload)
            except Exception as e:
                log.debug("[GUARDIAN] Callback WS falhou: %s", e)

    # ── Dashboard ─────────────────────────────────────────────────────────────

    def security_status(self) -> dict:
        """Dados completos para o endpoint /security/status."""
        return {
            "status": "active",
            "uptime_seconds": int(time.time() - self._started_at),
            "threat_stats": self.detector.stats(),
            "tokens": self.auth.list_tokens(),
            "blocked_ips": self.auth.list_blocked_ips(),
            "recent_threats": self.detector.recent_events(limit=20),
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _is_public_path(path: str) -> bool:
        """Rotas que não exigem token."""
        public = (
            "/health", "/ping", "/sw.js", "/manifest.json",
            "/static/", "/favicon",
        )
        return any(path.startswith(p) for p in public)


# ── Singleton ──────────────────────────────────────────────────────────────────

_guardian: Optional[JarvisGuardian] = None


def get_guardian() -> JarvisGuardian:
    global _guardian
    if _guardian is None:
        raise RuntimeError("Guardian não inicializado — chame init_guardian() no startup")
    return _guardian


def init_guardian(secret_key: str, tailscale_only: bool = False) -> JarvisGuardian:
    global _guardian
    _guardian = JarvisGuardian(secret_key, tailscale_only=tailscale_only)
    return _guardian
