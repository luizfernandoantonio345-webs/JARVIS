"""
Git tool — isolated, stateless.
Thin wrappers around git CLI using asyncio subprocess.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any


async def _run_git(*args: str, cwd: str | None = None) -> str:
    proc = await asyncio.create_subprocess_exec(
        "git", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(stderr.decode(errors="replace").strip())
    return stdout.decode(errors="replace").strip()


async def git_clone(parameters: dict[str, Any]) -> dict[str, Any]:
    url = parameters.get("url", "")
    dest = parameters.get("dest", "")
    if not url:
        raise ValueError("'url' parameter is required")
    args = ["clone", url]
    if dest:
        args.append(dest)
    output = await _run_git(*args)
    return {"message": f"Cloned {url}", "output": output}


async def git_commit(parameters: dict[str, Any]) -> dict[str, Any]:
    repo_path = parameters.get("path", ".")
    message = parameters.get("message", "chore: auto-commit")
    await _run_git("add", "-A", cwd=repo_path)
    output = await _run_git("commit", "-m", message, cwd=repo_path)
    return {"message": f"Committed: {message}", "output": output}
