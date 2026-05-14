"""
Security-focused tests for JARVIS.
Validates encryption, rate limiting, and input validation.
"""
import pytest
from fastapi.testclient import TestClient

from backend.core.encryption import EncryptedString, EncryptionError
from backend.middleware.rate_limiter import SessionRateLimiter


class TestEncryption:
    """Test encryption module."""

    def test_encrypted_string_creation(self):
        """Test creating encrypted string."""
        EncryptedString.initialize()
        plaintext = "sk-my-secret-api-key"
        encrypted = EncryptedString(plaintext)
        assert encrypted.decrypt() == plaintext

    def test_encrypted_string_masking(self):
        """Test that encrypted strings mask properly."""
        EncryptedString.initialize()
        encrypted = EncryptedString("mysecret12345")
        str_repr = str(encrypted)
        assert "***" in str_repr
        assert "5" in str_repr  # Last 4 chars visible

    def test_encrypted_string_empty_fails(self):
        """Test that empty strings fail."""
        EncryptedString.initialize()
        with pytest.raises(EncryptionError):
            EncryptedString("")

    def test_encryption_key_generation(self):
        """Test key generation."""
        key = EncryptedString.generate_key()
        assert isinstance(key, str)
        assert len(key) > 0

    def test_encryption_initialization(self):
        """Test cipher initialization."""
        key = EncryptedString.generate_key()
        EncryptedString.initialize(key)
        encrypted = EncryptedString("test")
        assert encrypted.decrypt() == "test"


class TestRateLimiting:
    """Test rate limiting."""

    @pytest.mark.asyncio
    async def test_rate_limiter_allows_within_limit(self):
        """Test that limiter allows requests within limit."""
        limiter = SessionRateLimiter()
        session = "test_session"

        # 3 requests within 1 request per 10 seconds should work
        for _ in range(3):
            allowed, error = await limiter.is_allowed(session, "test", (10, 10))
            assert allowed is True
            assert error is None

    @pytest.mark.asyncio
    async def test_rate_limiter_blocks_over_limit(self):
        """Test that limiter blocks over-limit requests."""
        limiter = SessionRateLimiter()
        session = "test_session"

        # Add 2 requests (limit is 2)
        for _ in range(2):
            await limiter.is_allowed(session, "test", (2, 10))

        # Next request should fail
        allowed, error = await limiter.is_allowed(session, "test", (2, 10))
        assert allowed is False
        assert error is not None

    @pytest.mark.asyncio
    async def test_different_sessions_separate_limits(self):
        """Test that sessions have separate limits."""
        limiter = SessionRateLimiter()

        # Session 1: 2 requests
        for _ in range(2):
            allowed, _ = await limiter.is_allowed("session1", "test", (2, 10))
            assert allowed is True

        # Session 2: should still work (different session)
        allowed, error = await limiter.is_allowed("session2", "test", (2, 10))
        assert allowed is True
        assert error is None


class TestSecurityHeaders:
    """Test security headers middleware."""

    def test_security_headers_present(self, client: TestClient):
        """Test that security headers are present."""
        response = client.get("/health")
        assert response.status_code == 200

        # Check headers
        assert "X-Content-Type-Options" in response.headers
        assert response.headers["X-Content-Type-Options"] == "nosniff"

        assert "X-Frame-Options" in response.headers
        assert response.headers["X-Frame-Options"] == "DENY"

        assert "Content-Security-Policy" in response.headers


class TestInputValidation:
    """Test input validation for critical endpoints."""

    def test_path_traversal_blocked(self, client: TestClient):
        """Test that path traversal is blocked."""
        response = client.post(
            "/files/read",
            json={"path": "../../../../../../etc/passwd"}
        )
        # Should block or return error
        assert response.status_code in [400, 403, 422]

    def test_dangerous_shell_command_blocked(self, client: TestClient):
        """Test dangerous shell commands are blocked."""
        dangerous_commands = [
            "rm -rf /",
            "sudo rm -rf",
            "del C:\\*",
            "format C:",
        ]

        for cmd in dangerous_commands:
            response = client.post(
                "/shell/execute",
                json={"command": cmd}
            )
            # Should block
            assert response.status_code in [400, 403, 422]

    def test_sql_injection_attempt_safe(self, client: TestClient):
        """Test SQL injection attempts are handled safely."""
        response = client.post(
            "/search",
            json={"query": "'; DROP TABLE users; --"}
        )
        # Should not cause errors, just not match
        assert response.status_code in [200, 400, 422]


class TestAPIEndpointSecurity:
    """Test API endpoints for security issues."""

    def test_health_check_no_sensitive_data(self, client: TestClient):
        """Test health check doesn't leak sensitive info."""
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        # Should not contain secrets
        for key in data:
            assert "secret" not in str(key).lower()
            assert "password" not in str(key).lower()
            assert "api_key" not in str(key).lower()

    def test_error_handling_safe(self, client: TestClient):
        """Test that error messages don't leak info."""
        response = client.post(
            "/chat/process",
            json={"invalid": "data"}
        )
        # Should return error without stack trace
        assert response.status_code in [400, 422]
        data = response.json()
        # Should not contain file paths or internal info
        assert "traceback" not in str(data).lower()
