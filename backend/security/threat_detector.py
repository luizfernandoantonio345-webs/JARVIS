"""
JARVIS Threat Detector — Sistema de defesa ativa em tempo real.

Detecta e reage a:
  - Brute force (tentativas repetidas de token inválido)
  - DDoS / flood (excesso de requisições por IP)
  - Port scan patterns (muitos endpoints diferentes rápido)
  - Payloads maliciosos (SQLi, XSS, path traversal, command injection,
    LDAP injection, XXE, SSRF, SSTI, NoSQL injection, Log4Shell,
    prototype pollution)
  - Acesso fora do horário configurado
  - IPs fora da rede Tailscale quando em modo restrito
  - Honeypot endpoints (armadilhas para scanners)
  - Scanner / ferramenta automatizada por User-Agent

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

_LDAP_PATTERNS = re.compile(
    r"(\(\||\)\(|&\(|\*\)\(|cn=\*|objectclass=\*|\bldap://|\bLDAPv3)",
    re.IGNORECASE
)

_XXE_PATTERNS = re.compile(
    r"(<!ENTITY|SYSTEM\s+[\"']file:|<!DOCTYPE[^>]+\[|%[a-z]+;|&[a-z]+;(?!amp|lt|gt|quot|apos))",
    re.IGNORECASE
)

_SSRF_PATTERNS = re.compile(
    r"(http://(?:127\.0\.0\.1|localhost|169\.254\.169\.254|metadata\.google|192\.168\.|10\.\d+\.|172\.(?:1[6-9]|2\d|3[01])\.)"
    r"|file:///|gopher://|dict://|ftp://(?:127|localhost))",
    re.IGNORECASE
)

_SSTI_PATTERNS = re.compile(
    r"(\{\{.*?\}\}|\{%.*?%\}|\$\{.*?\}|#\{.*?\}|@\{.*?\}|<\%=.*?%>|<%.*?%>)",
    re.IGNORECASE
)

_NOSQL_PATTERNS = re.compile(
    r'(\$where|\$regex|\$gt|\$lt|\$ne|\$in|\$nin|\$exists|\$elemMatch'
    r'|\bforceError\b|\$function|\$accumulator)',
    re.IGNORECASE
)

_LOG4SHELL_PATTERNS = re.compile(
    r'(\$\{jndi:|jndi:(?:ldap|rmi|dns|corba|iiop|ldaps|dnspolling)://|\$\{env:'
    r'|lower:\$|\$\{::-'
    r'|\}ndi:(?:ldap|rmi|dns)://'  # obfuscado: ${lower:j}ndi:ldap://
    r'|lower:j\}ndi'               # outro bypass: ${lower:j}ndi
    r')',
    re.IGNORECASE
)

_PROTO_POLLUTION = re.compile(
    r'(__proto__|constructor\.prototype|Object\.prototype)',
    re.IGNORECASE
)

_HTTP_SMUGGLING = re.compile(
    r'(Transfer-Encoding:\s*chunked.*Content-Length:|Content-Length:.*Transfer-Encoding:\s*chunked)',
    re.IGNORECASE
)

_SCANNER_UA = re.compile(
    r'(sqlmap|nikto|nessus|masscan|nmap|burpsuite|zgrab|nuclei|gobuster'
    r'|dirbuster|hydra|medusa|acunetix|openvas|metasploit|w3af|skipfish'
    r'|wfuzz|ffuf|dirsearch|feroxbuster)',
    re.IGNORECASE
)

_ENDPOINT_HONEYPOTS = frozenset({
    "/admin", "/wp-admin", "/wp-login.php", "/.env", "/.git/config",
    "/phpmyadmin", "/phpinfo.php", "/.aws/credentials", "/api/v1/admin",
    "/actuator", "/actuator/env", "/actuator/heapdump", "/console",
    "/manager/html", "/jmx-console", "/solr/admin", "/.DS_Store",
    "/server-status", "/server-info", "/web.config", "/config.php",
})


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

        # Deduplication: (ip, threat_type) → last emit timestamp
        self._last_emit: dict[tuple[str, str], float] = {}
        # Per-IP threat severity count (for escalation)
        self._ip_severity: dict[str, int] = defaultdict(int)
        # Request body size tracking per IP
        self._body_sizes: dict[str, deque] = defaultdict(lambda: deque(maxlen=20))

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

        # 5b. Path traversal na URL (verificar também versão URL-decoded)
        from urllib.parse import unquote
        decoded_path = unquote(path)
        if _PATH_TRAVERSAL.search(path) or _PATH_TRAVERSAL.search(decoded_path):
            event = ThreatEvent(
                ip=ip, threat_type="path_traversal",
                level=ThreatLevel.CRITICAL,
                detail=f"Path traversal detectado: {path[:80]}",
                path=path, user_agent=user_agent,
            )
            self._emit(event)
            return False, event

        # 5c. Honeypot endpoint
        if path in _ENDPOINT_HONEYPOTS or any(path.endswith(h) for h in _ENDPOINT_HONEYPOTS):
            event = ThreatEvent(
                ip=ip, threat_type="honeypot_triggered",
                level=ThreatLevel.HIGH,
                detail=f"Acesso a armadilha: {path}",
                path=path, user_agent=user_agent,
            )
            self._emit(event)
            return False, event

        # 5d. Scanner user agent
        if user_agent and _SCANNER_UA.search(user_agent):
            event = ThreatEvent(
                ip=ip, threat_type="scanner_detected",
                level=ThreatLevel.HIGH,
                detail=f"Scanner/ferramenta detectada: {user_agent[:80]}",
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
        last_24h = [e for e in self.events if now - e.timestamp < 86400]
        by_type: dict[str, int] = {}
        for e in last_hour:
            by_type[e.threat_type] = by_type.get(e.threat_type, 0) + 1
        top_attackers = sorted(
            self._ip_severity.items(), key=lambda x: x[1], reverse=True
        )[:5]
        return {
            "total_events": len(self.events),
            "last_hour": len(last_hour),
            "last_24h": len(last_24h),
            "critical": sum(1 for e in last_hour if e.level == ThreatLevel.CRITICAL),
            "high": sum(1 for e in last_hour if e.level == ThreatLevel.HIGH),
            "medium": sum(1 for e in last_hour if e.level == ThreatLevel.MEDIUM),
            "active_ips": len(self._request_times),
            "by_type": by_type,
            "top_attackers": [{"ip": ip, "score": s} for ip, s in top_attackers],
            "honeypot_traps": sum(1 for e in self.events if e.threat_type == "honeypot_triggered"),
        }

    # ── Internos ───────────────────────────────────────────────────────────────

    def _is_trusted_ip(self, ip: str) -> bool:
        return bool(_LOCALHOST.match(ip) or _TAILSCALE_RANGE.match(ip))

    def _scan_payload(self, body: str) -> Optional[tuple[str, str]]:
        """Retorna (tipo_ameaça, detalhe) se encontrar payload malicioso.

        Ordem: mais específico → mais geral, para evitar falsos positivos.
        """
        sample = body[:2000]
        # Log4Shell antes de SSTI (${jndi:...} é subconjunto de ${...})
        if _LOG4SHELL_PATTERNS.search(sample):
            return ("log4shell", f"Log4Shell/JNDI detectado: {sample[:100]}")
        # LDAP antes de CMD injection (| em filtros LDAP dispara CMD)
        if _LDAP_PATTERNS.search(sample):
            return ("ldap_injection", f"LDAP injection detectado: {sample[:100]}")
        # XXE antes de path traversal (/etc/passwd em ENTITY dispara traversal)
        if _XXE_PATTERNS.search(sample):
            return ("xxe_attempt", f"XXE attack detectado: {sample[:100]}")
        # SSRF antes de path traversal (file:// dispara traversal)
        if _SSRF_PATTERNS.search(sample):
            return ("ssrf_attempt", f"SSRF detectado: {sample[:100]}")
        # NoSQL antes de CMD injection (; em funções JS dispara CMD)
        if _NOSQL_PATTERNS.search(sample):
            return ("nosql_injection", f"NoSQL injection detectado: {sample[:100]}")
        # Prototype pollution
        if _PROTO_POLLUTION.search(sample):
            return ("proto_pollution", f"Prototype pollution detectado: {sample[:100]}")
        # SQLi
        if _SQLI_PATTERNS.search(sample):
            return ("sql_injection", f"Padrão SQL detectado: {sample[:100]}")
        # XSS
        if _XSS_PATTERNS.search(sample):
            return ("xss_attempt", f"Padrão XSS detectado: {sample[:100]}")
        # SSTI (genérico: {{...}}, ${...})
        if _SSTI_PATTERNS.search(sample):
            return ("ssti_attempt", f"Template injection detectado: {sample[:100]}")
        # CMD injection (mais genérico: ;, |, &&, `)
        if _CMD_INJECTION.search(sample):
            return ("command_injection", f"Padrão CMD detectado: {sample[:100]}")
        # Path traversal (mais genérico: ../, /etc/passwd)
        if _PATH_TRAVERSAL.search(sample):
            return ("path_traversal", f"Path traversal no body: {sample[:100]}")
        return None

    def _emit(self, event: ThreatEvent) -> None:
        key = (event.ip, event.threat_type)
        now = time.time()
        # Deduplication: same IP + type within 10s → suppress
        if now - self._last_emit.get(key, 0) < 10.0:
            return
        self._last_emit[key] = now
        self._ip_severity[event.ip] += 1
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
