"""Agenda lembretes persistentes via Windows Task Scheduler"""
import subprocess
import platform
import os
from datetime import datetime
from pathlib import Path

from backend.utils.env import env_flag

def reminder(parameters: dict, response=None, player=None) -> str:
    date_str = parameters.get("date", "")
    time_str = parameters.get("time", "")
    message = parameters.get("message", "Lembrete do JARVIS")

    if not date_str or not time_str:
        return "Data e hora são obrigatórias. Formato: data YYYY-MM-DD, hora HH:MM"

    try:
        # Valida data/hora
        dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        formatted_time = dt.strftime("%H:%M")
        formatted_date = dt.strftime("%d/%m/%Y")

        if env_flag("JARVIS_TEST_MODE"):
            return f"Lembrete agendado para {formatted_date} às {formatted_time}: {message}"

        system = platform.system()

        if system == "Windows":
            # Cria script VBS para exibir popup
            vbs_path = Path.home() / f"jarvis_reminder_{dt.strftime('%Y%m%d_%H%M')}.vbs"
            vbs_content = f'''
Set oShell = CreateObject("WScript.Shell")
oShell.Popup "{message}", 30, "JARVIS - Lembrete", 64
'''
            vbs_path.write_text(vbs_content)

            # Registra no Task Scheduler
            task_name = f"JARVIS_Reminder_{dt.strftime('%Y%m%d_%H%M')}"
            cmd = (
                f'schtasks /create /tn "{task_name}" '
                f'/tr "wscript.exe \\"{vbs_path}\\"" '
                f'/sc once /sd {dt.strftime("%m/%d/%Y")} '
                f'/st {formatted_time} /f'
            )
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

            if result.returncode == 0:
                if player:
                    player.write_log(f"Lembrete agendado: {message} em {formatted_date} às {formatted_time}")
                return f"Lembrete agendado para {formatted_date} às {formatted_time}: {message}"
            else:
                return f"Erro ao criar lembrete: {result.stderr}"

        elif system == "Darwin":
            # macOS: usa launchd ou at
            cmd = f'echo "osascript -e \'display notification \\"{message}\\" with title \\"JARVIS\\\"' \
                  f'" | at {formatted_time} {formatted_date}'
            subprocess.run(cmd, shell=True)
            return f"Lembrete agendado para {formatted_date} às {formatted_time}: {message}"

        else:
            # Linux: usa at
            cmd = f'echo "notify-send JARVIS \\"{message}\\"" | at {formatted_time} {formatted_date}'
            subprocess.run(cmd, shell=True)
            return f"Lembrete agendado: {message}"

    except ValueError:
        return "Formato de data/hora inválido. Use YYYY-MM-DD e HH:MM"
    except Exception as e:
        return f"Erro ao agendar lembrete: {e}"
