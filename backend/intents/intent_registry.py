from __future__ import annotations

import asyncio
import logging
import subprocess
import webbrowser
from collections.abc import Awaitable, Callable
from typing import Any

log = logging.getLogger(__name__)
IntentHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


async def open_browser_handler(parameters: dict[str, Any]) -> dict[str, Any]:
    url = str(parameters.get("url") or "about:blank")
    opened = await asyncio.to_thread(webbrowser.open, url)
    return {"opened": opened, "url": url, "tool": "webbrowser"}


async def go_to_url_handler(parameters: dict[str, Any]) -> dict[str, Any]:
    url = str(parameters.get("url") or parameters.get("target") or "").strip()
    if not url:
        raise ValueError("Missing url parameter")
    if "://" not in url:
        url = "https://" + url
    opened = await asyncio.to_thread(webbrowser.open, url)
    return {"opened": opened, "url": url, "tool": "webbrowser"}


async def open_app_handler(parameters: dict[str, Any]) -> dict[str, Any]:
    app = str(parameters.get("app") or parameters.get("name") or "").strip()
    if not app:
        raise ValueError("Missing app parameter")
    # Controlled handler: never executes raw user text as a command line.
    import os
    import subprocess

    aliases = {
        "chrome": ["cmd", "/c", "start", "", "chrome"],
        "google chrome": ["cmd", "/c", "start", "", "chrome"],
        "edge": ["cmd", "/c", "start", "", "msedge"],
        "notepad": ["notepad.exe"],
        "vscode": ["cmd", "/c", "start", "", "code"],
        "code": ["cmd", "/c", "start", "", "code"],
    }
    key = app.lower()
    if key not in aliases:
        raise ValueError(f"Unsupported app '{app}'. Add a registry handler or alias first.")
    if os.name == "nt":
        proc = await asyncio.to_thread(subprocess.Popen, aliases[key])
        return {"app": app, "pid": proc.pid, "tool": "subprocess-controlled-alias"}
    raise ValueError("open_app is currently implemented for Windows aliases only")


async def denied_high_risk_handler(parameters: dict[str, Any]) -> dict[str, Any]:
    raise PermissionError("High-risk action requires an explicit approved handler and confirmation")


async def status_handler(parameters: dict[str, Any]) -> dict[str, Any]:
    try:
        import psutil

        return {
            "status": "ok",
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_percent": psutil.virtual_memory().percent,
        }
    except Exception:
        return {"status": "ok"}


async def stop_handler(parameters: dict[str, Any]) -> dict[str, Any]:
    return {"stopped": True, "message": "Operacao cancelada."}


async def voice_mute_handler(parameters: dict[str, Any]) -> dict[str, Any]:
    return {"voice_enabled": False, "message": "Modo silencioso ativado."}


async def voice_enable_handler(parameters: dict[str, Any]) -> dict[str, Any]:
    return {"voice_enabled": True, "message": "Voz ativada."}


async def create_file_handler(parameters: dict[str, Any]) -> dict[str, Any]:
    path = str(parameters.get("path") or "novo_arquivo.txt").strip()
    content = str(parameters.get("content") or "")
    if not path:
        raise ValueError("Missing path parameter")
    from actions.vscode_control import create_file

    result = await asyncio.to_thread(create_file, path, content)
    return {"path": path, "result": result}


async def run_command_handler(parameters: dict[str, Any]) -> dict[str, Any]:
    command = str(parameters.get("command") or "").strip()
    if not command:
        raise ValueError("Missing command parameter")
    from actions.shell_exec import run_process

    result = await asyncio.to_thread(run_process, command)
    return {"command": command, "result": str(result)}


async def git_commit_handler(parameters: dict[str, Any]) -> dict[str, Any]:
    message = str(parameters.get("message") or "chore: update jarvis").strip()
    proc = await asyncio.to_thread(
        subprocess.run,
        ["git", "commit", "-am", message],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return {
        "message": message,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-2000:],
        "stderr": proc.stderr[-2000:],
    }


async def daily_report_handler(parameters: dict[str, Any]) -> dict[str, Any]:
    return {"message": "Relatorio do dia ainda sem tarefas pendentes consolidadas."}


async def next_steps_handler(parameters: dict[str, Any]) -> dict[str, Any]:
    return {"message": "Proximos passos: revisar telemetria, auditoria e dashboard."}


async def search_web_handler(parameters: dict[str, Any]) -> dict[str, Any]:
    query = str(parameters.get("query") or "").strip()
    if not query:
        raise ValueError("Missing query parameter")
    from actions.web_search import execute as search_web

    result = await asyncio.to_thread(search_web, query)
    return {"query": query, "result": result}


async def night_mode_handler(parameters: dict[str, Any]) -> dict[str, Any]:
    return {"night_mode": True, "message": "Modo noturno ativado."}


async def clear_memory_handler(parameters: dict[str, Any]) -> dict[str, Any]:
    raise PermissionError("Limpar memoria exige confirmacao explicita.")


async def take_screenshot_handler(parameters: dict[str, Any]) -> dict[str, Any]:
    try:
        from actions.pc_control import take_screenshot
    except Exception:
        import tempfile
        from pathlib import Path

        def take_screenshot() -> str:
            pyautogui = __import__("pyautogui")
            path = Path(tempfile.mktemp(prefix="jarvis_screen_", suffix=".png"))
            pyautogui.screenshot(str(path))
            return str(path)

    path = await asyncio.to_thread(take_screenshot)
    return {"screenshot": str(path)}


ACTION_REGISTRY: dict[str, IntentHandler] = {
    "open_browser": open_browser_handler,
    "go_to_url": go_to_url_handler,
    "navigate": go_to_url_handler,
    "open_app": open_app_handler,
    "purchase": denied_high_risk_handler,
    "delete_file": denied_high_risk_handler,
    "system_change": denied_high_risk_handler,
    "status": status_handler,
    "stop": stop_handler,
    "voice_mute": voice_mute_handler,
    "voice_enable": voice_enable_handler,
    "create_file": create_file_handler,
    "run_command": run_command_handler,
    "git_commit": git_commit_handler,
    "daily_report": daily_report_handler,
    "next_steps": next_steps_handler,
    "search_web": search_web_handler,
    "night_mode": night_mode_handler,
    "clear_memory": clear_memory_handler,
    "take_screenshot": take_screenshot_handler,
}


def get_handler(action: str) -> IntentHandler | None:
    return ACTION_REGISTRY.get(action.strip().lower())


def list_registered_actions() -> list[str]:
    return sorted(ACTION_REGISTRY)
