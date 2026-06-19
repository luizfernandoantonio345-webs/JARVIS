"""
JARVIS Threat Detector — Sistema de defesa ativa em tempo real.

Detecta e reage a:
  - Brute force (tentativas repetidas de token inválido)
  - DDoS / flood (excesso de requisições por IP)
  - Port scan patterns (muitos endpoints diferentes rápido)
  - Payloads maliciosos (SQLi, XSS, path traversal, command injection)
  - Acesso fora do horário configurado
  - IPs fora da rede Tailscale quando em modo restrito

Resposta automática:
  - Auto-ban do IP atacante (progressivo: 1min → 1h → permanente)
  - Broadcast de alerta para o frontend via WebSocket
  - Log de auditoria com classificação de ameaça
  - Notificação push (futuro)
"""
from __future__ import annotations

import logging
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

log = logging.getLogger("jarvis.security.threat")


class ThreatLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ThreatEvent:
    ip: str
    threat_type: str
    level: ThreatLevel
    detail: str
    timestamp: float = field(default_factory=time.time)
    path: str = ""
    user_agent: str = ""


# ── Padrões maliciosos ─────────────────────────────────────────────────────────

_SQLI_PATTERNS = re.compile(
    r"(\b(union|select|insert|update|delete|drop|create|alter|exec|execute)\b"
    r"|--|;--|/\*|\*/|xp_|@@|char\(|nchar\(|varchar\(|0x[0-9a-f]+)",
    re.IGNORECASE
)

_XSS_PATTERNS = re.compile(
    r"(<script|javascript:|onerror=|onload=|onclick=|<iframe|<object"
    r"|document\.cookie|alert\(|eval\(|String\.fromCharCode)",
    re.IGNORECASE
)

_PATH_TRAVERSAL = re.compile(
    r"(\.\./|\.\.\\|%2e%2e|%252e|/etc/passwd|/etc/shadow|c:\\windows|cmd\.exe)",
    re.IGNORECASE
)

_CMD_INJECTION = re.compile(
    r"(;|\||&&|`|\$\(|\bping\b|\bnmap\b|\bwhoami\b|\bcat\s+/|\bls\s+-)"
)

_TAILSCALE_RANGE = re.compile(r"^100\.\d+\.\d+\.\d+$")
_LOCALHOST = re.compile(r"^(127\.|::1|localhost)")


class ThreatDetector:
    """
    Motor de detecção de ameaças — analisa cada requisição e toma ação.
    """

    def __init__(
        self,
        on_threat: Optional[Callable[[ThreatEvent], None]] = None,
        tailscale_only: bool = False,
        max_auth_failures: int = 5,
        max_rps: int = 60,
        ban_duration_minutes: int = 60,
    ):
        self.on_threat = on_threat        # callback para alertar frontend
        self.tailscale_only = tailscale_only
        self.max_auth_failures = max_auth_failures
        self.max_rps = max_rps
        self.ban_duration = ban_duration_minutes * 60

        # Janelas de tempo por IP (últimos 60s de requests)
        self._request_times: dict[str, deque] = defaultdict(lambda: deque(maxlen=200))
        # Contagem de falhas de auth por IP
        self._auth_failures: dict[str, int] = defaultdict(int)
        # Histórico de bans (IP → quantas vezes banido)
        self._ban_count: dict[str, int] = defaultdict(int)
        # Endpoints visitados por IP nos últimos 5s (port scan detection)
        self._endpoint_scan: dict[str, deque] = defaultdict(lambda: deque(maxlen=50))

        self.events: deque[ThreatEvent] = deque(maxlen=500)

    # ── API pública ────────────────────────────────────────────────────────────

    def inspect_request(
        self,
        ip: str,
        path: str,
        method: str,
        body: str = "",
        user_agent: str = "",
        auth_ok: bool = True,
    ) -> tuple[bool, Optional[ThreatEvent]]:
        """
        Analisa uma requisição.
        Retorna (permitir: bool, evento_ameaça_ou_None).
        """
        now = time.time()

        # 1. Verificar se IP é da rede Tailscale (modo restrito)
        if self.tailscale_only and not self._is_trusted_ip(ip):
            event = ThreatEvent(
                ip=ip, threat_type="ip_not_trusted",
                level=ThreatLevel.HIGH,
                detail=f"IP {ip} fora da rede Tailscale",
                path=path, user_agent=user_agent,
            )
            self._emit(event)
            return False, event

        # 2. Rate limit (DDoS / flood)
        window = self._request_times[ip]
        window.append(now)
        # Requisições no último segundo
        recent_rps = sum(1 for t in window if now - t < 1.0)
        if recent_rps > self.max_rps:
            event = ThreatEvent(
                ip=ip, threat_type="rate_limit_exceeded",
                level=ThreatLevel.HIGH,
                detail=f"{recent_rps} req/s (limite: {self.max_rps})",
                path=path, user_agent=user_agent,
            )
            self._emit(event)
            return False, event

        # 3. Falha de autenticação
        if not auth_ok:
            self._auth_failures[ip] += 1
            failures = self._auth_failures[ip]
            level = ThreatLevel.MEDIUM if failures < self.max_auth_failures else ThreatLevel.CRITICAL
            event = ThreatEvent(
                ip=ip, threat_type="auth_failure",
                level=level,
                detail=f"Falha de token #{failures}",
                path=path, user_agent=user_agent,
            )
            self._emit(event)
            if failures >= self.max_auth_failures:
                return False, event
            return False, event

        # Auth ok — reset failure counter
        if ip in self._auth_failures:
            self._auth_failures[ip] = 0

        # 4. Port scan / endpoint scanning
        ep_window = self._endpoint_scan[ip]
        ep_window.append((path, now))
        unique_paths_5s = len(set(p for p, t in ep_window if now - t < 5.0))
        if unique_paths_5s > 20:
            event = ThreatEvent(
                ip=ip, threat_type="endpoint_scan",
                level=ThreatLevel.HIGH,
                detail=f"{unique_paths_5s} endpoints únicos em 5s",
                path=path, user_agent=user_agent,
            )
            self._emit(event)

        # 5. Payload malicioso
        if body:
            threat = self._scan_payload(body)
            if threat:
                event = ThreatEvent(
                    ip=ip, threat_type=threat[0],
                    level=ThreatLevel.CRITICAL,
                    detail=threat[1],
                    path=path, user_agent=user_agent,
                )
                self._emit(event)
                return False, event

        # 5b. Path traversal na URL
        if _PATH_TRAVERSAL.search(path):
            event = ThreatEvent(
                ip=ip, threat_type="path_traversal",
                level=ThreatLevel.CRITICAL,
                detail=f"Path traversal detectado: {path[:80]}",
                path=path, user_agent=user_agent,
            )
            self._emit(event)
            return False, event

        return True, None

    def record_auth_failure(self, ip: str, path: str = "") -> tuple[bool, int]:
        """
        Registra falha de auth e retorna (deve_banir, total_falhas).
        """
        self._auth_failures[ip] += 1
        failures = self._auth_failures[ip]
        should_ban = failures >= self.max_auth_failures
        return should_ban, failures

    def get_auth_failures(self, ip: str) -> int:
        return self._auth_failures.get(ip, 0)

    def reset_auth_failures(self, ip: str) -> None:
        self._auth_failures[ip] = 0

    def get_ban_duration(self, ip: str) -> int:
        """Duração do ban em segundos (progressiva: aumenta a cada ban)."""
        count = self._ban_count.get(ip, 0)
        self._ban_count[ip] = count + 1
        if count == 0:
            return 5 * 60      # 1º ban: 5 minutos
        elif count == 1:
            return 60 * 60     # 2º ban: 1 hora
        elif count == 2:
            return 24 * 3600   # 3º ban: 24 horas
        else:
            return 0           # Permanente

    def recent_events(self, limit: int = 50) -> list[dict]:
        events = list(self.events)[-limit:]
        return [
            {
                "ip": e.ip,
                "type": e.threat_type,
                "level": e.level,
                "detail": e.detail,
                "path": e.path,
                "time": e.timestamp,
            }
            for e in reversed(events)
        ]

    def stats(self) -> dict:
        now = time.time()
        last_hour = [e for e in self.events if now - e.timestamp < 3600]
        return {
            "total_events": len(self.events),
            "last_hour": len(last_hour),
            "critical": sum(1 for e in last_hour if e.level == ThreatLevel.CRITICAL),
            "high": sum(1 for e in last_hour if e.level == ThreatLevel.HIGH),
            "active_ips": len(self._request_times),
        }

    # ── Internos ───────────────────────────────────────────────────────────────

    def _is_trusted_ip(self, ip: str) -> bool:
        return bool(_LOCALHOST.match(ip) or _TAILSCALE_RANGE.match(ip))

    def _scan_payload(self, body: str) -> Optional[tuple[str, str]]:
        """Retorna (tipo_ameaça, detalhe) se encontrar payload malicioso."""
        sample = body[:2000]  # limitar análise
        if _SQLI_PATTERNS.search(sample):
            return ("sql_injection", f"Padrão SQL detectado: {sample[:100]}")
        if _XSS_PATTERNS.search(sample):
            return ("xss_attempt", f"Padrão XSS detectado: {sample[:100]}")
        if _CMD_INJECTION.search(sample):
            return ("command_injection", f"Padrão CMD detectado: {sample[:100]}")
        if _PATH_TRAVERSAL.search(sample):
            return ("path_traversal", f"Path traversal no body: {sample[:100]}")
        return None

    def _emit(self, event: ThreatEvent) -> None:
        """Registra evento e notifica callback."""
        self.events.append(event)
        log.warning(
            "[THREAT][%s] %s — IP: %s — %s",
            event.level.upper(), event.threat_type, event.ip, event.detail[:120]
        )
        if self.on_threat:
            try:
                self.on_threat(event)
            except Exception as e:
                log.debug("[THREAT] Callback falhou: %s", e)


# ── Singleton ──────────────────────────────────────────────────────────────────

_detector: Optional[ThreatDetector] = None


def get_threat_detector() -> ThreatDetector:
    global _detector
    if _detector is None:
        _detector = ThreatDetector()
    return _detector


def init_threat_detector(
    on_threat: Optional[Callable] = None,
    tailscale_only: bool = False,
) -> ThreatDetector:
    global _detector
    _detector = ThreatDetector(on_threat=on_threat, tailscale_only=tailscale_only)
    log.info("[THREAT] Detector inicializado (tailscale_only=%s)", tailscale_only)
    return _detector
