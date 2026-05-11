"""Abre aplicativos por nome."""

import platform
import shutil
import subprocess

APP_MAP_WINDOWS = {
    "chrome": "chrome",
    "google chrome": "chrome",
    "firefox": "firefox",
    "edge": "msedge",
    "notepad": "notepad",
    "bloco de notas": "notepad",
    "calculator": "calc",
    "calculadora": "calc",
    "explorer": "explorer",
    "vscode": "code",
    "visual studio code": "code",
    "spotify": "spotify",
    "discord": "discord",
    "whatsapp": "whatsapp",
    "telegram": "telegram",
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
    "paint": "mspaint",
    "cmd": "cmd",
    "terminal": "wt",
    "powershell": "powershell",
    "task manager": "taskmgr",
    "gerenciador de tarefas": "taskmgr",
    "steam": "steam",
    "vlc": "vlc",
}


def open_app(parameters: dict, response=None, player=None) -> str:
    app_name = parameters.get("app_name", "").lower().strip()
    system = platform.system()

    try:
        if system == "Windows":
            cmd = APP_MAP_WINDOWS.get(app_name, app_name)
            subprocess.Popen(cmd, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
            return f"Abrindo {app_name}"

        elif system == "Darwin":
            subprocess.Popen(["open", "-a", app_name])
            return f"Abrindo {app_name}"

        else:
            if shutil.which(app_name):
                subprocess.Popen([app_name])
                return f"Abrindo {app_name}"
            return f"Aplicativo nao encontrado: {app_name}"

    except Exception as e:
        return f"Erro ao abrir {app_name}: {e}"
