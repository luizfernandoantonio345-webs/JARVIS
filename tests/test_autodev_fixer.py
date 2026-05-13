"""
TESTE 2 — AutoDev com erro forçado (auto_fixer)

Goal: "crie uma função Python que importa pandas e retorna df.head()"

Configuração: no ambiente de teste pandas NÃO precisa estar instalado —
              o Validator detecta o ImportError como erro crítico e o
              AutoFixer tenta corrigir.

Validações:
  ✓ Validator detecta erro de import (pandas não instalado / sintaxe problemática)
  ✓ auto_fixer tenta corrigir (errors_fixed ou escalation report)
  ✓ escalations.json é gerado se falhar 3x
  ✓ Status final: "escalated" (não "failed") quando há erros persistentes

Run: pytest tests/test_autodev_fixer.py -v
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import JOBS_DIR, start_job, wait_for_terminal

os.environ["JARVIS_TEST_MODE"] = "1"
os.environ["JARVIS_DISABLE_VOICE"] = "1"

FIXER_GOAL = (
    "crie uma função Python chamada get_head que importa pandas como pd "
    "e retorna pd.DataFrame({'a': [1,2,3]}).head()"
)


class TestAutoDevFixer:

    def test_job_starts(self, client: TestClient):
        resp = start_job(client, FIXER_GOAL)
        assert "job_id" in resp
        self.__class__._job_id = resp["job_id"]

    def test_job_reaches_terminal(self, client: TestClient):
        job_id = getattr(self.__class__, "_job_id", None)
        if not job_id:
            pytest.skip("No job_id")
        final = wait_for_terminal(client, job_id, timeout=240)
        # Acceptable outcomes: "done" (pandas installed) or "escalated" (not installed)
        assert final["status"] in ("done", "escalated", "failed"), (
            f"Unexpected status: {final['status']}"
        )
        self.__class__._final = final

    def test_fixer_was_invoked(self, client: TestClient):
        """errors_fixed > 0 OR escalation_count > 0 OR escalations.json exists."""
        job_id = getattr(self.__class__, "_job_id", None)
        if not job_id:
            pytest.skip("No job_id")

        final = getattr(self.__class__, "_final", {})
        workspace = JOBS_DIR / job_id

        escalations_file = workspace / "escalations.json"
        fixer_was_invoked = (
            final.get("errors_fixed", 0) > 0
            or final.get("escalation_count", 0) > 0
            or escalations_file.exists()
        )
        assert fixer_was_invoked, (
            "AutoFixer appears not to have been invoked "
            f"(errors_found={final.get('errors_found',0)}, "
            f"errors_fixed={final.get('errors_fixed',0)}, "
            f"escalation_count={final.get('escalation_count',0)})"
        )

    def test_escalation_report_structure(self, client: TestClient):
        """If escalations.json exists, validate its structure."""
        job_id = getattr(self.__class__, "_job_id", None)
        if not job_id:
            pytest.skip("No job_id")

        workspace = JOBS_DIR / job_id
        esc_file = workspace / "escalations.json"
        if not esc_file.exists():
            pytest.skip("No escalations.json — fixer succeeded, test not applicable")

        reports = json.loads(esc_file.read_text(encoding="utf-8"))
        assert isinstance(reports, list)
        assert len(reports) >= 1

        report = reports[0]
        for key in ("job_id", "file_path", "original_error", "attempts", "escalated_at"):
            assert key in report, f"Missing key '{key}' in escalation report"

        # Each attempt record should have strategy progression
        attempts = report["attempts"]
        assert len(attempts) >= 1
        strategies = [a["strategy"] for a in attempts]
        # At least error+original strategy should appear
        assert "error+original" in strategies

    def test_not_plain_failed(self, client: TestClient):
        """Status should be 'escalated' or 'done', not plain 'failed'."""
        final = getattr(self.__class__, "_final", {})
        status = final.get("status", "")
        assert status != "failed", (
            "Job ended with 'failed' — unhandled exception rather than escalation. "
            f"Error: {final.get('error', 'unknown')}"
        )
