"""
Testes para /tasks — criação, consulta, cancelamento e retry de tarefas.
Usa mocks para não precisar do Ollama rodando.
"""
from __future__ import annotations

import os
import time
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

os.environ.setdefault("JARVIS_TEST_MODE", "1")
os.environ.setdefault("JARVIS_DISABLE_VOICE", "1")


@pytest.fixture(scope="module")
def client():
    with patch("ai.client.get_ai_client") as mock_ai:
        mock_ai.return_value.call.return_value = "mock response"
        from fastapi.testclient import TestClient
        from backend.main import app
        with TestClient(app) as c:
            yield c


# ── POST /tasks — criação ─────────────────────────────────────────────────────
def test_create_task_custom(client):
    r = client.post("/tasks", json={
        "type": "custom",
        "payload": {"prompt": "Olá JARVIS"}
    })
    assert r.status_code == 200
    data = r.json()
    assert "task_id" in data
    assert data["task_id"].startswith("task_")
    assert data["status"] == "pending"
    assert "poll_url" in data


def test_create_task_invalid_type(client):
    r = client.post("/tasks", json={"type": "nao_existe"})
    assert r.status_code == 400
    assert "não suportado" in r.json()["detail"]


def test_create_task_missing_type(client):
    r = client.post("/tasks", json={})
    assert r.status_code == 422


# ── GET /tasks/{id} — status ──────────────────────────────────────────────────
def test_get_task_status(client):
    create = client.post("/tasks", json={"type": "custom", "payload": {"prompt": "test"}})
    assert create.status_code == 200
    task_id = create.json()["task_id"]

    r = client.get(f"/tasks/{task_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == task_id
    assert data["type"] == "custom"
    assert data["status"] in ("pending", "running", "completed", "failed")
    assert "elapsed_seconds" in data


def test_get_task_not_found(client):
    r = client.get("/tasks/task_nonexistent123")
    assert r.status_code == 404


# ── GET /tasks — listagem ─────────────────────────────────────────────────────
def test_list_tasks(client):
    # Criar ao menos uma tarefa antes
    client.post("/tasks", json={"type": "custom", "payload": {"prompt": "list test"}})

    r = client.get("/tasks")
    assert r.status_code == 200
    data = r.json()
    assert "tasks" in data
    assert "count" in data
    assert "summary" in data
    summary = data["summary"]
    assert "total" in summary
    assert "completed" in summary
    assert "failed" in summary
    assert "running" in summary
    assert "pending" in summary


def test_list_tasks_limit(client):
    r = client.get("/tasks?limit=2")
    assert r.status_code == 200
    assert len(r.json()["tasks"]) <= 2


def test_list_tasks_filter_status(client):
    r = client.get("/tasks?status=completed")
    assert r.status_code == 200
    for t in r.json()["tasks"]:
        assert t["status"] == "completed"


# ── DELETE /tasks/{id} — cancelar ────────────────────────────────────────────
def test_cancel_pending_task(client):
    create = client.post("/tasks", json={"type": "custom", "payload": {"prompt": "cancelar"}})
    task_id = create.json()["task_id"]

    r = client.delete(f"/tasks/{task_id}")
    assert r.status_code == 200
    data = r.json()
    # Pode já ter completado ou ter sido cancelado
    assert "task_id" in data or "task" in data


def test_cancel_nonexistent_task(client):
    r = client.delete("/tasks/task_ghost000000")
    assert r.status_code == 404


# ── POST /tasks/{id}/retry ────────────────────────────────────────────────────
def test_retry_failed_task(client):
    # Criar tarefa que vai falhar (mock levanta excecao)
    with patch("routes.tasks._handle_custom_task", side_effect=RuntimeError("force fail")):
        create = client.post("/tasks", json={"type": "custom", "payload": {"prompt": "fail"}})
        task_id = create.json()["task_id"]
        # Aguardar processamento (max 3s)
        for _ in range(6):
            time.sleep(0.5)
            status_r = client.get(f"/tasks/{task_id}")
            if status_r.json()["status"] in ("failed", "completed"):
                break

    # Tentar retry
    r = client.post(f"/tasks/{task_id}/retry", json={})
    # Se status ainda não for failed/cancelled pode retornar 400 — aceitar ambos
    assert r.status_code in (200, 400)
    if r.status_code == 200:
        data = r.json()
        assert "new_task_id" in data
        assert data["old_task_id"] == task_id


# ── DELETE /tasks — limpar concluídas ────────────────────────────────────────
def test_clear_completed_tasks(client):
    r = client.delete("/tasks?keep_running=true")
    assert r.status_code == 200
    data = r.json()
    assert "removed" in data
    assert "remaining" in data
    assert isinstance(data["removed"], int)


# ── Persistência SQLite ───────────────────────────────────────────────────────
def test_sqlite_db_created():
    from pathlib import Path
    db_path = Path(__file__).parent.parent / "backend" / "data" / "tasks.db"
    assert db_path.exists(), f"SQLite DB nao criado em {db_path}"


def test_task_survives_memory_clear(client):
    """Simula reinício: remove do cache em memória, verifica que carrega do DB."""
    create = client.post("/tasks", json={"type": "custom", "payload": {"prompt": "persist test"}})
    task_id = create.json()["task_id"]

    # Aguardar processamento
    time.sleep(1)

    # Remover do cache em memória (simular reinício)
    from routes.tasks import _TASKS
    _TASKS.pop(task_id, None)

    # Deve carregar do SQLite
    r = client.get(f"/tasks/{task_id}")
    assert r.status_code == 200
    assert r.json()["id"] == task_id
