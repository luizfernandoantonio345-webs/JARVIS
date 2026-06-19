from __future__ import annotations

import os
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

from config import get_config
from core.jarvis_persona import MAIN_SYSTEM_PROMPT

SYSTEM_PROMPT = MAIN_SYSTEM_PROMPT

_sessions: Dict[str, List[Dict[str, str]]] = defaultdict(list)
_SESSION_HISTORY_CAP = int(os.getenv("SESSION_HISTORY_CAP", "40"))
_DB_PATH = Path(get_config().memory_db_path)


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS session_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_session_messages_session_id_id ON session_messages(session_id, id)"
    )
    return conn


def _trim_persisted_history(conn: sqlite3.Connection, session_id: str) -> None:
    overflow = conn.execute(
        "SELECT id FROM session_messages WHERE session_id = ? ORDER BY id DESC LIMIT -1 OFFSET ?",
        (session_id, _SESSION_HISTORY_CAP),
    ).fetchall()
    if overflow:
        conn.executemany("DELETE FROM session_messages WHERE id = ?", [(row["id"],) for row in overflow])


def _load_session(session_id: str) -> List[Dict[str, str]]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT role, content FROM session_messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in rows]
    finally:
        conn.close()


def get_history(session_id: str) -> List[Dict[str, str]]:
    if not _sessions[session_id]:
        _sessions[session_id] = _load_session(session_id)
    return _sessions[session_id]


def append_message(session_id: str, role: str, content: str) -> None:
    history = get_history(session_id)
    history.append({"role": role, "content": content})

    while len(history) > _SESSION_HISTORY_CAP:
        history.pop(0)
        if history:
            history.pop(0)

    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO session_messages (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content),
        )
        _trim_persisted_history(conn, session_id)
        conn.commit()
    finally:
        conn.close()


def clear_session(session_id: str) -> None:
    _sessions[session_id] = []
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM session_messages WHERE session_id = ?", (session_id,))
        conn.commit()
    finally:
        conn.close()


def delete_session(session_id: str) -> bool:
    """Remove all messages for a session from both in-memory cache and SQLite. Returns True on success."""
    try:
        _sessions.pop(session_id, None)
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM session_messages WHERE session_id = ?", (session_id,))
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception:
        return False


def message_count(session_id: str) -> int:
    """Return the total number of messages persisted for a session."""
    try:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM session_messages WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            return row[0] if row else 0
        finally:
            conn.close()
    except Exception:
        return 0


SYSTEM_PROMPT = "You are JARVIS, a personal AI assistant. Be helpful, concise, and professional."


class SessionStore:
    """Object-oriented wrapper around the module-level session functions."""

    def get_history(self, session_id: str) -> List[Dict[str, str]]:
        return get_history(session_id)

    def get(self, session_id: str) -> List[Dict[str, str]]:
        return get_history(session_id)

    def add_message(self, session_id: str, role: str, content: str) -> None:
        append_message(session_id, role, content)

    def save(self, session_id: str, role: str, content: str) -> None:
        append_message(session_id, role, content)

    def append(self, session_id: str, role: str, content: str) -> None:
        append_message(session_id, role, content)

    def clear(self, session_id: str) -> None:
        clear_session(session_id)

    def delete(self, session_id: str) -> bool:
        return delete_session(session_id)

    def count(self, session_id: str) -> int:
        return message_count(session_id)


_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    global _store
    if _store is None:
        _store = SessionStore()
    return _store
