"""
Shared pytest fixtures and helpers for JARVIS integration tests.

IMPORTANT: backend/ must be on sys.path so bare imports like
  patch("ai.client.get_ai_client") work correctly.
"""
from __future__ import annotations

import ast
import os
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

# ── sys.path: adiciona backend/ ANTES de qualquer import ─────────────────────
_BACKEND_DIR = str(Path(__file__).parent.parent / "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

os.environ["JARVIS_TEST_MODE"] = "1"
os.environ["JARVIS_DISABLE_VOICE"] = "1"

# ── Base URL ───────────────────────────────────────────────────────────────────
BASE_URL = os.getenv("JARVIS_TEST_URL", "http://localhost:8000")
JOBS_DIR = Path(os.getenv("JARVIS_JOBS_DIR", Path(__file__).parent.parent / "jobs"))
TIMEOUT  = 180
_TEST_CLIENT: TestClient | None = None
_TEST_CLIENT_STARTED = False


def _get_test_client() -> TestClient:
    global _TEST_CLIENT, _TEST_CLIENT_STARTED
    if _TEST_CLIENT is None:
        from backend.main import app
        _TEST_CLIENT = TestClient(app)
    if not _TEST_CLIENT_STARTED:
        _TEST_CLIENT.__enter__()
        _TEST_CLIENT_STARTED = True
    return _TEST_CLIENT


# ── Helpers ────────────────────────────────────────────────────────────────────
def wait_for_terminal(
    client_or_job_id: TestClient | str,
    job_id: str | None = None,
    timeout: int = TIMEOUT,
) -> dict[str, Any]:
    if isinstance(client_or_job_id, TestClient):
        client = client_or_job_id
        assert job_id is not None
    else:
        client = _get_test_client()
        job_id = client_or_job_id

    terminal = {"done", "escalated", "failed"}
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/autodev/status/{job_id}")
        r.raise_for_status()
        data = r.json()
        if data.get("status") in terminal:
            return data
        time.sleep(3)
    raise TimeoutError(f"Job {job_id} did not complete within {timeout}s")


def is_valid_python(code: str) -> bool:
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


def start_job(
    client_or_goal: TestClient | str,
    goal: str | None = None,
    constraints: dict | None = None,
) -> dict[str, Any]:
    if isinstance(client_or_goal, TestClient):
        client = client_or_goal
        assert goal is not None
    else:
        client = _get_test_client()
        goal = client_or_goal

    r = client.post(
        "/autodev/start",
        json={"goal": goal, "constraints": constraints or {}},
    )
    r.raise_for_status()
    return r.json()


# ── Fixtures ───────────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def client():
    """Provide an in-process API client for all integration tests."""
    test_client = _get_test_client()
    r = test_client.get("/health")
    # Health pode retornar 200 mesmo sem Ollama (status=degraded é ok em teste)
    assert r.status_code == 200
    yield test_client


@pytest.fixture(scope="session")
def api(client: TestClient):
    return client
