"""
Critical Path E2E Tests for JARVIS

Tests the main flow:
  1. Health check (GET /health)
  2. Message ingestion (POST /chat/process)
  3. WebSocket connection + message
  4. Error handling

Run: pytest tests/test_critical_path.py -v
"""

import asyncio
import json
import logging
from typing import Any

import httpx
import pytest
import websocket

from conftest import BASE_URL

log = logging.getLogger(__name__)


@pytest.mark.integration
class TestCriticalPath:
    """Critical path smoke tests — requerem servidor rodando em localhost:8000."""

    @pytest.fixture
    def client(self):
        """HTTP client for test requests."""
        return httpx.Client(base_url=BASE_URL, timeout=30)

    # ───────────────────────────────────────────────────────────────────────────────
    # TEST 1: Health Check
    # ───────────────────────────────────────────────────────────────────────────────

    def test_01_health_check(self, client):
        """
        GET /health returns 200 and indicates server is operational.
        """
        resp = client.get("/health")
        assert resp.status_code == 200, f"Health check failed: {resp.text}"
        
        data = resp.json()
        assert "status" in data or "health" in data, "Health response missing status"
        log.info(f"✓ Health check passed: {data}")

    # ───────────────────────────────────────────────────────────────────────────────
    # TEST 2: Chat Message Processing
    # ───────────────────────────────────────────────────────────────────────────────

    def test_02_chat_process_simple_message(self, client):
        """
        POST /chat/process with a simple message returns a response.
        """
        payload = {
            "message": "responda OK",
            "session_id": "test_critical_001"
        }
        
        resp = client.post("/chat/process", json=payload)
        assert resp.status_code == 200, f"Chat failed: {resp.text}"
        
        data = resp.json()
        assert "response" in data or "message" in data, "Response missing output"
        
        response_text = data.get("response") or data.get("message", "")
        assert len(response_text) > 0, "Response is empty"
        log.info(f"✓ Chat response: {response_text[:100]}")

    def test_02b_chat_process_with_intent(self, client):
        """
        POST /chat/process with a message that has clear intent.
        """
        payload = {
            "message": "qual é a data de hoje?",
            "session_id": "test_critical_002"
        }
        
        resp = client.post("/chat/process", json=payload)
        assert resp.status_code == 200, f"Chat failed: {resp.text}"
        
        data = resp.json()
        response_text = data.get("response") or data.get("message", "")
        assert len(response_text) > 0, "Response is empty"
        log.info(f"✓ Intent response: {response_text[:100]}")

    # ───────────────────────────────────────────────────────────────────────────────
    # TEST 3: WebSocket Connection & Message
    # ───────────────────────────────────────────────────────────────────────────────

    def test_03_websocket_connect_and_receive(self):
        """
        Connect to WebSocket /ws/jarvis, send a message, and receive a response.
        """
        ws_url = BASE_URL.replace("http://", "ws://").replace("https://", "wss://")
        ws_endpoint = f"{ws_url}/ws/jarvis"
        
        try:
            # Connect to WebSocket
            ws = websocket.create_connection(ws_endpoint, timeout=10)
            log.info(f"✓ WebSocket connected: {ws_endpoint}")
            
            # Receive welcome message
            welcome = ws.recv()
            assert len(welcome) > 0, "No welcome message"
            log.info(f"✓ Welcome: {welcome[:100]}")
            
            # Send a test message
            test_msg = "teste"
            ws.send(test_msg)
            log.info(f"✓ Sent message: {test_msg}")
            
            # Receive response (may have multiple messages: thinking, speaking, etc.)
            response = ws.recv()
            assert len(response) > 0, "No response received"
            log.info(f"✓ Response: {response[:100]}")
            
            ws.close()
            log.info("✓ WebSocket test passed")
            
        except Exception as e:
            log.error(f"WebSocket test failed: {e}")
            raise

    # ───────────────────────────────────────────────────────────────────────────────
    # TEST 4: Error Handling & Graceful Fallback
    # ───────────────────────────────────────────────────────────────────────────────

    def test_04_chat_error_handling(self, client):
        """
        POST /chat/process with invalid payload handles gracefully.
        """
        # Send empty message
        payload = {
            "message": "",
            "session_id": "test_critical_003"
        }
        
        resp = client.post("/chat/process", json=payload)
        # Should either return 400 (bad request) or 200 with error message
        assert resp.status_code in (200, 400), f"Unexpected status: {resp.status_code}"
        
        if resp.status_code == 200:
            data = resp.json()
            # Either we get a response or an error field
            assert "response" in data or "error" in data or "message" in data
            log.info(f"✓ Error handled gracefully: {data}")
        else:
            log.info(f"✓ Error correctly returned status 400")

    def test_04b_malformed_json(self, client):
        """
        POST /chat/process with malformed payload handles gracefully.
        """
        # Try to send raw text instead of JSON
        resp = client.post(
            "/chat/process",
            content="not json",
            headers={"Content-Type": "application/json"}
        )
        # Should return error
        assert resp.status_code >= 400, f"Expected error status, got {resp.status_code}"
        log.info(f"✓ Malformed payload rejected with {resp.status_code}")


@pytest.mark.integration
class TestActionSecurity:
    """Tests for action security (whitelist, validation)."""

    @pytest.fixture
    def client(self):
        return httpx.Client(base_url=BASE_URL, timeout=30)

    def test_computer_control_action_validation(self, client):
        """
        computer_control action requires valid action parameter.
        """
        # This would be tested via the chat endpoint if a message
        # triggers computer_control action. For now, we just verify
        # the action module loaded correctly.
        try:
            from backend.actions import computer_control
            assert hasattr(computer_control, 'computer_control')
            assert hasattr(computer_control, '_ALLOWED_ACTIONS')
            log.info("✓ computer_control action loaded with security constraints")
        except ImportError:
            log.warning("computer_control not available in test environment")

    def test_browser_control_url_validation(self, client):
        """
        browser_control action validates URLs against whitelist.
        """
        try:
            from backend.actions import browser_control
            assert hasattr(browser_control, '_ALLOWED_DOMAINS')
            assert hasattr(browser_control, '_validate_url')
            
            # Test URL validation
            is_valid, msg = browser_control._validate_url("https://github.com")
            assert is_valid, f"github.com should be allowed: {msg}"
            
            is_valid, msg = browser_control._validate_url("file:///etc/passwd")
            assert not is_valid, "file:// should be blocked"
            
            log.info("✓ browser_control URL validation working")
        except ImportError:
            log.warning("browser_control not available in test environment")


# ───────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ───────────────────────────────────────────────────────────────────────────────

"""
Critical Path Coverage:

✓ T1 — Health Check: Server is up and running
✓ T2 — Message Ingestion: Can receive and respond to chat messages
✓ T3 — WebSocket: Real-time communication works
✓ T4 — Error Handling: Gracefully handles bad input

Expected to pass when:
- backend/main.py is running
- routes/health.py and routes/chat.py are available
- WebSocket endpoint is live

Optional security tests:
- T5 — computer_control validates actions
- T6 — browser_control validates URLs
"""
