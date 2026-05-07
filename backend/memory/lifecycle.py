from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from config import get_config


class MemoryLifecycle:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or get_config().memory_db_path

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path), check_same_thread=False)

    async def archive_stale(self) -> int:
        cutoff = time.time() - 90 * 86400
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE semantic_memory SET archived=1 WHERE archived=0 AND score < 0.3 AND last_accessed < ?",
                (cutoff,),
            )
            conn.commit()
            return cur.rowcount

    async def enforce_limit(self, max_active: int = 10000) -> int:
        with self._conn() as conn:
            count = conn.execute("SELECT COUNT(*) FROM semantic_memory WHERE archived=0").fetchone()[0]
            if count <= max_active:
                return 0
            rows = conn.execute(
                "SELECT id FROM semantic_memory WHERE archived=0 ORDER BY score ASC, last_accessed ASC LIMIT ?",
                (min(1000, count - max_active),),
            ).fetchall()
            ids = [r[0] for r in rows]
            conn.executemany("UPDATE semantic_memory SET archived=1 WHERE id=?", [(i,) for i in ids])
            conn.commit()
            return len(ids)

    async def consolidate(self) -> dict:
        archived = await self.archive_stale()
        limited = await self.enforce_limit()
        return {
            "status": "ok",
            "archived_stale": archived,
            "archived_by_limit": limited,
            "report": "Consolidacao executada. Memorias de dominio sao mantidas indefinidamente.",
        }

