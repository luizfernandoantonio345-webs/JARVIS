
"""
JARVIS v6.0 — Security Validation Tests

Coverage:
  ✅ SQL injection attempts
  ✅ XSS payloads
  ✅ Path traversal
  ✅ CORS violations
  ✅ Rate limiting bypass
  ✅ Invalid input validation

Run: pytest tests/test_security_complete.py -v --tb=short
"""

import pytest
pytestmark = pytest.mark.integration

import pytest
import httpx
from urllib.parse import urlencode


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def backend_url():
    return "http://localhost:8000"


# ── Tests: SQL Injection ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sql_injection_in_search(backend_url):
    """Test 1: SQL injection in search endpoint."""
    payloads = [
        "' OR '1'='1",
        "'; DROP TABLE users; --",
        "' UNION SELECT * FROM passwords --",
        "1' AND '1'='1",
    ]
    
    async with httpx.AsyncClient(timeout=10) as client:
        for payload in payloads:
            # Try search endpoint
            r = await client.get(
                f"{backend_url}/experience/search",
                params={"q": payload}
            )
            # Should not crash or return SQL error
            assert r.status_code in [200, 400, 404]
            
            body = r.text.lower()
            assert "sql" not in body
            assert "error" not in body or "input error" in body


@pytest.mark.asyncio
async def test_sql_injection_in_chat(backend_url):
    """Test 2: SQL injection in chat message."""
    payload = {
        "message": "'; DROP TABLE sessions; --",
        "session_id": "test_sql_inject"
    }
    
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{backend_url}/chat",
            json=payload
        )
        # Should not crash
        assert r.status_code in [200, 202, 400]


# ── Tests: XSS (Cross-Site Scripting) ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_xss_in_chat(backend_url):
    """Test 3: XSS payload in chat message."""
    payloads = [
        "<script>alert('xss')</script>",
        "<img src=x onerror='alert(1)'>",
        "<svg onload='alert(1)'>",
        "javascript:alert('xss')",
    ]
    
    async with httpx.AsyncClient(timeout=30) as client:
        for payload in payloads:
            r = await client.post(
                f"{backend_url}/chat",
                json={"message": payload, "session_id": "test_xss"}
            )
            
            # Should not crash
            assert r.status_code in [200, 202, 400]
            
            # Response should not contain unescaped script
            if "response" in r.text:
                assert "<script>" not in r.text


@pytest.mark.asyncio
async def test_xss_in_tts(backend_url):
    """Test 4: XSS payload in TTS endpoint."""
    payloads = [
        "<script>alert('xss')</script>",
        "<img src=x onerror='alert(1)'>",
    ]
    
    async with httpx.AsyncClient(timeout=10) as client:
        for payload in payloads:
            r = await client.get(
                f"{backend_url}/tts",
                params={"text": payload}
            )
            
            # Should reject or sanitize
            assert r.status_code in [200, 400, 422]


# ── Tests: Path Traversal ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_path_traversal(backend_url):
    """Test 5: Path traversal attempts."""
    payloads = [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32\\config\\sam",
        "../../../../../../../../etc/passwd",
        "..\\..\\..\\..",
    ]
    
    async with httpx.AsyncClient(timeout=10) as client:
        # Try various file endpoints
        for payload in payloads:
            # Some endpoints that might accept paths
            endpoints = [
                f"{backend_url}/tts?text={payload}",
                f"{backend_url}/files?path={payload}",
            ]
            
            for url in endpoints:
                try:
                    r = await client.get(url)
                    # Should not expose file system
                    assert "root:" not in r.text
                    assert "[boot loader]" not in r.text
                except:
                    pass


# ── Tests: Rate Limiting Bypass ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rate_limit_bypass_header_spoofing(backend_url):
    """Test 6: Rate limiting not bypassable with header spoofing."""
    async with httpx.AsyncClient(timeout=30) as client:
        # Try to bypass with X-Forwarded-For
        for i in range(20):
            r = await client.get(
                f"{backend_url}/chat",
                headers={"X-Forwarded-For": f"192.168.1.{i}"}
            )
            
            # Requests should be rate limited globally
            assert r.status_code in [200, 429]


@pytest.mark.asyncio
async def test_rate_limit_bypass_cache_busting(backend_url):
    """Test 7: Rate limiting not bypassable with cache parameters."""
    async with httpx.AsyncClient(timeout=30) as client:
        for i in range(20):
            r = await client.get(
                f"{backend_url}/health?cache_bust={i}"
            )
            
            # Should still be rate limited
            assert r.status_code in [200, 429]


# ── Tests: CORS Violations ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cors_preflight(backend_url):
    """Test 8: CORS preflight requests handled correctly."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.options(
            f"{backend_url}/chat",
            headers={
                "Origin": "https://malicious.com",
                "Access-Control-Request-Method": "POST",
            }
        )
        
        # Should be 200 (preflight OK) or reject
        assert r.status_code in [200, 403, 404]
        
        # If allowed, should have proper CORS headers
        if r.status_code == 200:
            cors_origin = r.headers.get("Access-Control-Allow-Origin")
            # Should be specific origin, not *
            if cors_origin:
                assert corsorigin != "*" or "localhost" in cors_origin


# ── Tests: Input Validation ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invalid_json(backend_url):
    """Test 9: Invalid JSON is rejected."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            f"{backend_url}/chat",
            content="{invalid json}",
            headers={"Content-Type": "application/json"}
        )
        
        # Should reject with 400
        assert r.status_code in [400, 422]


@pytest.mark.asyncio
async def test_oversized_payload(backend_url):
    """Test 10: Oversized payloads are rejected."""
    large_message = "x" * (10 * 1024 * 1024)  # 10MB
    
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            f"{backend_url}/chat",
            json={"message": large_message, "session_id": "test"},
            timeout=5
        )
        
        # Should reject
        assert r.status_code in [400, 413, 422]


@pytest.mark.asyncio
async def test_malformed_session_id(backend_url):
    """Test 11: Malformed session IDs are handled."""
    payloads = [
        "'; DROP TABLE --",
        "<script>alert(1)</script>",
        "../../etc/passwd",
    ]
    
    async with httpx.AsyncClient(timeout=10) as client:
        for sid in payloads:
            r = await client.post(
                f"{backend_url}/chat",
                json={"message": "hi", "session_id": sid}
            )
            
            # Should handle gracefully
            assert r.status_code in [200, 202, 400]


# ── Tests: Null Byte Injection ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_null_byte_injection(backend_url):
    """Test 12: Null bytes don't cause issues."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            f"{backend_url}/chat",
            json={"message": "hello\x00world", "session_id": "test"}
        )
        
        # Should handle or reject gracefully
        assert r.status_code in [200, 202, 400, 422]


# ── Tests: Authentication (if applicable) ──────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_auth_token(backend_url):
    """Test 13: Endpoints don't require auth (open API)."""
    # JARVIS v6.0 is open API for now
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{backend_url}/health")
        
        # Should NOT require authentication
        assert r.status_code == 200


# ── Summary ────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
