"""
Shared pytest fixtures and helpers for JARVIS integration tests.
"""
from __future__ import annotations

import ast
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

# ── Base URL ───────────────────────────────────────────────────────────────────
BASE_URL = os.getenv("JARVIS_TEST_URL", "http://localhost:8000")
JOBS_DIR = Path(os.getenv("JARVIS_JOBS_DIR", Path(__file__).parent.parent / "jobs"))
TIMEOUT  = 180          # seconds to wait for a job to complete


# ── Helpers ────────────────────────────────────────────────────────────────────

def wait_for_terminal(job_id: str, timeout: int = TIMEOUT) -> dict[str, Any]:
    """Poll /autodev/status/{job_id} until status is terminal, then return."""
    terminal = {"done", "escalated", "failed"}
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = httpx.get(f"{BASE_URL}/autodev/status/{job_id}", timeout=10)
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


def start_job(goal: str, constraints: dict | None = None) -> dict[str, Any]:
    r = httpx.post(
        f"{BASE_URL}/autodev/start",
        json={"goal": goal, "constraints": constraints or {}},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def api():
    """Verify the server is reachable before any test runs."""
    try:
        r = httpx.get(f"{BASE_URL}/health", timeout=5)
        r.raise_for_status()
    except Exception as exc:
        pytest.skip(f"Server not reachable at {BASE_URL}: {exc}")
    return BASE_URL
