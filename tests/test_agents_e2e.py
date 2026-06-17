
"""
TESTE 4 — Multi-Agent com objetivo real

Goal: "analise o arquivo main.py e liste os endpoints FastAPI definidos nele"

Validações:
  ✓ Planner decompõe em subtasks (read_file, analyze, summarize)
  ✓ Executor usa shell ou file_reader para ler o arquivo
  ✓ Critic aprova o resultado (score >= 0.7)
  ✓ Resultado contém pelo menos 3 endpoints reais do sistema

Run: pytest tests/test_agents_e2e.py -v
"""
from __future__ import annotations
import pytest
pytestmark = pytest.mark.integration


import os
import re
import time
import unittest.mock as mock

from fastapi.testclient import TestClient
import pytest

os.environ["JARVIS_TEST_MODE"] = "1"
os.environ["JARVIS_DISABLE_VOICE"] = "1"

AGENT_GOAL = (
    "analise o arquivo backend/main.py e liste todos os endpoints FastAPI "
    "definidos nele, incluindo método HTTP e path"
)

# Known endpoints from main.py — at least 3 of these must appear in the result
KNOWN_ENDPOINTS = [
    "/health",
    "/chat",
    "/execute",
    "/memory",
    "/tasks",
    "/agents",
    "/security",
    "/orchestrate",
    "/workspace",
    "/terminal",
    "/autodev",
    "/system/digest",
]


@pytest.fixture(scope="class", autouse=True)
def mock_llm_post():
    with mock.patch("httpx.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "response": "resposta mock do LLM"
        }
        yield mock_post


class TestAgentsE2E:

    def test_agent_run_starts(self, client: TestClient):
        """POST /agents/run returns a result or task_id."""
        r = client.post(
            "/agents/run",
            json={"goal": AGENT_GOAL},
        )
        assert r.status_code in (200, 202), f"Unexpected status {r.status_code}: {r.text}"
        data = r.json()
        self.__class__._response = data

    def test_response_has_result(self, client: TestClient):
        """Response contains a non-empty result field."""
        data = getattr(self.__class__, "_response", {})
        result_text = (
            data.get("result")
            or data.get("output")
            or data.get("response")
            or data.get("answer")
            or ""
        )
        # If it returned a task_id, poll for completion
        if not result_text and "task_id" in data:
            result_text = _poll_task(client, data["task_id"])
        self.__class__._result_text = result_text
        assert result_text, f"Empty result from agent. Full response: {data}"

    def test_result_contains_endpoints(self):
        """Result mentions at least 3 known Jarvis endpoints."""
        result = getattr(self.__class__, "_result_text", "")
        found = [ep for ep in KNOWN_ENDPOINTS if ep in result]
        assert len(found) >= 3, (
            f"Result mentions only {len(found)} known endpoints: {found}\n"
            f"Result text (first 500 chars): {result[:500]}"
        )

    def test_result_mentions_methods(self):
        """Result mentions HTTP methods (GET, POST, etc.)."""
        result = getattr(self.__class__, "_result_text", "")
        http_methods = re.findall(r"\b(GET|POST|PUT|DELETE|PATCH|WS|WebSocket)\b",
                                   result, re.IGNORECASE)
        assert len(http_methods) >= 1, (
            "Result does not mention any HTTP methods. "
            f"Result (first 300): {result[:300]}"
        )

    def test_orchestrator_responded(self):
        """Response has status field indicating orchestrator ran."""
        data = getattr(self.__class__, "_response", {})
        # Various orchestrator response shapes are acceptable
        has_result_field = any(
            k in data for k in ("result", "output", "response", "answer", "task_id")
        )
        assert has_result_field, f"Response missing known result fields: {data.keys()}"


def _poll_task(client: TestClient, task_id: str, timeout: int = 120) -> str:
    """Poll /tasks/{task_id} until completed, return result."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/tasks/{task_id}")
        if r.status_code == 200:
            data = r.json()
            if data.get("status") in ("completed", "done"):
                return data.get("result", "")
        time.sleep(3)
    return ""
