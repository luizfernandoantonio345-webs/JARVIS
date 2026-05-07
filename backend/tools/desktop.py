"""
Desktop automation tool — isolated, stateless.
Wraps pyautogui / subprocess for app/browser control.
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from typing import Any


async def open_app(parameters: dict[str, Any]) -> dict[str, Any]:
    """Open a desktop application by name or path."""
    app = parameters.get("app") or parameters.get("name", "")
    if not app:
        raise ValueError("'app' parameter is required")

    if sys.platform == "win32":
        proc = await asyncio.create_subprocess_shell(
            f'start "" "{app}"',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    elif sys.platform == "darwin":
        proc = await asyncio.create_subprocess_exec(
            "open", "-a", app,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    else:
        proc = await asyncio.create_subprocess_exec(
            app,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    _, stderr = await proc.communicate()
    if proc.returncode and proc.returncode != 0:
        raise RuntimeError(stderr.decode(errors="replace").strip())
    return {"message": f"Launched: {app}"}


async def open_browser(parameters: dict[str, Any]) -> dict[str, Any]:
    """Open the default browser."""
    import webbrowser
    url = parameters.get("url", "https://google.com")
    await asyncio.to_thread(webbrowser.open, url)
    return {"message": f"Browser opened: {url}"}


async def go_to_url(parameters: dict[str, Any]) -> dict[str, Any]:
    """Navigate to a URL in the default browser."""
    url = parameters.get("url", "")
    if not url:
        raise ValueError("'url' parameter is required")
    import webbrowser
    await asyncio.to_thread(webbrowser.open, url)
    return {"message": f"Navigated to: {url}"}
