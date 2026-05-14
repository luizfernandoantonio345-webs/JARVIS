"""
Storage abstraction layer for JARVIS.
Supports SQLite, PostgreSQL, and Redis backends.
"""
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, List, Optional

log = logging.getLogger(__name__)

# Data model
class StorageEntry:
    """Generic storage entry."""

    def __init__(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        metadata: Optional[dict] = None
    ):
        self.key = key
        self.value = value
        self.ttl = ttl
        self.metadata = metadata or {}
        self.created_at = datetime.now()
        self.updated_at = datetime.now()

    def is_expired(self) -> bool:
        """Check if entry has expired."""
        if self.ttl is None:
            return False
        expiry = self.created_at + timedelta(seconds=self.ttl)
        return datetime.now() > expiry

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "value": self.value,
            "ttl": self.ttl,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class BaseStorage(ABC):
    """Abstract storage backend."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize storage."""
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set key-value pair."""
        pass

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Get value by key."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete key. Returns True if existed."""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clear all data."""
        pass

    @abstractmethod
    async def list_keys(self, pattern: str = "*") -> List[str]:
        """List keys matching pattern."""
        pass


class SQLiteStorage(BaseStorage):
    """SQLite storage backend."""

    def __init__(self, db_path: str = "backend/memory.db"):
        self.db_path = db_path
        self.conn = None

    async def initialize(self) -> None:
        """Initialize SQLite database."""
        import sqlite3
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS storage (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                ttl INTEGER,
                metadata TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        self.conn.commit()
        log.info(f"SQLiteStorage initialized: {self.db_path}")

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set key-value pair."""
        import sqlite3
        value_str = json.dumps(value) if not isinstance(value, str) else value
        metadata_str = json.dumps({})
        now = datetime.now().isoformat()

        try:
            self.conn.execute("""
                INSERT OR REPLACE INTO storage
                (key, value, ttl, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (key, value_str, ttl, metadata_str, now, now))
            self.conn.commit()
        except sqlite3.Error as e:
            log.error(f"SQLite error: {e}")

    async def get(self, key: str) -> Optional[Any]:
        """Get value by key."""
        try:
            cursor = self.conn.execute(
                "SELECT value, ttl, created_at FROM storage WHERE key = ?",
                (key,)
            )
            row = cursor.fetchone()

            if not row:
                return None

            value_str, ttl, created_at = row

            # Check expiry
            if ttl:
                created = datetime.fromisoformat(created_at)
                if datetime.now() > created + timedelta(seconds=ttl):
                    await self.delete(key)
                    return None

            return json.loads(value_str)
        except Exception as e:
            log.error(f"Error getting key {key}: {e}")
            return None

    async def delete(self, key: str) -> bool:
        """Delete key."""
        cursor = self.conn.execute("DELETE FROM storage WHERE key = ?", (key,))
        self.conn.commit()
        return cursor.rowcount > 0

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        cursor = self.conn.execute(
            "SELECT 1 FROM storage WHERE key = ? LIMIT 1",
            (key,)
        )
        return cursor.fetchone() is not None

    async def clear(self) -> None:
        """Clear all data."""
        self.conn.execute("DELETE FROM storage")
        self.conn.commit()

    async def list_keys(self, pattern: str = "*") -> List[str]:
        """List keys matching pattern."""
        if pattern == "*":
            cursor = self.conn.execute("SELECT key FROM storage")
        else:
            # Simple pattern matching (LIKE)
            pattern = pattern.replace("*", "%")
            cursor = self.conn.execute(
                "SELECT key FROM storage WHERE key LIKE ?",
                (pattern,)
            )
        return [row[0] for row in cursor.fetchall()]


class RedisStorage(BaseStorage):
    """Redis storage backend."""

    def __init__(self, url: str = "redis://localhost:6379"):
        self.url = url
        self.redis = None

    async def initialize(self) -> None:
        """Initialize Redis connection."""
        try:
            import aioredis
            self.redis = await aioredis.create_redis_pool(self.url)
            log.info(f"RedisStorage initialized: {self.url}")
        except ImportError:
            log.error("aioredis not installed. Install with: pip install aioredis")

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set key-value pair."""
        if not self.redis:
            return

        value_str = json.dumps(value) if not isinstance(value, str) else value

        if ttl:
            await self.redis.setex(key, ttl, value_str)
        else:
            await self.redis.set(key, value_str)

    async def get(self, key: str) -> Optional[Any]:
        """Get value by key."""
        if not self.redis:
            return None

        value_str = await self.redis.get(key)
        if value_str is None:
            return None

        try:
            return json.loads(value_str)
        except json.JSONDecodeError:
            return value_str

    async def delete(self, key: str) -> bool:
        """Delete key."""
        if not self.redis:
            return False

        deleted = await self.redis.delete(key)
        return deleted > 0

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        if not self.redis:
            return False

        exists = await self.redis.exists(key)
        return exists > 0

    async def clear(self) -> None:
        """Clear all data."""
        if self.redis:
            await self.redis.flushdb()

    async def list_keys(self, pattern: str = "*") -> List[str]:
        """List keys matching pattern."""
        if not self.redis:
            return []

        keys = await self.redis.keys(pattern)
        return [k.decode() if isinstance(k, bytes) else k for k in keys]


class StorageFactory:
    """Factory for creating storage backends."""

    _backends = {
        "sqlite": SQLiteStorage,
        "redis": RedisStorage,
    }

    @classmethod
    def create(cls, backend: str = "sqlite", **kwargs) -> BaseStorage:
        """
        Create storage backend.

        Args:
            backend: Backend type (sqlite, redis)
            **kwargs: Backend-specific arguments

        Returns:
            Storage instance
        """
        if backend not in cls._backends:
            raise ValueError(f"Unknown backend: {backend}")

        storage_class = cls._backends[backend]
        return storage_class(**kwargs)

    @classmethod
    def register_backend(cls, name: str, storage_class: type) -> None:
        """Register custom storage backend."""
        cls._backends[name] = storage_class


# Global instance (initialized at startup)
storage: Optional[BaseStorage] = None


async def initialize_storage(backend: str = "sqlite", **kwargs) -> None:
    """Initialize global storage."""
    global storage
    storage = StorageFactory.create(backend, **kwargs)
    await storage.initialize()


async def get_storage() -> BaseStorage:
    """Get global storage instance."""
    global storage
    if storage is None:
        await initialize_storage()
    return storage
