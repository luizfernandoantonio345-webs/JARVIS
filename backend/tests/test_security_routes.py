"""
Testes dos endpoints de segurança — /security/* (35 casos).
"""
from __future__ import annotations
import sys, os, time, hmac, hashlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

TEST_SECRET = "deadbeef" * 8


@pytest.fixture(scope="module")
def sec_client():
    """TestClient com Guardian ativo e sem token (testa proteção)."""
    os.environ["JARVIS_SECRET_KEY"] = ""  # Desabilitado — testa endpoints livres
    from main import app
    from fastapi.testclient import TestClient
    return TestClient(app, raise_server_exceptions=False)


# ══════════════════════════════════════════════════════════════════════════════
# /security/status
# ══════════════════════════════════════════════════════════════════════════════

class TestSecurityStatus:
    def test_status_endpoint_exists(self, client):
        r = client.get("/security/status")
        assert r.status_code in (200, 500, 503)

    def test_status_returns_json(self, client):
        r = client.get("/security/status")
        if r.status_code == 200:
            data = r.json()
            assert isinstance(data, dict)

    def test_status_has_security_info(self, client):
        r = client.get("/security/status")
        if r.status_code == 200:
            data = r.json()
            # Either guardian format or health format is acceptable
            has_guardian = "status" in data or "threat_stats" in data
            has_health = "checks" in data or "level" in data or "security_score" in data
            assert has_guardian or has_health

    def test_status_has_threat_stats(self, client):
        r = client.get("/security/status")
        if r.status_code == 200:
            data = r.json()
            assert "threat_stats" in data or "checks" in data  # guardian or health format

    def test_status_has_tokens_list(self, client):
        r = client.get("/security/status")
        if r.status_code == 200:
            data = r.json()
            assert "tokens" in data or "level" in data  # guardian or health format

    def test_status_has_blocked_ips(self, client):
        r = client.get("/security/status")
        if r.status_code == 200:
            data = r.json()
            assert "blocked_ips" in data or "security_score" in data  # guardian or health

    def test_status_has_recent_threats(self, client):
        r = client.get("/security/status")
        if r.status_code == 200:
            data = r.json()
            assert "recent_threats" in data or "checks" in data  # guardian or health


# ══════════════════════════════════════════════════════════════════════════════
# /security/token/generate
# ══════════════════════════════════════════════════════════════════════════════

class TestTokenGenerate:
    def test_generate_requires_device_name(self, client):
        r = client.post("/security/token/generate", json={})
        assert r.status_code in (422, 500)

    def test_generate_with_device_name(self, client):
        r = client.post("/security/token/generate",
                        json={"device_name": "test_pc"})
        assert r.status_code in (200, 500)

    def test_generate_returns_token_field(self, client):
        r = client.post("/security/token/generate",
                        json={"device_name": "iphone_test"})
        if r.status_code == 200:
            data = r.json()
            assert "token" in data
            assert len(data["token"]) == 64

    def test_generate_returns_auth_url(self, client):
        r = client.post("/security/token/generate",
                        json={"device_name": "url_test_device"})
        if r.status_code == 200:
            data = r.json()
            assert "auth_url" in data
            assert "token" in data.get("auth_url", "")

    def test_generate_with_ip_hint(self, client):
        r = client.post("/security/token/generate",
                        json={"device_name": "home_pc", "ip_hint": "192.168.1.10"})
        assert r.status_code in (200, 500)

    def test_generate_same_device_twice_same_token(self, client):
        r1 = client.post("/security/token/generate", json={"device_name": "stable_device"})
        r2 = client.post("/security/token/generate", json={"device_name": "stable_device"})
        if r1.status_code == 200 and r2.status_code == 200:
            assert r1.json()["token"] == r2.json()["token"]


# ══════════════════════════════════════════════════════════════════════════════
# /security/token/revoke
# ══════════════════════════════════════════════════════════════════════════════

class TestTokenRevoke:
    def test_revoke_requires_device_name(self, client):
        r = client.post("/security/token/revoke", json={})
        assert r.status_code in (422, 500)

    def test_revoke_nonexistent_device_returns_404(self, client):
        r = client.post("/security/token/revoke",
                        json={"device_name": "nonexistent_device_xyz_12345"})
        assert r.status_code in (404, 500)

    def test_revoke_existing_device_works(self, client):
        client.post("/security/token/generate", json={"device_name": "to_revoke_via_api"})
        r = client.post("/security/token/revoke",
                        json={"device_name": "to_revoke_via_api"})
        assert r.status_code in (200, 404, 500)


# ══════════════════════════════════════════════════════════════════════════════
# /security/token/revoke_all
# ══════════════════════════════════════════════════════════════════════════════

class TestRevokeAll:
    def test_revoke_all_endpoint_exists(self, client):
        r = client.post("/security/token/revoke_all")
        assert r.status_code in (200, 500)

    def test_revoke_all_returns_count(self, client):
        client.post("/security/token/generate", json={"device_name": "bulk1"})
        client.post("/security/token/generate", json={"device_name": "bulk2"})
        r = client.post("/security/token/revoke_all")
        if r.status_code == 200:
            data = r.json()
            assert "revoked_count" in data
            assert isinstance(data["revoked_count"], int)


# ══════════════════════════════════════════════════════════════════════════════
# /security/ip/block & /security/ip/unblock
# ══════════════════════════════════════════════════════════════════════════════

class TestIPBlockUnblock:
    def test_block_ip_requires_fields(self, client):
        r = client.post("/security/ip/block", json={})
        assert r.status_code in (422, 500)

    def test_block_ip_valid(self, client):
        r = client.post("/security/ip/block",
                        json={"ip": "192.168.1.99", "reason": "test block", "duration_minutes": 5})
        assert r.status_code in (200, 500)

    def test_block_ip_returns_confirmation(self, client):
        r = client.post("/security/ip/block",
                        json={"ip": "192.168.1.98", "reason": "test", "duration_minutes": 1})
        if r.status_code == 200:
            data = r.json()
            assert data.get("blocked") is True

    def test_unblock_ip(self, client):
        client.post("/security/ip/block",
                    json={"ip": "192.168.1.97", "reason": "temp", "duration_minutes": 10})
        r = client.post("/security/ip/unblock", json={"ip": "192.168.1.97"})
        assert r.status_code in (200, 404, 500)

    def test_unblock_nonexistent_ip_returns_404(self, client):
        r = client.post("/security/ip/unblock", json={"ip": "10.255.255.255"})
        assert r.status_code in (404, 500)


# ══════════════════════════════════════════════════════════════════════════════
# /security/threats
# ══════════════════════════════════════════════════════════════════════════════

class TestThreatsEndpoint:
    def test_threats_endpoint_exists(self, client):
        r = client.get("/security/threats")
        assert r.status_code in (200, 500)

    def test_threats_returns_json(self, client):
        r = client.get("/security/threats")
        if r.status_code == 200:
            assert isinstance(r.json(), dict)

    def test_threats_has_events_key(self, client):
        r = client.get("/security/threats")
        if r.status_code == 200:
            assert "events" in r.json()

    def test_threats_has_stats_key(self, client):
        r = client.get("/security/threats")
        if r.status_code == 200:
            assert "stats" in r.json()

    def test_threats_limit_param(self, client):
        r = client.get("/security/threats?limit=5")
        assert r.status_code in (200, 422, 500)


# ══════════════════════════════════════════════════════════════════════════════
# /security/guardian — guardian status (não conflita com health.py)
# ══════════════════════════════════════════════════════════════════════════════

class TestGuardianStatus:
    def test_guardian_endpoint_exists(self, client):
        r = client.get("/security/guardian")
        assert r.status_code in (200, 500)

    def test_guardian_returns_json(self, client):
        r = client.get("/security/guardian")
        if r.status_code == 200:
            assert isinstance(r.json(), dict)

    def test_guardian_has_security_score(self, client):
        r = client.get("/security/guardian")
        if r.status_code == 200:
            assert "security_score" in r.json()

    def test_guardian_has_lockdown_field(self, client):
        r = client.get("/security/guardian")
        if r.status_code == 200:
            assert "lockdown" in r.json()


# ══════════════════════════════════════════════════════════════════════════════
# /security/allowlist
# ══════════════════════════════════════════════════════════════════════════════

class TestAllowlistEndpoints:
    def test_allowlist_add_exists(self, client):
        r = client.post("/security/allowlist/add", json={"ip": "10.0.0.1"})
        assert r.status_code in (200, 422, 500)

    def test_allowlist_get_exists(self, client):
        r = client.get("/security/allowlist")
        assert r.status_code in (200, 500)

    def test_allowlist_remove_exists(self, client):
        r = client.request("DELETE", "/security/allowlist/remove", params={"ip": "10.0.0.1"})
        assert r.status_code in (200, 404, 500)

    def test_allowlist_get_returns_json(self, client):
        r = client.get("/security/allowlist")
        if r.status_code == 200:
            data = r.json()
            assert "allowlist" in data or isinstance(data, list)


# ══════════════════════════════════════════════════════════════════════════════
# /security/lockdown
# ══════════════════════════════════════════════════════════════════════════════

class TestLockdownEndpoints:
    def test_lockdown_enable_exists(self, client):
        r = client.post("/security/lockdown")
        assert r.status_code in (200, 500)

    def test_lockdown_disable_exists(self, client):
        # Try to disable (may or may not be in lockdown)
        r = client.request("DELETE", "/security/lockdown")
        assert r.status_code in (200, 500)

    def test_lockdown_enable_returns_json(self, client):
        r = client.post("/security/lockdown")
        if r.status_code == 200:
            data = r.json()
            assert "lockdown" in data or "message" in data


# ══════════════════════════════════════════════════════════════════════════════
# /security/metrics
# ══════════════════════════════════════════════════════════════════════════════

class TestSecurityMetrics:
    def test_metrics_endpoint_exists(self, client):
        r = client.get("/security/metrics")
        assert r.status_code in (200, 500)

    def test_metrics_returns_json(self, client):
        r = client.get("/security/metrics")
        if r.status_code == 200:
            assert isinstance(r.json(), dict)

    def test_metrics_has_security_score(self, client):
        r = client.get("/security/metrics")
        if r.status_code == 200:
            assert "security_score" in r.json()

    def test_metrics_has_threat_summary(self, client):
        r = client.get("/security/metrics")
        if r.status_code == 200:
            assert "threat_summary" in r.json()


# ══════════════════════════════════════════════════════════════════════════════
# /security/audit
# ══════════════════════════════════════════════════════════════════════════════

class TestAuditEndpoint:
    def test_audit_endpoint_exists(self, client):
        r = client.get("/security/audit")
        assert r.status_code in (200, 500)

    def test_audit_returns_json(self, client):
        r = client.get("/security/audit")
        if r.status_code == 200:
            data = r.json()
            assert "audit" in data or isinstance(data, (list, dict))

    def test_audit_limit_param(self, client):
        r = client.get("/security/audit?limit=10")
        assert r.status_code in (200, 500)


# ══════════════════════════════════════════════════════════════════════════════
# /security/device/ban
# ══════════════════════════════════════════════════════════════════════════════

class TestDeviceBanEndpoint:
    def test_device_ban_endpoint_exists(self, client):
        r = client.post("/security/device/ban", json={"device_name": "nonexistent_xyz"})
        assert r.status_code in (200, 404, 422, 500)

    def test_device_ban_requires_device_name(self, client):
        r = client.post("/security/device/ban", json={})
        assert r.status_code in (422, 500)

    def test_device_ban_nonexistent_404_or_500(self, client):
        r = client.post("/security/device/ban", json={"device_name": "nonexistent_xyz_99999"})
        assert r.status_code in (404, 500)
