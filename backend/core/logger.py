"""
Structured JSON logging for JARVIS.
Replaces ad-hoc print/logging calls with a unified, JSON-structured logger.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from enum import Enum
from pathlib import Path
from typing import Any

from config import get_config

cfg = get_config()


class LogCategory(str, Enum):
    INTENT = "intent"
    EXECUTION = "execution"
    MEMORY = "memory"
    ERROR = "error"
    AUTONOMY = "autonomy"
    SYSTEM = "system"
    SECURITY = "security"


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.time(),
            "level": record.levelname,
            "category": getattr(record, "category", "system"),
            "msg": record.getMessage(),
            "logger": record.name,
        }
        for key in ("session_id", "intent", "tool", "risk", "action", "error"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _build_logger() -> logging.Logger:
    logger = logging.getLogger("jarvis")
    if logger.handlers:
        return logger  # already configured

    logger.setLevel(logging.DEBUG)

    # Console handler (human-readable in dev; JSON always written to file)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(_JsonFormatter())
    logger.addHandler(ch)

    # File handler — JSON
    log_path = Path(cfg.jarvis_log_file) if hasattr(cfg, "jarvis_log_file") else Path("jarvis.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(_JsonFormatter())
    logger.addHandler(fh)

    logger.propagate = False
    return logger


_logger = _build_logger()


def _log(log_level: int, msg: str, category: LogCategory, **extra: Any) -> None:
    # Strip 'level' from extra to avoid collision with logging internals
    extra.pop("level", None)
    record = logging.LogRecord(
        name="jarvis",
        level=log_level,
        pathname="",
        lineno=0,
        msg=msg,
        args=(),
        exc_info=None,
    )
    record.category = category.value
    for k, v in extra.items():
        setattr(record, k, v)
    _logger.handle(record)


def log_intent(msg: str, **extra: Any) -> None:
    _log(logging.INFO, msg, LogCategory.INTENT, **extra)


def log_execution(msg: str, **extra: Any) -> None:
    _log(logging.INFO, msg, LogCategory.EXECUTION, **extra)


def log_memory(msg: str, **extra: Any) -> None:
    _log(logging.DEBUG, msg, LogCategory.MEMORY, **extra)


def log_error(msg: str, **extra: Any) -> None:
    _log(logging.ERROR, msg, LogCategory.ERROR, **extra)


def log_autonomy(msg: str, **extra: Any) -> None:
    _log(logging.INFO, msg, LogCategory.AUTONOMY, **extra)


def log_system(msg: str, **extra: Any) -> None:
    _log(logging.INFO, msg, LogCategory.SYSTEM, **extra)


def log_security(msg: str, **extra: Any) -> None:
    _log(logging.WARNING, msg, LogCategory.SECURITY, **extra)
