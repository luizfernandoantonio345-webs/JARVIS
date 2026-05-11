"""Controle de configuracoes do computador."""

import platform
import subprocess

import pyautogui


def computer_settings(parameters: dict, response=None, player=None) -> str:
    action = parameters.get("action", "")
    description = parameters.get("description", "").lower()
    value = parameters.get("value", "")

    combined = (action + " " + description).lower()

    try:
        # Volume
        if any(w in combined for w in ["volume", "som", "mute", "mudo"]):
            if "mute" in combined or "mudo" in combined:
                pyautogui.press("volumemute")
                return "Volume mutado"
            elif "up" in combined or "aumentar" in combined or "subir" in combined:
                for _ in range(5):
                    pyautogui.press("volumeup")
                return "Volume aumentado"
            elif "down" in combined or "diminuir" in combined or "baixar" in combined:
                for _ in range(5):
                    pyautogui.press("volumedown")
                return "Volume diminuido"

        # Brightness (Windows)
        elif any(w in combined for w in ["brightness", "brilho"]):
            level = int(value) if value else 70
            if platform.system() == "Windows":
                subprocess.run(
                    [
                        "powershell",
                        "-Command",
                        (
                            "(Get-WmiObject -Namespace root/WMI -Class "
                            f"WmiMonitorBrightnessMethods).WmiSetBrightness(1,{level})"
                        ),
                    ],
                    capture_output=True,
                )
            return f"Brilho ajustado para {level}%"

        # Screenshot
        elif any(w in combined for w in ["screenshot", "captura", "printscreen"]):
            path = value or "screenshot.png"
            pyautogui.screenshot(path)
            return f"Screenshot salvo: {path}"

        # Dark mode
        elif any(w in combined for w in ["dark", "escuro", "night"]):
            if platform.system() == "Windows":
                subprocess.run(
                    [
                        "reg",
                        "add",
                        r"HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                        "/v",
                        "AppsUseLightTheme",
                        "/t",
                        "REG_DWORD",
                        "/d",
                        "0",
                        "/f",
                    ],
                    capture_output=True,
                )
            return "Modo escuro ativado"

        # Lock screen
        elif any(w in combined for w in ["lock", "travar", "bloquear"]):
            if platform.system() == "Windows":
                import ctypes

                ctypes.windll.user32.LockWorkStation()
            return "Tela bloqueada"

        # Shutdown
        elif any(w in combined for w in ["shutdown", "desligar"]):
            if platform.system() == "Windows":
                subprocess.run(["shutdown", "/s", "/t", "10"])
            return "Computador desligando em 10 segundos"

        # Restart
        elif any(w in combined for w in ["restart", "reiniciar"]):
            if platform.system() == "Windows":
                subprocess.run(["shutdown", "/r", "/t", "10"])
            return "Computador reiniciando em 10 segundos"

        # Fullscreen
        elif any(w in combined for w in ["fullscreen", "tela cheia"]):
            pyautogui.press("f11")
            return "Alternado tela cheia"

        # Zoom
        elif any(w in combined for w in ["zoom in", "aumentar zoom"]):
            pyautogui.hotkey("ctrl", "+")
            return "Zoom aumentado"
        elif any(w in combined for w in ["zoom out", "diminuir zoom"]):
            pyautogui.hotkey("ctrl", "-")
            return "Zoom diminuido"

        else:
            return f"Configuracao nao reconhecida: {combined}"

    except Exception as e:
        return f"Erro computer_settings: {e}"
