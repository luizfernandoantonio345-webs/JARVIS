"""
Tasks Route — JARVIS v8.0
Fila de tarefas assíncronas em background com status tracking.
POST /tasks → cria tarefa
GET  /tasks → lista todas
GET  /tasks/{id} → status + resultado
DELETE /tasks/{id} → cancela
POST /tasks/{id}/retry → re-executa tarefa falhada
"""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()
log = logging.getLogger("jarvis.tasks")

_MAX_TASKS = 200
_TASK_TTL  = 86400  # 24h de persistência
_DB_PATH = Path(__file__).parent.parent / "data" / "tasks.db"
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# ── In-memory cache (rápido para tarefas ativas) + SQLite (persistência) ──────
_TASKS: Dict[str, dict] = {}


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id           TEXT PRIMARY KEY,
            type         TEXT NOT NULL,
            payload      TEXT NOT NULL DEFAULT '{}',
            status       TEXT NOT NULL DEFAULT 'pending',
            created_at   REAL NOT NULL,
            started_at   REAL,
            completed_at REAL,
            result       TEXT,
            error        TEXT,
            progress     INTEGER DEFAULT 0,
            progress_msg TEXT DEFAULT ''
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at DESC)")
    conn.commit()
    return conn


def _task_to_dict(row) -> dict:
    d = dict(row)
    for f in ("payload", "result"):
        if d.get(f) and isinstance(d[f], str):
            try:
                d[f] = json.loads(d[f])
            except Exception:
                pass
    return d


def _persist_task(task: dict) -> None:
    """Salva/atualiza tarefa no SQLite."""
    try:
        with _get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO tasks
                (id, type, payload, status, created_at, started_at,
                 completed_at, result, error, progress, progress_msg)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (
                task["id"],
                task["type"],
                json.dumps(task.get("payload") or {}),
                task["status"],
                task["created_at"],
                task.get("started_at"),
                task.get("completed_at"),
                json.dumps(task.get("result")) if task.get("result") is not None else None,
                task.get("error"),
                task.get("progress", 0),
                task.get("progress_msg", ""),
            ))
    except Exception as e:
        log.warning("[TASKS] Erro ao persistir tarefa: %s", e)


def _load_tasks_from_db() -> None:
    """Carrega tarefas recentes do SQLite no cache de memória."""
    try:
        with _get_conn() as conn:
            cutoff = time.time() - _TASK_TTL
            rows = conn.execute(
                "SELECT * FROM tasks WHERE created_at > ? ORDER BY created_at DESC LIMIT ?",
                (cutoff, _MAX_TASKS)
            ).fetchall()
        for row in rows:
            task = _task_to_dict(row)
            # Tarefas que estavam "running" quando o processo reiniciou → failed
            if task["status"] in ("running", "pending"):
                task["status"] = "failed"
                task["error"] = "Interrompido por reinício do servidor"
                task["completed_at"] = time.time()
                _persist_task(task)
            _TASKS[task["id"]] = task
        log.info("[TASKS] %d tarefas carregadas do SQLite", len(_TASKS))
    except Exception as e:
        log.warning("[TASKS] Erro ao carregar do SQLite: %s", e)


# Carregar tarefas do DB ao importar o módulo
_load_tasks_from_db()


def _clean_old_tasks() -> None:
    now = time.time()
    expired = [tid for tid, t in _TASKS.items() if now - t["created_at"] > _TASK_TTL]
    for tid in expired:
        _TASKS.pop(tid, None)
    if len(_TASKS) > _MAX_TASKS:
        sorted_by_age = sorted(_TASKS.keys(), key=lambda k: _TASKS[k]["created_at"])
        for tid in sorted_by_age[:len(_TASKS) - _MAX_TASKS]:
            _TASKS.pop(tid, None)
    # Limpar DB também
    try:
        with _get_conn() as conn:
            conn.execute("DELETE FROM tasks WHERE created_at < ?", (now - _TASK_TTL,))
    except Exception:
        pass


def _new_task(task_type: str, payload: dict) -> dict:
    _clean_old_tasks()
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    task = {
        "id": task_id,
        "type": task_type,
        "payload": payload,
        "status": "pending",
        "created_at": time.time(),
        "started_at": None,
        "completed_at": None,
        "result": None,
        "error": None,
        "progress": 0,
        "progress_msg": "",
    }
    _TASKS[task_id] = task
    _persist_task(task)
    return task


def _task_result(task_id: str) -> dict:
    t = _TASKS.get(task_id)
    if not t:
        # Tentar carregar do DB (tarefas antigas)
        try:
            with _get_conn() as conn:
                row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row:
                t = _task_to_dict(row)
                _TASKS[task_id] = t
        except Exception:
            pass
    if not t:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    elapsed = None
    if t.get("started_at") and t.get("completed_at"):
        elapsed = round(t["completed_at"] - t["started_at"], 2)
    elif t.get("started_at"):
        elapsed = round(time.time() - t["started_at"], 2)
    return {**t, "elapsed_seconds": elapsed}


# ── Background runner ─────────────────────────────────────────────────────────
async def _run_task_bg(task_id: str, coro_fn: Callable, **kwargs) -> None:
    task = _TASKS.get(task_id)
    if not task:
        return
    task["status"] = "running"
    task["started_at"] = time.time()
    task["progress"] = 5
    task["progress_msg"] = "Iniciando..."
    _persist_task(task)
    try:
        result = await coro_fn(task_id=task_id, **kwargs)
        task["status"] = "completed"
        task["result"] = result
        task["progress"] = 100
        task["progress_msg"] = "Concluído"
    except asyncio.CancelledError:
        task["status"] = "cancelled"
        task["progress_msg"] = "Cancelado"
    except Exception as e:
        task["status"] = "failed"
        task["error"] = str(e)
        task["progress_msg"] = f"Erro: {e}"
    finally:
        task["completed_at"] = time.time()
        _persist_task(task)


# ── Pydantic models ───────────────────────────────────────────────────────────
class TaskCreateReq(BaseModel):
    type: str          # "analyze" | "generate_code" | "investigate" | "architect" | "custom"
    payload: dict = {}
    priority: str = "normal"  # low | normal | high


class TaskRetryReq(BaseModel):
    override_payload: dict = {}


# ── Task type handlers ────────────────────────────────────────────────────────
async def _handle_analyze_task(task_id: str, payload: dict) -> Any:
    t = _TASKS[task_id]
    t["progress"] = 20; t["progress_msg"] = "Lendo arquivo..."
    from routes.analyze import analyze_code, AnalyzeRequest
    req = AnalyzeRequest(**payload)
    t["progress"] = 60; t["progress_msg"] = "Analisando com LLM..."
    result = await analyze_code(req)
    t["progress"] = 95; t["progress_msg"] = "Finalizando..."
    return result


async def _handle_investigate_task(task_id: str, payload: dict) -> Any:
    t = _TASKS[task_id]
    t["progress"] = 20; t["progress_msg"] = "Iniciando investigação..."
    from routes.investigate import investigate, InvestigateRequest
    req = InvestigateRequest(**payload)
    t["progress"] = 60; t["progress_msg"] = "Consultando fontes OSINT..."
    result = await investigate(req)
    t["progress"] = 95
    return result


async def _handle_architect_task(task_id: str, payload: dict) -> Any:
    t = _TASKS[task_id]
    t["progress"] = 20; t["progress_msg"] = "Elaborando arquitetura..."
    from routes.architect import generate_architecture, ArchitectRequest
    req = ArchitectRequest(**payload)
    t["progress"] = 60; t["progress_msg"] = "Gerando plano com LLM..."
    result = await generate_architecture(req)
    t["progress"] = 95
    return result


async def _handle_generate_code_task(task_id: str, payload: dict) -> Any:
    t = _TASKS[task_id]
    t["progress"] = 30; t["progress_msg"] = "Gerando código..."
    from routes.generate import generate_code, GenerateCodeReq
    req = GenerateCodeReq(**payload)
    t["progress"] = 70; t["progress_msg"] = "LLM processando..."
    result = await generate_code(req)
    t["progress"] = 95
    return result


async def _handle_custom_task(task_id: str, payload: dict) -> Any:
    """Execute a custom LLM query as a background task."""
    t = _TASKS[task_id]
    t["progress"] = 20; t["progress_msg"] = "Processando consulta..."
    from ai.client import get_ai_client
    msgs = payload.get("messages", [])
    if not msgs:
        system = payload.get("system", "Você é JARVIS, assistente IA sênior.")
        user = payload.get("prompt", "Olá")
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    t["progress"] = 50; t["progress_msg"] = "LLM respondendo..."
    result = get_ai_client().call(msgs)
    t["progress"] = 95
    return {"response": result, "type": "custom"}


_HANDLERS: Dict[str, Callable] = {
    "analyze": _handle_analyze_task,
    "investigate": _handle_investigate_task,
    "architect": _handle_architect_task,
    "generate_code": _handle_generate_code_task,
    "custom": _handle_custom_task,
}


# ── Endpoints ─────────────────────────────────────────────────────────────────
@router.post("")
async def create_task(req: TaskCreateReq):
    """Cria e inicia uma tarefa em background."""
    handler = _HANDLERS.get(req.type)
    if not handler:
        supported = list(_HANDLERS.keys())
        raise HTTPException(status_code=400, detail=f"Tipo '{req.type}' não suportado. Use: {supported}")

    task = _new_task(req.type, req.payload)
    task_id = task["id"]

    # Launch in background
    asyncio.create_task(_run_task_bg(task_id, handler, **{"payload": req.payload}))

    return {
        "task_id": task_id,
        "status": "pending",
        "message": f"Tarefa '{req.type}' criada. Consulte GET /tasks/{task_id} para acompanhar.",
        "poll_url": f"/tasks/{task_id}",
    }


@router.get("")
async def list_tasks(status: str = "", limit: int = 20):
    """Lista as últimas tarefas. Filtra por status opcionalmente."""
    _clean_old_tasks()
    tasks = list(_TASKS.values())
    tasks.sort(key=lambda t: t["created_at"], reverse=True)
    if status:
        tasks = [t for t in tasks if t["status"] == status]
    tasks = tasks[:limit]
    # Compute elapsed for each
    now = time.time()
    results = []
    for t in tasks:
        elapsed = None
        if t["started_at"] and t["completed_at"]:
            elapsed = round(t["completed_at"] - t["started_at"], 2)
        elif t["started_at"]:
            elapsed = round(now - t["started_at"], 2)
        results.append({**t, "elapsed_seconds": elapsed})
    return {
        "count": len(results),
        "tasks": results,
        "summary": {
            "total": len(_TASKS),
            "pending": sum(1 for t in _TASKS.values() if t["status"] == "pending"),
            "running": sum(1 for t in _TASKS.values() if t["status"] == "running"),
            "completed": sum(1 for t in _TASKS.values() if t["status"] == "completed"),
            "failed": sum(1 for t in _TASKS.values() if t["status"] == "failed"),
        }
    }


@router.get("/{task_id}")
async def get_task(task_id: str):
    """Retorna status e resultado de uma tarefa."""
    return _task_result(task_id)


@router.delete("/{task_id}")
async def cancel_task(task_id: str):
    """Cancela uma tarefa pendente ou em execução."""
    task = _TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    if task["status"] in ("completed", "failed", "cancelled"):
        return {"message": f"Tarefa já em estado '{task['status']}', Senhor.", "task": task}
    task["status"] = "cancelled"
    task["completed_at"] = time.time()
    task["progress_msg"] = "Cancelado pelo utilizador"
    _persist_task(task)
    return {"message": "Tarefa cancelada, Senhor.", "task_id": task_id}


@router.post("/{task_id}/retry")
async def retry_task(task_id: str, req: TaskRetryReq):
    """Re-executa uma tarefa falhada com o mesmo ou novo payload."""
    old_task = _TASKS.get(task_id)
    if not old_task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    if old_task["status"] not in ("failed", "cancelled"):
        raise HTTPException(status_code=400, detail=f"Só pode re-executar tarefas falhadas/canceladas. Status atual: {old_task['status']}")

    task_type = old_task["type"]
    payload = {**old_task["payload"], **req.override_payload}
    handler = _HANDLERS.get(task_type)
    if not handler:
        raise HTTPException(status_code=400, detail=f"Handler para '{task_type}' não encontrado")

    new_task = _new_task(task_type, payload)
    new_task_id = new_task["id"]
    asyncio.create_task(_run_task_bg(new_task_id, handler, **{"payload": payload}))

    return {
        "message": f"Tarefa re-executada como '{new_task_id}', Senhor.",
        "old_task_id": task_id,
        "new_task_id": new_task_id,
        "poll_url": f"/tasks/{new_task_id}",
    }


@router.delete("")
async def clear_tasks(keep_running: bool = True):
    """Limpa todas as tarefas concluídas/falhadas/canceladas."""
    removed = 0
    to_remove = []
    for tid, t in _TASKS.items():
        if keep_running and t["status"] in ("pending", "running"):
            continue
        to_remove.append(tid)
    for tid in to_remove:
        _TASKS.pop(tid, None)
        removed += 1
    # Limpar do DB também
    try:
        if keep_running:
            with _get_conn() as conn:
                conn.execute("DELETE FROM tasks WHERE status NOT IN ('pending','running')")
        else:
            with _get_conn() as conn:
                conn.execute("DELETE FROM tasks")
    except Exception:
        pass
    return {"removed": removed, "remaining": len(_TASKS)}
