"""
Testes para /generate — 15 sub-endpoints de geração de código/docs.
A API retorna {"voice_response": ..., "display_type": ..., "data": {...}}
Todos os campos úteis estão dentro de "data".
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
import pytest
from unittest.mock import patch

# Garantir que backend/ está no sys.path (conftest já faz isso, mas redundância não custa)
_BD = str(Path(__file__).parent.parent / "backend")
if _BD not in sys.path:
    sys.path.insert(0, _BD)

os.environ.setdefault("JARVIS_TEST_MODE", "1")
os.environ.setdefault("JARVIS_DISABLE_VOICE", "1")

_MOCK_LLM = "mock LLM output"


@pytest.fixture(scope="module")
def client():
    with patch("ai.client.get_ai_client") as mock_ai:
        mock_ai.return_value.call.return_value = _MOCK_LLM
        from fastapi.testclient import TestClient
        from backend.main import app
        with TestClient(app) as c:
            yield c, mock_ai


# ── /generate/code ───────────────────────────────────────────────────────────
def test_generate_code_ok(client):
    c, _ = client
    r = c.post("/generate/code", json={"description": "hello world", "language": "python"})
    assert r.status_code == 200
    body = r.json()
    assert "data" in body
    assert "code" in body["data"]
    assert body["data"]["language"] == "python"


def test_generate_code_missing_description(client):
    c, _ = client
    r = c.post("/generate/code", json={})
    assert r.status_code == 422


def test_generate_code_default_language(client):
    c, _ = client
    r = c.post("/generate/code", json={"description": "soma dois numeros"})
    assert r.status_code == 200
    assert r.json()["data"]["language"] == "python"


# ── /generate/tests ──────────────────────────────────────────────────────────
def test_generate_tests_ok(client):
    c, _ = client
    r = c.post("/generate/tests", json={"code": "def add(a,b): return a+b", "language": "python"})
    assert r.status_code == 200
    body = r.json()
    assert "data" in body
    # resultado fica em data["code"] com type="tests"
    assert "code" in body["data"] or body["data"].get("type") == "tests"


def test_generate_tests_missing_code(client):
    c, _ = client
    r = c.post("/generate/tests", json={})
    # sem code e sem file_path → retorna 200 com mensagem de erro (não 422)
    assert r.status_code == 200
    body = r.json()
    assert "voice_response" in body


# ── /generate/docs ───────────────────────────────────────────────────────────
def test_generate_docs_ok(client):
    c, _ = client
    r = c.post("/generate/docs", json={"code": "def foo(): pass"})
    assert r.status_code == 200
    body = r.json()
    assert "data" in body
    assert "code" in body["data"]


# ── /generate/explain ────────────────────────────────────────────────────────
def test_generate_explain_ok(client):
    c, _ = client
    r = c.post("/generate/explain", json={"code": "lambda x: x*2"})
    assert r.status_code == 200
    body = r.json()
    assert "data" in body
    # LLM mockado retorna string, não JSON → fallback: explanation em data["explanation"]
    assert "explanation" in body["data"] or "summary" in body["data"]


# ── /generate/fix ────────────────────────────────────────────────────────────
def test_generate_fix_ok(client):
    c, _ = client
    r = c.post("/generate/fix", json={
        "code": "prnt('hello')",
        "error": "NameError: name 'prnt' is not defined"
    })
    assert r.status_code == 200
    body = r.json()
    assert "data" in body
    d = body["data"]
    assert "fixed_code" in d or "code" in d


# ── /generate/review ─────────────────────────────────────────────────────────
def test_generate_review_ok(client):
    c, _ = client
    r = c.post("/generate/review", json={"code": "x = eval(input())"})
    assert r.status_code == 200
    body = r.json()
    assert "data" in body
    d = body["data"]
    # verdict, score ou overall_feedback indicam que é um review
    assert "verdict" in d or "overall_feedback" in d or "score" in d


# ── /generate/optimize ───────────────────────────────────────────────────────
def test_generate_optimize_ok(client):
    c, _ = client
    r = c.post("/generate/optimize", json={"code": "for i in range(len(lst)): print(lst[i])"})
    assert r.status_code == 200


# ── /generate/regex ──────────────────────────────────────────────────────────
def test_generate_regex_ok(client):
    c, _ = client
    r = c.post("/generate/regex", json={"description": "match email addresses"})
    assert r.status_code == 200
    body = r.json()
    assert "data" in body
    d = body["data"]
    assert "pattern" in d or "regex" in d


# ── /generate/docker ─────────────────────────────────────────────────────────
def test_generate_dockerfile_ok(client):
    c, _ = client
    r = c.post("/generate/docker", json={"description": "fastapi python app"})
    assert r.status_code == 200


# ── /generate/readme ─────────────────────────────────────────────────────────
def test_generate_readme_ok(client):
    c, _ = client
    r = c.post("/generate/readme", json={
        "project_name": "JARVIS",
        "description": "AI assistant"
    })
    assert r.status_code == 200


# ── /generate/convert ────────────────────────────────────────────────────────
def test_generate_convert_ok(client):
    c, _ = client
    r = c.post("/generate/convert", json={
        "code": "def add(a, b): return a+b",
        "from_language": "python",
        "to_language": "javascript"
    })
    assert r.status_code == 200


# ── /generate/summarize ──────────────────────────────────────────────────────
def test_generate_summarize_ok(client):
    c, _ = client
    r = c.post("/generate/summarize", json={"text": "This is a long document about AI systems."})
    assert r.status_code == 200


# ── /generate/api ────────────────────────────────────────────────────────────
def test_generate_api_spec_ok(client):
    c, _ = client
    r = c.post("/generate/api", json={"description": "user CRUD API"})
    assert r.status_code == 200


# ── /generate/diagram ────────────────────────────────────────────────────────
def test_generate_diagram_ok(client):
    c, _ = client
    r = c.post("/generate/diagram", json={"description": "user auth flow"})
    assert r.status_code == 200
    body = r.json()
    assert "data" in body
    assert "mermaid" in body["data"]
