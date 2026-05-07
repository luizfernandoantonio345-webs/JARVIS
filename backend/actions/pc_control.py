from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


def open_application(name: str) -> dict:
    aliases = {
        "chrome": ["cmd", "/c", "start", "", "chrome"],
        "google chrome": ["cmd", "/c", "start", "", "chrome"],
        "edge": ["cmd", "/c", "start", "", "msedge"],
        "vscode": ["cmd", "/c", "start", "", "code"],
        "vs code": ["cmd", "/c", "start", "", "code"],
        "code": ["cmd", "/c", "start", "", "code"],
        "notepad": ["notepad.exe"],
    }
    key = name.strip().lower()
    args = aliases.get(key)
    if not args:
        raise ValueError(f"Unsupported application: {name}")
    proc = subprocess.Popen(args if os.name == "nt" else [key])
    return {"app": name, "pid": proc.pid}


def focus_window(title: str) -> dict:
    gw = __import__("pygetwindow")
    matches = [window for window in gw.getAllWindows() if title.lower() in window.title.lower()]
    if not matches:
        return {"focused": False, "title": title}
    window = matches[0]
    window.activate()
    return {"focused": True, "title": window.title}


def type_text(text: str) -> dict:
    pyautogui = __import__("pyautogui")
    pyautogui.write(text, interval=0.01)
    return {"typed": len(text)}


def press_keys(*keys: str) -> dict:
    pyautogui = __import__("pyautogui")
    pyautogui.hotkey(*keys)
    return {"pressed": list(keys)}


def take_screenshot() -> str:
    pyautogui = __import__("pyautogui")
    path = Path(tempfile.mktemp(prefix="jarvis_screen_", suffix=".png"))
    pyautogui.screenshot(str(path))
    return str(path)


def get_active_window() -> str:
    gw = __import__("pygetwindow")
    window = gw.getActiveWindow()
    return window.title if window else ""


def list_open_windows() -> list[str]:
    gw = __import__("pygetwindow")
    return [window.title for window in gw.getAllWindows() if window.title]
