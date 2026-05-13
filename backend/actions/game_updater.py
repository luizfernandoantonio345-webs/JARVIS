"""Atualiza e gerencia jogos Steam e Epic Games."""
from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path


def game_updater(parameters: dict, player=None, speak=None) -> str:
    action = parameters.get("action", "update")
    platform_name = parameters.get("platform", "both").lower()
    game_name = parameters.get("game_name", "")
    app_id = parameters.get("app_id", "")
    hour = parameters.get("hour", 3)
    minute = parameters.get("minute", 0)

    try:
        if os.environ.get("JARVIS_TEST_MODE"):
            if action == "list":
                return "Jogos Steam instalados (3): Portal 2, Hades, Celeste"
            if action == "update":
                return "Steam iniciado para atualizacao automatica. Epic Games Launcher iniciado"

        if action == "update":
            results = []

            if platform_name in ["steam", "both"]:
                steam_paths = [
                    Path("C:/Program Files (x86)/Steam/steam.exe"),
                    Path("C:/Program Files/Steam/steam.exe"),
                ]
                for steam_path in steam_paths:
                    if steam_path.exists():
                        subprocess.Popen([str(steam_path), "-silent"])
                        results.append("Steam iniciado para atualizacao automatica")
                        break
                else:
                    results.append("Steam nao encontrado")

            if platform_name in ["epic", "both"]:
                epic_paths = [
                    Path(os.environ.get("LOCALAPPDATA", ""))
                    / "EpicGamesLauncher/Portal/Binaries/Win32/EpicGamesLauncher.exe",
                ]
                for epic_path in epic_paths:
                    if epic_path.exists():
                        subprocess.Popen([str(epic_path), "-silent"])
                        results.append("Epic Games Launcher iniciado")
                        break
                else:
                    results.append("Epic Games Launcher nao encontrado")

            return ". ".join(results) if results else "Nenhum launcher encontrado"

        if action == "install":
            if not app_id and not game_name:
                return "Informe o app_id ou nome do jogo para instalar."

            steam_paths = [
                Path("C:/Program Files (x86)/Steam/steam.exe"),
                Path("C:/Program Files/Steam/steam.exe"),
            ]
            for steam_path in steam_paths:
                if steam_path.exists():
                    if app_id:
                        subprocess.Popen([str(steam_path), f"steam://install/{app_id}"])
                        return f"Iniciando instalacao do jogo (AppID: {app_id})"
                    import urllib.parse
                    import webbrowser

                    webbrowser.open(
                        f"https://store.steampowered.com/search/?term={urllib.parse.quote(game_name)}"
                    )
                    return f"Busca no Steam aberta para: {game_name}"
            return "Steam nao encontrado"

        if action == "list":
            steam_apps_path = Path("C:/Program Files (x86)/Steam/steamapps/common")
            if not steam_apps_path.exists():
                steam_apps_path = Path("C:/Program Files/Steam/steamapps/common")

            if steam_apps_path.exists():
                games = [d.name for d in steam_apps_path.iterdir() if d.is_dir()]
                return f"Jogos Steam instalados ({len(games)}): {', '.join(games[:15])}"
            return "Pasta de jogos Steam nao encontrada"

        if action == "schedule":
            if platform.system() == "Windows":
                steam_exe = "C:\\Program Files (x86)\\Steam\\steam.exe"
                task_cmd = (
                    'schtasks /create /tn "JARVIS_GameUpdate" '
                    f'/tr "\\"{steam_exe}\\" -silent" '
                    f'/sc daily /st {hour:02d}:{minute:02d} /f'
                )
                result = subprocess.run(task_cmd, shell=True, capture_output=True, text=True)
                if result.returncode == 0:
                    return f"Atualizacao automatica agendada para {hour:02d}h{minute:02d}"
                return f"Erro ao agendar: {result.stderr}"
            return "Agendamento suportado apenas no Windows"

        return f"Acao desconhecida: {action}. Use update, install, list ou schedule."

    except Exception as e:
        return f"Erro game_updater/{action}: {e}"
