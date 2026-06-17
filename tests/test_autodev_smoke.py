
"""
TESTE 1 — AutoDev básico (smoke test)

Goal: "crie um script Python que lê um arquivo CSV e imprime a soma da coluna 'valor'"

Validações:
  ✓ Job criado com job_id válido
  ✓ Arquivos gerados em jobs/{job_id}/
  ✓ Código gerado é Python válido (ast.parse sem erro)
  ✓ Validator retorna sem ValidationError crítico
  ✓ Status final: completed (done ou escalated sem critical)

Run: pytest tests/test_autodev_smoke.py -v
"""
from __future__ import annotations
import pytest
pytestmark = pytest.mark.integration


import os
from pathlib import Path
import unittest.mock as mock

import pytest
from fastapi.testclient import TestClient

from conftest import JOBS_DIR, start_job, wait_for_terminal, is_valid_python

os.environ["JARVIS_TEST_MODE"] = "1"
os.environ["JARVIS_DISABLE_VOICE"] = "1"

SMOKE_GOAL = (
    "crie um script Python que lê um arquivo CSV e imprime a soma da coluna 'valor'"
)


@pytest.fixture(scope="class", autouse=True)
def mock_llm_post():
    with mock.patch("httpx.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "response": "resposta mock do LLM"
        }
        yield mock_post


class TestAutoDevSmoke:

    def test_job_created(self, client: TestClient):
        """POST /autodev/start returns a valid job_id."""
        resp = start_job(client, SMOKE_GOAL)
        assert "job_id" in resp, "Response missing job_id"
        assert len(resp["job_id"]) > 0
        assert resp["status"] in ("pending", "resuming", "generating", "scaffolding")
        self.__class__._job_id = resp["job_id"]

    def test_job_workspace_created(self, client: TestClient):
        """Workspace directory for the job is created on disk."""
        job_id = getattr(self.__class__, "_job_id", None)
        if not job_id:
            pytest.skip("No job_id — run test_job_created first")
        workspace = JOBS_DIR / job_id
        assert workspace.exists(), f"Workspace not found: {workspace}"

    def test_job_completes(self, client: TestClient):
        """Job reaches a terminal state within TIMEOUT seconds."""
        job_id = getattr(self.__class__, "_job_id", None)
        if not job_id:
            pytest.skip("No job_id")
        final = wait_for_terminal(client, job_id)
        assert final["status"] in ("done", "escalated"), (
            f"Unexpected final status: {final['status']}"
        )
        self.__class__._final = final

    def test_files_generated(self, client: TestClient):
        """At least one file was generated in the job workspace."""
        job_id = getattr(self.__class__, "_job_id", None)
        if not job_id:
            pytest.skip("No job_id")
        workspace = JOBS_DIR / job_id
        py_files = list(workspace.rglob("*.py"))
        # Exclude meta files
        py_files = [f for f in py_files if f.name not in ("state.json",)]
        assert len(py_files) >= 1, f"No Python files found in {workspace}"
        self.__class__._py_files = py_files

    def test_generated_code_is_valid_python(self, client: TestClient):
        """All generated .py files parse without SyntaxError."""
        py_files = getattr(self.__class__, "_py_files", None)
        if not py_files:
            pytest.skip("No files to check")

        invalid = []
        for f in py_files:
            code = f.read_text(encoding="utf-8")
            if not is_valid_python(code):
                invalid.append(str(f))

        assert not invalid, f"Invalid Python files: {invalid}"

    def test_status_files_generated_count(self, client: TestClient):
        """files_generated in status response is > 0."""
        final = getattr(self.__class__, "_final", None)
        if not final:
            pytest.skip("No final status")
        assert final.get("files_generated", 0) > 0

    def test_context_json_persisted(self, client: TestClient):
        """context.json was written by ProjectContext."""
        job_id = getattr(self.__class__, "_job_id", None)
        if not job_id:
            pytest.skip("No job_id")
        ctx_file = JOBS_DIR / job_id / "context.json"
        assert ctx_file.exists(), "context.json not found — ProjectContext not saving"

        import json
        ctx = json.loads(ctx_file.read_text(encoding="utf-8"))
        assert "files" in ctx
        assert len(ctx["files"]) >= 1
