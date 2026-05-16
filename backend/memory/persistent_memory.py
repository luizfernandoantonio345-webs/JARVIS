from datetime import datetime
import sqlite3
import json
import pathlib
import logging

log = logging.getLogger(__name__)
DB_PATH = pathlib.Path("data/jarvis_memory.db")

class PersistentMemory:
    def __init__(self):
        DB_PATH.parent.mkdir(exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(DB_PATH) as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    summary TEXT,
                    importance INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT (datetime('now')),
                    tags TEXT DEFAULT '[]'
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS user_profile (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TEXT DEFAULT (datetime('now'))
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fact TEXT NOT NULL,
                    source_session TEXT,
                    confidence REAL DEFAULT 1.0,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)

    def save(self, session_id: str, role: str, content: str,
             importance: int = 1, tags: list = None):
        with sqlite3.connect(DB_PATH) as c:
            c.execute(
                "INSERT INTO memories (session_id, role, content, importance, tags) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, role, content, importance, json.dumps(tags or []))
            )

    def get_recent(self, session_id: str, limit: int = 20) -> list[dict]:
        with sqlite3.connect(DB_PATH) as c:
            rows = c.execute(
                "SELECT role, content, created_at FROM memories "
                "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit)
            ).fetchall()
        return [{"role": r[0], "content": r[1], "ts": r[2]}
                for r in reversed(rows)]

    def get_all_sessions(self) -> list[str]:
        with sqlite3.connect(DB_PATH) as c:
            rows = c.execute(
                "SELECT DISTINCT session_id FROM memories"
            ).fetchall()
        return [r[0] for r in rows]

    def save_fact(self, fact: str, session_id: str = "global"):
        with sqlite3.connect(DB_PATH) as c:
            c.execute(
                "INSERT INTO facts (fact, source_session) VALUES (?, ?)",
                (fact, session_id)
            )

    def get_facts(self, limit: int = 50) -> list[str]:
        with sqlite3.connect(DB_PATH) as c:
            rows = c.execute(
                "SELECT fact FROM facts ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [r[0] for r in rows]

    def update_profile(self, key: str, value: str):
        with sqlite3.connect(DB_PATH) as c:
            c.execute(
                "INSERT OR REPLACE INTO user_profile (key, value, updated_at) "
                "VALUES (?, ?, datetime('now'))", (key, value)
            )

    def get_profile(self) -> dict:
        with sqlite3.connect(DB_PATH) as c:
            rows = c.execute(
                "SELECT key, value FROM user_profile"
            ).fetchall()
        return {r[0]: r[1] for r in rows}

    def build_context(self, session_id: str) -> str:
        profile = self.get_profile()
        facts = self.get_facts(10)
        recent = self.get_recent(session_id, 6)

        parts = []
        if profile:
            prof_str = ", ".join(f"{k}={v}" for k,v in profile.items())
            parts.append(f"[Perfil do usuario] {prof_str}")
        if facts:
            parts.append("[Fatos conhecidos]\n" + "\n".join(f"- {f}" for f in facts))
        if recent:
            parts.append("[Conversa recente]")
            for m in recent[-4:]:
                parts.append(f"{m['role'].upper()}: {m['content'][:100]}")
        return "\n\n".join(parts)

_mem: PersistentMemory | None = None
def get_persistent_memory() -> PersistentMemory:
    global _mem
    if _mem is None:
        _mem = PersistentMemory()
    return _mem
