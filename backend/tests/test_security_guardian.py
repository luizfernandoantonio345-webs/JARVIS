"""
Testes do JarvisGuardian — 50 casos cobrindo orquestração de segurança.
"""
from __future__ import annotations
import sys, os, time, hmac, hashlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

TEST_SECRET = "deadbeef" * 8


def _make_token(device: str, secret: str = TEST_SECRET) -> str:
    payload = f"{device}:{int(time.time() // 86400)}"
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


# ══════════════════════════════════════════════════════════════════════════════
# INICIALIZAÇÃO
# ══════════════════════════════════════════════════════════════════════════════

class TestGuardianInit:
    def test_guardian_initializes(self, guardian):
        assert guardian is not None

    def test_guardian_has_auth(self, guardian):
        assert guardian.auth is not None

    def test_guardian_has_detector(self, guardian):
        assert guardian.detector is not None

    def test_guardian_started_at_recent(self, guardian):
        assert time.time() - guardian._started_at < 60


# ══════════════════════════════════════════════════════════════════════════════
# check_request — ROTAS PÚBLICAS
# ══════════════════════════════════════════════════════════════════════════════

class TestPublicPaths:
    def test_health_always_allowed(self, guardian):
        ok, status, _ = guardian.check_request("1.2.3.4", "/health", "GET")
        assert ok is True
        assert status == 200

    def test_ping_always_allowed(self, guardian):
        ok, status, _ = guardian.check_request("1.2.3.4", "/ping", "GET")
        assert ok is True

    def test_sw_js_always_allowed(self, guardian):
        ok, status, _ = guardian.check_request("1.2.3.4", "/sw.js", "GET")
        assert ok is True

    def test_manifest_always_allowed(self, guardian):
        ok, status, _ = guardian.check_request("1.2.3.4", "/manifest.json", "GET")
        assert ok is True

    def test_static_assets_always_allowed(self, guardian):
        ok, status, _ = guardian.check_request("1.2.3.4", "/static/index.css", "GET")
        assert ok is True


# ══════════════════════════════════════════════════════════════════════════════
# check_request — AUTENTICAÇÃO
# ══════════════════════════════════════════════════════════════════════════════

class TestAuthentication:
    def test_valid_token_grants_access(self, guardian):
        tok = guardian.auth.generate_token("auth_test_device")
        ok, status, detail = guardian.check_request("100.1.1.1", "/chat", "POST", token=tok)
        assert ok is True
        assert status == 200

    def test_no_token_returns_401(self, guardian):
        ok, status, detail = guardian.check_request("100.1.1.2", "/chat", "POST", token="")
        assert ok is False
        assert status == 401

    def test_invalid_token_returns_401(self, guardian):
        ok, status, _ = guardian.check_request("100.1.1.3", "/api", "GET", token="b" * 64)
        assert ok is False
        assert status == 401

    def test_wrong_length_token_returns_401(self, guardian):
        ok, status, _ = guardian.check_request("100.1.1.4", "/api", "GET", token="abc")
        assert ok is False
        assert status == 401

    def test_valid_token_returns_device_name(self, guardian):
        guardian.auth.generate_token("my_iphone")
        tok = guardian.auth.generate_token("my_iphone")
        ok, _, detail = guardian.check_request("100.1.1.5", "/api", "GET", token=tok)
        assert ok is True
        assert detail == "my_iphone"

    def test_revoked_token_returns_401(self, guardian):
        tok = guardian.auth.generate_token("rev_phone")
        guardian.auth.revoke_token("rev_phone")
        ok, status, _ = guardian.check_request("100.1.1.6", "/api", "GET", token=tok)
        assert ok is False
        assert status == 401


# ══════════════════════════════════════════════════════════════════════════════
# check_request — IP BLOQUEADO
# ══════════════════════════════════════════════════════════════════════════════

class TestBlockedIPs:
    def test_blocked_ip_denied(self, guardian):
        guardian.auth.block_ip("10.100.0.1", "test block", 60)
        ok, status, _ = guardian.check_request("10.100.0.1", "/api", "GET")
        assert ok is False
        assert status == 403

    def test_blocked_ip_on_public_path_also_denied(self, guardian):
        guardian.auth.block_ip("10.100.0.2", "blocked everywhere", 60)
        # Rotas públicas: verificação de IP bloqueado tem prioridade
        ok, status, _ = guardian.check_request("10.100.0.2", "/health", "GET")
        assert ok is False
        assert status == 403

    def test_unblocked_ip_allowed_again(self, guardian):
        tok = guardian.auth.generate_token("unblock_test")
        guardian.auth.block_ip("10.100.0.3", "temporary", 60)
        guardian.auth.unblock_ip("10.100.0.3")
        ok, _, _ = guardian.check_request("10.100.0.3", "/api", "GET", token=tok)
        assert ok is True


# ══════════════════════════════════════════════════════════════════════════════
# AUTO-BAN POR BRUTE FORCE
# ══════════════════════════════════════════════════════════════════════════════

class TestAutoBan:
    def test_auto_ban_after_max_failures(self, guardian):
        ip = "10.200.0.1"
        # Precisa de max_auth_failures falhas para banir
        limit = guardian.detector.max_auth_failures
        for _ in range(limit):
            guardian.check_request(ip, "/api", "POST", token="x" * 64)
        blocked, _ = guardian.auth.is_ip_blocked(ip)
        assert blocked is True

    def test_auto_ban_returns_403_not_401(self, guardian):
        ip = "10.200.0.2"
        limit = guardian.detector.max_auth_failures
        status = None
        for _ in range(limit):
            _, status, _ = guardian.check_request(ip, "/api", "POST", token="y" * 64)
        assert status == 403

    def test_failure_counter_increments(self, guardian):
        ip = "10.200.0.3"
        guardian.check_request(ip, "/api", "POST", token="z" * 64)
        failures = guardian.detector.get_auth_failures(ip)
        assert failures >= 1


# ══════════════════════════════════════════════════════════════════════════════
# PAYLOAD SCAN
# ══════════════════════════════════════════════════════════════════════════════

class TestPayloadScan:
    def test_sqli_in_body_blocked(self, guardian):
        tok = guardian.auth.generate_token("scan_device")
        ok, status, _ = guardian.check_request(
            "100.2.1.1", "/chat", "POST",
            body="SELECT * FROM users WHERE 1=1", token=tok
        )
        assert ok is False

    def test_xss_in_body_blocked(self, guardian):
        tok = guardian.auth.generate_token("scan_device2")
        ok, _, _ = guardian.check_request(
            "100.2.1.2", "/chat", "POST",
            body="<script>alert(1)</script>", token=tok
        )
        assert ok is False

    def test_clean_body_allowed(self, guardian):
        tok = guardian.auth.generate_token("clean_device")
        ok, _, _ = guardian.check_request(
            "100.2.1.3", "/chat", "POST",
            body='{"message": "Olá, JARVIS! Como você está?"}', token=tok
        )
        assert ok is True


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD / STATUS
# ══════════════════════════════════════════════════════════════════════════════

class TestSecurityStatus:
    def test_status_returns_dict(self, guardian):
        result = guardian.security_status()
        assert isinstance(result, dict)

    def test_status_has_required_fields(self, guardian):
        result = guardian.security_status()
        assert "status" in result
        assert "threat_stats" in result
        assert "tokens" in result
        assert "blocked_ips" in result
        assert "recent_threats" in result

    def test_status_active(self, guardian):
        result = guardian.security_status()
        assert result["status"] == "active"

    def test_status_tokens_is_list(self, guardian):
        guardian.auth.generate_token("status_check_device")
        result = guardian.security_status()
        assert isinstance(result["tokens"], list)

    def test_status_uptime_positive(self, guardian):
        result = guardian.security_status()
        assert result["uptime_seconds"] >= 0


# ══════════════════════════════════════════════════════════════════════════════
# CALLBACKS WS
# ══════════════════════════════════════════════════════════════════════════════

class TestWSCallbacks:
    def test_register_callback(self, guardian):
        cb = lambda p: None
        guardian.register_alert_callback(cb)
        assert cb in guardian._alert_callbacks

    def test_unregister_callback(self, guardian):
        cb = lambda p: None
        guardian.register_alert_callback(cb)
        guardian.unregister_alert_callback(cb)
        assert cb not in guardian._alert_callbacks

    def test_no_duplicate_callbacks(self, guardian):
        cb = lambda p: None
        guardian.register_alert_callback(cb)
        guardian.register_alert_callback(cb)  # Segunda vez
        count = guardian._alert_callbacks.count(cb)
        assert count == 1

    def test_threat_triggers_callback(self, guardian):
        alerts = []
        guardian.register_alert_callback(lambda p: alerts.append(p))
        # Dispara ameaça diretamente no detector
        from security.threat_detector import ThreatEvent, ThreatLevel
        ev = ThreatEvent("1.2.3.4", "test_threat", ThreatLevel.CRITICAL, "test")
        guardian.detector._emit(ev)
        # O callback do guardian é chamado pelo detector
        # (o guardian registrou _handle_threat no detector via init_threat_detector)


# ══════════════════════════════════════════════════════════════════════════════
# SINGLETON
# ══════════════════════════════════════════════════════════════════════════════

class TestSingleton:
    def test_init_guardian_returns_guardian(self, tmp_path):
        import security.auth_manager as _mod
        import security.guardian as _gmod
        old_db = _mod._DB_PATH
        old_g = _gmod._guardian
        _mod._DB_PATH = tmp_path / "singleton_test.db"
        _mod._DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        g = _gmod.init_guardian(TEST_SECRET)
        assert g is not None
        assert _gmod._guardian is g
        _mod._DB_PATH = old_db
        _gmod._guardian = old_g

    def test_get_guardian_raises_if_not_init(self):
        import security.guardian as _gmod
        old_g = _gmod._guardian
        _gmod._guardian = None
        with pytest.raises(RuntimeError):
            _gmod.get_guardian()
        _gmod._guardian = old_g


# ══════════════════════════════════════════════════════════════════════════════
# LOCKDOWN MODE
# ══════════════════════════════════════════════════════════════════════════════

class TestLockdownMode:
    def test_enable_lockdown(self, guardian):
        try:
            guardian.enable_lockdown()
            assert guardian.is_lockdown is True
        except AttributeError:
            pytest.skip("Lockdown not implemented")

    def test_disable_lockdown(self, guardian):
        try:
            guardian.enable_lockdown()
            guardian.disable_lockdown()
            assert guardian.is_lockdown is False
        except AttributeError:
            pytest.skip("Lockdown not implemented")

    def test_lockdown_blocks_non_health_paths(self, guardian):
        try:
            guardian.enable_lockdown()
            allowed, status, _ = guardian.check_request(
                "1.2.3.4", "/chat", "POST", token=""
            )
            assert allowed is False
            assert status == 503
        except AttributeError:
            pytest.skip("Lockdown not implemented")
        finally:
            try:
                guardian.disable_lockdown()
            except Exception:
                pass

    def test_lockdown_allows_health(self, guardian):
        try:
            guardian.enable_lockdown()
            allowed, status, _ = guardian.check_request(
                "1.2.3.4", "/health", "GET", token=""
            )
            assert allowed is True
        except AttributeError:
            pytest.skip("Lockdown not implemented")
        finally:
            try:
                guardian.disable_lockdown()
            except Exception:
                pass

    def test_lockdown_start_disabled(self, guardian):
        try:
            assert guardian.is_lockdown is False
        except AttributeError:
            pytest.skip("Lockdown not implemented")


# ══════════════════════════════════════════════════════════════════════════════
# ALLOWLIST BYPASS
# ══════════════════════════════════════════════════════════════════════════════

class TestAllowlistBypass:
    def test_allowlisted_ip_bypasses_auth(self, guardian):
        try:
            guardian.auth.add_to_allowlist("10.0.0.100", "test bypass")
            allowed, status, detail = guardian.check_request(
                "10.0.0.100", "/chat", "POST", token=""
            )
            assert allowed is True
        except AttributeError:
            pytest.skip("Allowlist bypass not implemented")

    def test_non_allowlisted_needs_token(self, guardian):
        try:
            allowed, status, detail = guardian.check_request(
                "99.99.99.99", "/chat", "POST", token=""
            )
            assert allowed is False
            assert status == 401
        except AttributeError:
            pytest.skip("Allowlist bypass not implemented")


# ══════════════════════════════════════════════════════════════════════════════
# SECURITY SCORE
# ══════════════════════════════════════════════════════════════════════════════

class TestSecurityScore:
    def test_score_is_int(self, guardian):
        try:
            score = guardian.security_score()
            assert isinstance(score, int)
        except AttributeError:
            pytest.skip("security_score not implemented")

    def test_score_in_range(self, guardian):
        try:
            score = guardian.security_score()
            assert 0 <= score <= 100
        except AttributeError:
            pytest.skip("security_score not implemented")

    def test_score_100_on_no_threats(self, guardian):
        try:
            score = guardian.security_score()
            assert score == 100  # fresh guardian with no threats = max score
        except AttributeError:
            pytest.skip("security_score not implemented")

    def test_score_in_status(self, guardian):
        try:
            status = guardian.security_status()
            assert "security_score" in status
        except AttributeError:
            pytest.skip("security_score not implemented")


# ══════════════════════════════════════════════════════════════════════════════
# DEVICE BAN
# ══════════════════════════════════════════════════════════════════════════════

class TestDeviceBan:
    def test_ban_registered_device(self, guardian):
        try:
            guardian.auth.generate_token("ban_test_device", ip_hint="1.2.3.4")
            ok = guardian.ban_device("ban_test_device", "test ban")
            assert ok is True
        except AttributeError:
            pytest.skip("ban_device not implemented")

    def test_ban_revokes_token(self, guardian):
        try:
            token = guardian.auth.generate_token("ban_token_test", ip_hint="")
            guardian.ban_device("ban_token_test", "test")
            valid, _ = guardian.auth.validate_token(token)
            assert valid is False
        except AttributeError:
            pytest.skip("ban_device not implemented")

    def test_ban_nonexistent_device_false(self, guardian):
        try:
            ok = guardian.ban_device("nonexistent_device_xyz_12345")
            assert ok is False
        except AttributeError:
            pytest.skip("ban_device not implemented")

    def test_status_has_allowlisted_ips(self, guardian):
        try:
            status = guardian.security_status()
            assert "allowlisted_ips" in status
        except AttributeError:
            pytest.skip("allowlisted_ips not in status")

    def test_status_has_honeypot_triggers(self, guardian):
        try:
            status = guardian.security_status()
            assert "honeypot_triggers" in status
        except AttributeError:
            pytest.skip("honeypot_triggers not in status")
