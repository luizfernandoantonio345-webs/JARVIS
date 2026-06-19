"""
Configuração global de testes do JARVIS.
Fixtures, marcadores e helpers compartilhados.
"""
from __future__ import annotations

import os
import sys
import hmac
import hashlib
import time
import tempfile
import sqlite3
from pathlib import Path

# Backend no sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Variáveis de ambiente para testes ────────────────────────────────────────
# JARVIS_SECRET_KEY vazio = Guardian desativado (modo aberto, para testes gerais)
os.environ["JARVIS_MODEL"] = "smollm2:135m"
os.environ["JARVIS_VOICE_ENABLED"] = "false"
os.environ["JARVIS_HEADSET_MODE"] = "false"
os.environ["JARVIS_WAKE_WORD_ENABLED"] = "false"
os.environ["JARVIS_LOG_LEVEL"] = "WARNING"
os.environ["JARVIS_SECRET_KEY"] = ""  # Guardian desativado nos testes gerais
os.environ["JARVIS_API_KEY"] = ""     # Auth legado desativado
os.environ["JARVIS_SAFE_MODE"] = "false"
os.environ["JARVIS_OLLAMA_URL"] = "http://127.0.0.1:11434"

import pytest

# ── Constantes ────────────────────────────────────────────────────────────────
TEST_SECRET = "deadbeef" * 8   # 64 chars hex — chave de teste
TEST_DEVICE = "test_device"


# ── Fixtures de banco de dados temporário ────────────────────────────────────
@pytest.fixture
def tmp_db(tmp_path):
    """Banco SQLite temporário para testes de auth."""
    return str(tmp_path / "test_security.db")


@pytest.fixture
def auth_manager(tmp_path):
    """AuthManager com DB temporário e chave de teste."""
    from security.auth_manager import AuthManager
    old_db = None
    import security.auth_manager as _mod
    old_db_path = _mod._DB_PATH
    _mod._DB_PATH = tmp_path / "test_security.db"
    _mod._DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    mgr = AuthManager(TEST_SECRET)
    yield mgr
    _mod._DB_PATH = old_db_path


@pytest.fixture
def threat_detector():
    """ThreatDetector isolado (sem singleton)."""
    from security.threat_detector import ThreatDetector
    return ThreatDetector(max_auth_failures=3, max_rps=10)


@pytest.fixture
def guardian(tmp_path):
    """Guardian com DB temporário."""
    import security.auth_manager as _mod
    old = _mod._DB_PATH
    _mod._DB_PATH = tmp_path / "guardian_security.db"
    _mod._DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    import security.guardian as _gmod
    old_g = _gmod._guardian
    g = _gmod.JarvisGuardian(TEST_SECRET)
    yield g
    _gmod._guardian = old_g
    _mod._DB_PATH = old


@pytest.fixture(scope="module")
def client():
    """FastAPI TestClient com Guardian desativado."""
    from main import app
    from fastapi.testclient import TestClient
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="module")
def client_with_auth():
    """FastAPI TestClient com Guardian ativo e token de teste."""
    os.environ["JARVIS_SECRET_KEY"] = TEST_SECRET
    from main import app
    from fastapi.testclient import TestClient
    # Gera token para device de teste
    payload = f"{TEST_DEVICE}:{int(time.time() // 86400)}"
    token = hmac.new(TEST_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    c = TestClient(app, raise_server_exceptions=False, headers={"Authorization": f"Bearer {token}"})
    yield c
    os.environ["JARVIS_SECRET_KEY"] = ""


# ── Marcadores ────────────────────────────────────────────────────────────────
def pytest_configure(config):
    config.addinivalue_line("markers", "slow: teste lento (LLM/rede)")
    config.addinivalue_line("markers", "integration: requer serviços externos")
    config.addinivalue_line("markers", "security: testes do sistema de segurança")


def pytest_collection_modifyitems(items):
    for item in items:
        if "slow" in item.nodeid or "llm" in item.nodeid.lower():
            item.add_marker(pytest.mark.slow)
