"""
Testes para session_store (SQLite) e memory_service.
Usa arquivo de banco temporário para não sujar o banco real.
"""
import sys
import os
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


# ── Session Store (SQLite) ─────────────────────────────────────────────────────

@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    """Patch o DB path para usar arquivo temporário."""
    db_file = str(tmp_path / "test_jarvis.db")
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", db_file)
    # Resetar singletons do session_store
    import importlib
    import services.session_store as ss
    ss._sessions.clear()
    yield db_file
    ss._sessions.clear()


def test_session_starts_empty(temp_db):
    from services.session_store import get_history
    history = get_history("test_session_abc")
    assert history == []


def test_append_message_persists(temp_db):
    from services.session_store import append_message, get_history, clear_session
    clear_session("s1")
    append_message("s1", "user", "Olá JARVIS")
    history = get_history("s1")
    assert len(history) >= 1
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "Olá JARVIS"


def test_append_multiple_messages(temp_db):
    from services.session_store import append_message, get_history, clear_session
    clear_session("s2")
    append_message("s2", "user", "pergunta 1")
    append_message("s2", "assistant", "resposta 1")
    append_message("s2", "user", "pergunta 2")
    history = get_history("s2")
    assert len(history) == 3


def test_clear_session_empties_history(temp_db):
    from services.session_store import append_message, get_history, clear_session
    append_message("s3", "user", "test")
    clear_session("s3")
    history = get_history("s3")
    assert history == []


def test_sessions_are_isolated(temp_db):
    from services.session_store import append_message, get_history, clear_session
    clear_session("sa")
    clear_session("sb")
    append_message("sa", "user", "mensagem A")
    history_a = get_history("sa")
    history_b = get_history("sb")
    assert len(history_a) >= 1
    assert len(history_b) == 0


def test_system_prompt_is_string():
    from services.session_store import SYSTEM_PROMPT
    assert isinstance(SYSTEM_PROMPT, str)
    assert len(SYSTEM_PROMPT) > 50


# ── Config ─────────────────────────────────────────────────────────────────────

def test_config_loads():
    from config import get_config
    cfg = get_config()
    assert cfg is not None


def test_config_has_model():
    from config import get_config
    cfg = get_config()
    assert hasattr(cfg, "local_model") or hasattr(cfg, "model")


def test_config_has_ollama_url():
    from config import get_config
    cfg = get_config()
    assert hasattr(cfg, "ollama_url")
    assert "11434" in cfg.ollama_url or "localhost" in cfg.ollama_url or "127.0" in cfg.ollama_url


# ── Autonomy Policy Engine ──────────────────────────────────────────────────────

def test_policy_engine_loads():
    from autonomy.policy_engine import PolicyEngine
    engine = PolicyEngine()
    assert engine is not None


def test_policy_idle_allows_briefing():
    from autonomy.policy_engine import Event, PolicyDecision, PolicyEngine
    engine = PolicyEngine()
    result = engine.evaluate(Event("idle_detected", {"idle_seconds": 301, "safe_mode": True}))
    assert result == PolicyDecision.ALLOW


def test_policy_delete_is_denied():
    from autonomy.policy_engine import Event, PolicyDecision, PolicyEngine
    engine = PolicyEngine()
    result = engine.evaluate(Event("delete_files", {}))
    assert result == PolicyDecision.DENY


def test_policy_auto_commit_requires_confirmation():
    from autonomy.policy_engine import Event, PolicyDecision, PolicyEngine
    engine = PolicyEngine()
    result = engine.evaluate(Event("auto_commit", {}))
    assert result == PolicyDecision.REQUIRE_CONFIRMATION


# ── Jarvis Persona ─────────────────────────────────────────────────────────────

def test_persona_has_main_prompt():
    from core.jarvis_persona import MAIN_SYSTEM_PROMPT
    assert isinstance(MAIN_SYSTEM_PROMPT, str)
    assert "JARVIS" in MAIN_SYSTEM_PROMPT


def test_build_agent_prompt_returns_string():
    from core.jarvis_persona import build_agent_prompt
    result = build_agent_prompt("dev", "You are a dev agent.")
    assert isinstance(result, str)
    assert len(result) > 20
