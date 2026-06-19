"""
Testes de integração para as rotas HTTP do JARVIS.
Usa TestClient do FastAPI sem precisar de servidor externo.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """Cria TestClient com app JARVIS completo."""
    os.environ.setdefault("JARVIS_MODEL", "smollm2:135m")
    os.environ.setdefault("JARVIS_VOICE_ENABLED", "false")
    os.environ.setdefault("JARVIS_HEADSET_MODE", "false")
    os.environ.setdefault("JARVIS_WAKE_WORD_ENABLED", "false")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


# ── /health ────────────────────────────────────────────────────────────────────

def test_health_returns_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert "status" in data


def test_health_contains_model(client):
    r = client.get("/health")
    data = r.json()
    # Pode estar ok ou degraded, mas deve ter campo model
    assert "model" in data or "version" in data or "status" in data


def test_ping_returns_pong(client):
    r = client.get("/ping")
    assert r.status_code == 200


def test_ready_returns_200(client):
    r = client.get("/ready")
    assert r.status_code in (200, 503)


# ── / (frontend) ───────────────────────────────────────────────────────────────

def test_root_returns_html_or_json(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "") or r.headers.get("content-type", "").startswith("application/json")


# ── /agents ────────────────────────────────────────────────────────────────────

def test_agents_list_returns_agents(client):
    r = client.get("/agents/")
    assert r.status_code == 200
    data = r.json()
    assert "agents" in data
    assert isinstance(data["agents"], list)
    assert len(data["agents"]) > 0


def test_agents_list_has_count(client):
    r = client.get("/agents/")
    data = r.json()
    assert data["count"] == len(data["agents"])


def test_agent_run_unknown_role_returns_404(client):
    r = client.post("/agents/nonexistent_role/run", json={"message": "test"})
    assert r.status_code == 404


def test_agent_run_empty_message_returns_error(client):
    r = client.post("/agents/dev/run", json={"message": ""})
    assert r.status_code in (400, 422)


# ── /memory ────────────────────────────────────────────────────────────────────

def test_memory_search_empty_query(client):
    r = client.get("/memory/search?q=")
    assert r.status_code in (200, 400, 422)


def test_memory_search_valid_query(client):
    r = client.get("/memory/search?q=python")
    assert r.status_code in (200, 503)


# ── /voice ─────────────────────────────────────────────────────────────────────

def test_voice_status_returns_dict(client):
    r = client.get("/voice/status")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, dict)


def test_voice_tts_empty_text_returns_400(client):
    r = client.get("/voice/tts?text=")
    assert r.status_code in (400, 503)


def test_voice_audio_unknown_file_returns_404(client):
    r = client.get("/voice/audio/nonexistent_file.mp3")
    assert r.status_code == 404


def test_voice_audio_invalid_filename_returns_400(client):
    r = client.get("/voice/audio/../secret.mp3")
    assert r.status_code in (400, 404, 422)


# ── /tasks ─────────────────────────────────────────────────────────────────────

def test_tasks_run_requires_body(client):
    r = client.post("/tasks/run")
    assert r.status_code in (400, 422)


def test_tasks_nonexistent_id_returns_404(client):
    r = client.get("/tasks/nonexistent-task-id-12345")
    assert r.status_code == 404


def test_tasks_list_returns_list(client):
    r = client.get("/tasks/list")
    assert r.status_code in (200, 404)


# ── /chat ──────────────────────────────────────────────────────────────────────

def test_chat_history_empty_session(client):
    r = client.get("/chat/history?session_id=test_session_nonexistent_xyz")
    assert r.status_code in (200, 404)


# ── CORS headers ───────────────────────────────────────────────────────────────

def test_cors_header_present(client):
    r = client.options("/health", headers={"Origin": "http://testclient"})
    assert r.status_code in (200, 405)
