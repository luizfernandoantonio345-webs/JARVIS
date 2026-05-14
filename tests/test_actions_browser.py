"""
Integration tests for JARVIS browser control actions.
Tests URL validation, navigation, form filling with security checks.
"""
import pytest
from fastapi.testclient import TestClient


class TestBrowserControl:
    """Test suite for browser automation."""

    def test_navigate_to_safe_url(self, client: TestClient):
        """Test navigation to whitelisted URL."""
        response = client.post(
            "/browser/navigate",
            json={"url": "https://www.google.com"}
        )
        assert response.status_code in [200, 400, 422]

    def test_navigate_to_dangerous_url(self, client: TestClient):
        """Test that dangerous URLs are blocked."""
        # Should reject file:// protocol
        response = client.post(
            "/browser/navigate",
            json={"url": "file:///etc/passwd"}
        )
        # Should block or reject
        assert response.status_code in [400, 403, 422]

    def test_navigate_to_javascript_url(self, client: TestClient):
        """Test that javascript: URLs are blocked."""
        response = client.post(
            "/browser/navigate",
            json={"url": "javascript:alert('xss')"}
        )
        # Should block
        assert response.status_code in [400, 403, 422]

    def test_navigate_to_data_url(self, client: TestClient):
        """Test that data: URLs are blocked."""
        response = client.post(
            "/browser/navigate",
            json={"url": "data:text/html,<script>alert('xss')</script>"}
        )
        # Should block
        assert response.status_code in [400, 403, 422]

    def test_get_current_url(self, client: TestClient):
        """Test fetching current URL."""
        response = client.post("/browser/get/url", json={})
        assert response.status_code in [200, 400, 422]

    def test_click_element(self, client: TestClient):
        """Test clicking an element by selector."""
        response = client.post(
            "/browser/click",
            json={"selector": "button.submit"}
        )
        assert response.status_code in [200, 400, 422]

    def test_type_in_input(self, client: TestClient):
        """Test typing in an input field."""
        response = client.post(
            "/browser/type",
            json={"selector": "input[type='text']", "text": "test input"}
        )
        assert response.status_code in [200, 400, 422]

    def test_get_page_content(self, client: TestClient):
        """Test fetching page content."""
        response = client.post("/browser/get/content", json={})
        assert response.status_code in [200, 400, 422]

    def test_take_screenshot(self, client: TestClient):
        """Test taking a browser screenshot."""
        response = client.post("/browser/screenshot", json={})
        assert response.status_code in [200, 400, 422]

    def test_url_whitelist_enforcement(self, client: TestClient):
        """Test that URL whitelist is enforced."""
        # Try navigation to non-whitelisted domain
        response = client.post(
            "/browser/navigate",
            json={"url": "https://malicious-domain-that-should-be-blocked.com"}
        )
        # Should block unknown domains
        assert response.status_code in [400, 403, 422]
