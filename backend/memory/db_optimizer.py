"""
SQLite Database Optimizer
- WAL mode: eliminates locks in concurrent access
- Auto-cleanup: removes old memories
- Performance tuning: cache, memory, mmap
"""

import sqlite3
import pathlib
import logging
import asyncio
import time

log = logging.getLogger(__name__)

def optimize_database(db_path: str):
    """Enable WAL mode and performance tuning"""
    try:
        with sqlite3.connect(db_path) as c:
            # WAL mode eliminates locks in concurrent access
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
            c.execute("PRAGMA cache_size=10000")
            c.execute("PRAGMA temp_store=MEMORY")
            c.execute("PRAGMA mmap_size=268435456")
            c.execute("PRAGMA busy_timeout=5000")
            log.info(f"[DB] WAL mode enabled: {db_path}")
    except Exception as e:
        log.warning(f"[DB] Optimization failed: {e}")

def cleanup_old_memories(db_path: str, keep_days: int = 30):
    """Remove old memories older than keep_days"""
    try:
        with sqlite3.connect(db_path) as c:
            # Remove old memories
            deleted = c.execute(
                "DELETE FROM memories WHERE "
                "datetime(created_at) < datetime('now', ? || ' days')",
                (f"-{keep_days}",)
            ).rowcount
            
            if deleted > 0:
                c.execute("VACUUM")
                log.info(f"[DB] Cleanup: {deleted} old records removed, database vacuumed")
            else:
                log.debug(f"[DB] No old records to cleanup")
    except Exception as e:
        log.debug(f"[DB] Cleanup skipped: {e}")

async def db_maintenance_loop(db_path: str, interval_seconds: int = 3600):
    """Background task: cleanup every interval_seconds (default 1 hour)"""
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            cleanup_old_memories(db_path)
        except Exception as e:
            log.warning(f"[DB] Maintenance task error: {e}")
            await asyncio.sleep(10)
