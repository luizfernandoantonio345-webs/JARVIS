from __future__ import annotations

import sqlite3
from pathlib import Path

from config import get_config


def collect_interactions(limit: int = 1000) -> list[dict]:
    db_path: Path = get_config().memory_db_path
    if not db_path.exists():
        return []
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT message, response, action, created_at FROM memory ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {"user_input": msg, "response": resp, "intent": action, "timestamp": ts}
        for msg, resp, action, ts in rows
    ]

