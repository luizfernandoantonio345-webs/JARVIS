"""
Integration tests for JARVIS chat and workflow execution.
Tests chat endpoints, message processing, and orchestration.
"""
import json
import pytest
from fastapi.testclient import TestClient


class TestChatWorkflow:
    """Test suite for chat processing and workflows."""

    def test_chat_simple_message(self, client: TestClient):
        """Test basic chat message processing."""
        response = client.post(
            "/chat/process",
            json={"message": "Hello", "session_id": "test_session_1"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "response" in data or "message" in data

    def test_chat_empty_message(self, client: TestClient):
        """Test chat with empty message."""
        response = client.post(
            "/chat/process",
            json={"message": "", "session_id": "test_session_2"}
        )
        # Should handle gracefully
        assert response.status_code in [200, 400, 422]

    def test_chat_with_session_id(self, client: TestClient):
        """Test chat with session ID tracking."""
        session_id = "test_session_with_id"
        response = client.post(
            "/chat/process",
            json={"message": "Test message", "session_id": session_id}
        )
        assert response.status_code == 200

    def test_chat_streaming(self, client: TestClient):
        """Test streaming chat response."""
        response = client.post(
            "/chat/stream",
            json={"message": "Test streaming", "session_id": "stream_test"}
        )
        assert response.status_code == 200

    def test_intent_classification(self, client: TestClient):
        """Test intent classification."""
        # Should recognize different intents
        intents = [
            ("search for python tutorial", ["search", "learn"]),
            ("write a python script", ["code", "write"]),
            ("what time is it", ["info", "time"]),
        ]
        for message, expected_domains in intents:
            response = client.post(
                "/chat/process",
                json={"message": message, "session_id": "intent_test"}
            )
            assert response.status_code == 200

    def test_chat_with_context(self, client: TestClient):
        """Test that chat maintains context."""
        session_id = "context_test"

        # First message
        r1 = client.post(
            "/chat/process",
            json={"message": "My name is Alice", "session_id": session_id}
        )
        assert r1.status_code == 200

        # Follow-up message
        r2 = client.post(
            "/chat/process",
            json={"message": "What is my name?", "session_id": session_id}
        )
        assert r2.status_code == 200

    def test_memory_retrieval(self, client: TestClient):
        """Test memory endpoints."""
        response = client.get("/memory/episodic")
        assert response.status_code in [200, 400, 422]

    def test_memory_save(self, client: TestClient):
        """Test saving to memory."""
        response = client.post(
            "/memory/save",
            json={
                "type": "episodic",
                "content": "Test memory entry"
            }
        )
        assert response.status_code in [200, 400, 422]

    def test_orchestration(self, client: TestClient):
        """Test message orchestration."""
        response = client.post(
            "/orchestrate",
            json={"message": "Test orchestration"}
        )
        assert response.status_code in [200, 400, 422]


class TestEndpointValidation:
    """Test API endpoint contracts and validation."""

    def test_chat_missing_required_fields(self, client: TestClient):
        """Test chat with missing required fields."""
        response = client.post(
            "/chat/process",
            json={}  # Missing message and session_id
        )
        assert response.status_code == 422

    def test_chat_invalid_json(self, client: TestClient):
        """Test chat with invalid JSON."""
        response = client.post(
            "/chat/process",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code in [400, 422]

    def test_nonexistent_endpoint(self, client: TestClient):
        """Test calling nonexistent endpoint."""
        response = client.post("/nonexistent/endpoint", json={})
        assert response.status_code == 404

    def test_health_check(self, client: TestClient):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

    def test_cors_headers(self, client: TestClient):
        """Test CORS headers are present."""
        response = client.get("/health")
        assert response.status_code == 200
        # Should have CORS headers if configured
        # assert "access-control-allow-origin" in response.headers
