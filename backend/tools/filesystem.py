"""
Filesystem tool — isolated, stateless.
Safe file read/write/delete with path validation.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from core.logger import log_security

# Blocked path patterns (security)
_BLOCKED = ["/etc/passwd", "/etc/shadow", "C:\\Windows\\System32"]


def _validate_path(raw_path: str) -> Path:
    path = Path(raw_path).resolve()
    for blocked in _BLOCKED:
        if str(path).startswith(blocked):
            log_security("blocked_path_access", path=str(path))
            raise PermissionError(f"Access to path is not allowed: {path}")
    return path


async def read_file(parameters: dict[str, Any]) -> dict[str, Any]:
    raw = parameters.get("path", "")
    if not raw:
        raise ValueError("'path' parameter is required")
    path = _validate_path(raw)
    content = await asyncio.to_thread(path.read_text, "utf-8")
    return {"message": f"Read {len(content)} chars from {path}", "content": content}


async def write_file(parameters: dict[str, Any]) -> dict[str, Any]:
    raw = parameters.get("path", "")
    content = parameters.get("content", "")
    if not raw:
        raise ValueError("'path' parameter is required")
    path = _validate_path(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(path.write_text, content, "utf-8")
    return {"message": f"Written {len(content)} chars to {path}"}


async def delete_file(parameters: dict[str, Any]) -> dict[str, Any]:
    raw = parameters.get("path", "")
    if not raw:
        raise ValueError("'path' parameter is required")
    path = _validate_path(raw)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    await asyncio.to_thread(path.unlink)
    return {"message": f"Deleted: {path}"}
