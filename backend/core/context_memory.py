"""
Context Memory — FASE 1: JARVIS Intelligence Layer

Per-session conversational context persisted in memory.db (the same SQLite
file used by memory_service.py).  Two new tables are created on first use:

  context_memory  — intent extraction log per message
  active_project  — current project state (goal, domain, stack, files)

Public API
----------
save_intent(session_id, message, intent, response="")
    Persist an IntentModel and update active_project when applicable.

get_recent_intents(session_id, limit=5) -> list[dict]
    Return recent {message, intent, ts} dicts, newest first.

get_active_project(session_id) -> dict | None
    Return {goal, domain, stack, files, status} for the current project.

add_project_file(session_id, filepath)
    Append a file path to the active project's file list.

build_context_summary(session_id) -> str
    Concise context string (~400 chars) ready for LLM prompt injection.

All public functions catch every exception internally — they never crash
the chat pipeline.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime
from typing import Optional

from config import get_config

log = logging.getLogger(__name__)
_lock = threading.Lock()


# ── DB bootstrap ───────────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    """Open the shared memory.db with WAL mode and create tables if missing."""
    conn = sqlite3.connect(str(get_config().memory_db_path), check_same_thread=False)

    # Match the pragmas used by memory_service.py
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-8000")

    # Table: per-message intent log
    conn.execute("""
        CREATE TABLE IF NOT EXISTS context_memory (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT    NOT NULL,
            intent_json TEXT    NOT NULL,
            message     TEXT    NOT NULL,
            response    TEXT    NOT NULL DEFAULT '',
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ctxmem_session "
        "ON context_memory(session_id)"
    )

    # Table: active project state (one row per session)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS active_project (
            session_id  TEXT PRIMARY KEY,
            goal        TEXT NOT NULL DEFAULT '',
            domain      TEXT NOT NULL DEFAULT 'chat',
            stack       TEXT NOT NULL DEFAULT '[]',
            files       TEXT NOT NULL DEFAULT '[]',
            status      TEXT NOT NULL DEFAULT 'active',
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    return conn


# ── Public API ─────────────────────────────────────────────────────────────────

def save_intent(
    session_id: str,
    message: str,
    intent,
    response: str = "",
) -> None:
    """
    Persist *intent* in context_memory and update active_project.

    active_project is only updated when:
      - domain != "chat"  (skip pure conversation)
      - ambiguity_score < 0.75  (intent clear enough to track)
    """
    with _lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO context_memory (session_id, intent_json, message, response) "
                "VALUES (?, ?, ?, ?)",
                (
                    session_id,
                    intent.model_dump_json(),
                    message[:2000],
                    response[:4000],
                ),
            )
            if intent.domain != "chat" and intent.ambiguity_score < 0.75:
                _upsert_project(conn, session_id, intent)
            conn.commit()
        except Exception as exc:
            log.warning("context_memory.save_intent failed: %s", exc)
        finally:
            conn.close()


def _upsert_project(conn: sqlite3.Connection, session_id: str, intent) -> None:
    """Insert or update the active_project row, merging stack constraints."""
    new_stack: list[str] = [c for c in (intent.constraints or []) if c]
    now = datetime.utcnow().isoformat()

    existing = conn.execute(
        "SELECT stack FROM active_project WHERE session_id = ?",
        (session_id,),
    ).fetchone()

    if existing:
        old_stack: list[str] = json.loads(existing[0] or "[]")
        merged = list(dict.fromkeys(old_stack + new_stack))  # deduplicated, order-preserving
        conn.execute(
            "UPDATE active_project "
            "SET goal=?, domain=?, stack=?, status='active', updated_at=? "
            "WHERE session_id=?",
            (intent.goal, intent.domain, json.dumps(merged), now, session_id),
        )
    else:
        conn.execute(
            "INSERT INTO active_project (session_id, goal, domain, stack, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, intent.goal, intent.domain, json.dumps(new_stack), now),
        )


def add_project_file(session_id: str, filepath: str) -> None:
    """
    Record a file generated by AutoDev into the active project's file list.
    Creates an active_project row if none exists yet.
    """
    with _lock:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT files FROM active_project WHERE session_id = ?",
                (session_id,),
            ).fetchone()

            if row:
                files: list[str] = json.loads(row[0] or "[]")
                if filepath not in files:
                    files.append(filepath)
                conn.execute(
                    "UPDATE active_project SET files=?, updated_at=? "
                    "WHERE session_id=?",
                    (json.dumps(files), datetime.utcnow().isoformat(), session_id),
                )
                conn.commit()
        except Exception as exc:
            log.warning("context_memory.add_project_file failed: %s", exc)
        finally:
            conn.close()


def get_recent_intents(session_id: str, limit: int = 5) -> list[dict]:
    """Return the *limit* most recent intent records for the session, newest first."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT message, intent_json, created_at FROM context_memory "
            "WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()

        result: list[dict] = []
        for msg, intent_json, created_at in rows:
            try:
                result.append({
                    "message": msg,
                    "intent": json.loads(intent_json),
                    "ts": created_at,
                })
            except Exception:
                pass  # corrupted row — skip silently
        return result

    except Exception as exc:
        log.warning("context_memory.get_recent_intents failed: %s", exc)
        return []
    finally:
        conn.close()


def get_active_project(session_id: str) -> Optional[dict]:
    """Return the active project dict or None if no project exists for the session."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT goal, domain, stack, files, status "
            "FROM active_project WHERE session_id = ?",
            (session_id,),
        ).fetchone()

        if not row:
            return None

        return {
            "goal":   row[0],
            "domain": row[1],
            "stack":  json.loads(row[2] or "[]"),
            "files":  json.loads(row[3] or "[]"),
            "status": row[4],
        }
    except Exception as exc:
        log.warning("context_memory.get_active_project failed: %s", exc)
        return None
    finally:
        conn.close()


def build_context_summary(session_id: str) -> str:
    """
    Build a concise (~400 chars) context string for LLM prompt injection.

    Includes:
      - Active project goal, domain, stack
      - List of files already created (first 8)
      - Goal chain from recent non-chat intents (last 3)

    Returns empty string if no context exists yet.
    """
    parts: list[str] = []

    project = get_active_project(session_id)
    if project and project["status"] == "active" and project["goal"]:
        parts.append(
            f"Projeto ativo: {project['goal']} (domínio: {project['domain']})"
        )
        if project["stack"]:
            parts.append(f"Stack: {', '.join(project['stack'][:5])}")
        if project["files"]:
            parts.append(f"Arquivos criados: {', '.join(project['files'][:8])}")

    recent = get_recent_intents(session_id, limit=4)
    goals = [
        r["intent"].get("goal", "")
        for r in recent
        if r["intent"].get("domain") not in (None, "chat") and r["intent"].get("goal")
    ]
    if goals:
        parts.append(f"Histórico: {' → '.join(goals[:3])}")

    return "\n".join(parts)
