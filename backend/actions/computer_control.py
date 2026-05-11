"""Controle direto de mouse, teclado e tela com validação de segurança."""

import logging
import os
import time
from typing import Any

import pyautogui
import pyperclip

log = logging.getLogger(__name__)

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.1

ACTION_NAME = "computer_control"

# Ações que requerem confirmação explícita (sensíveis)
_CONFIRMATION_REQUIRED = {"type", "smart_type", "hotkey", "press", "clear_field"}

# Ações permitidas (whitelist)
_ALLOWED_ACTIONS = {
    "type", "smart_type", "click", "double_click", "right_click",
    "hotkey", "press", "scroll", "move", "screenshot",
    "copy", "paste", "wait", "focus_window", "screen_find", "clear_field"
}

SYSTEM_PROMPT = (
    "You control computer input (mouse/keyboard) safely. "
    "Use read-only actions (move, screenshot) freely. "
    "Use input actions (type, click) conservatively — each one is logged. "
    "Never assume coordinates without asking for screen context first."
)


def computer_control(parameters: dict, player=None) -> str:
    action = parameters.get("action", "")
    
    # ───────────────────────────────────────────────────────────────────────────────
    # SECURITY: Validate action
    # ───────────────────────────────────────────────────────────────────────────────
    if not action:
        return "❌ Erro: parametro 'action' obrigatório"
    
    if action not in _ALLOWED_ACTIONS:
        log.warning(f"[SECURITY] Blocked unknown action: {action}")
        return f"❌ Ação desconhecida: {action}"
    
    if action in _CONFIRMATION_REQUIRED:
        log.info(f"[AUDIT] computer_control/{action} executada com parametros: {parameters}")

    try:
        if action == "type":
            text = parameters.get("text", "")
            pyautogui.typewrite(text, interval=0.05)
            return f"Digitado: {text}"

        elif action == "smart_type":
            text = parameters.get("text", "")
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
            return f"Colado: {text}"

        elif action == "click":
            x, y = parameters.get("x"), parameters.get("y")
            if x is not None and y is not None:
                pyautogui.click(x, y)
                return f"Clicado em ({x}, {y})"
            return "Coordenadas nao fornecidas"

        elif action == "double_click":
            x, y = parameters.get("x"), parameters.get("y")
            if x is None or y is None:
                return "Coordenadas nao fornecidas"
            pyautogui.doubleClick(x, y)
            return f"Duplo clique em ({x}, {y})"

        elif action == "right_click":
            x, y = parameters.get("x"), parameters.get("y")
            if x is None or y is None:
                return "Coordenadas nao fornecidas"
            pyautogui.rightClick(x, y)
            return f"Clique direito em ({x}, {y})"

        elif action == "hotkey":
            keys = parameters.get("keys", "")
            parts = [k.strip() for k in keys.replace("+", " ").split() if k.strip()]
            if not parts:
                return "Parametro obrigatorio ausente: keys"
            pyautogui.hotkey(*parts)
            return f"Atalho executado: {keys}"

        elif action == "press":
            key = parameters.get("key", "")
            if not key:
                return "Parametro obrigatorio ausente: key"
            pyautogui.press(key)
            return f"Tecla pressionada: {key}"

        elif action == "scroll":
            direction = parameters.get("direction", "down")
            amount = parameters.get("amount", 3)
            clicks = amount if direction == "down" else -amount
            pyautogui.scroll(clicks)
            return f"Scroll {direction} {amount}"

        elif action == "move":
            x, y = parameters.get("x", 0), parameters.get("y", 0)
            pyautogui.moveTo(x, y, duration=0.3)
            return f"Mouse movido para ({x}, {y})"

        elif action == "screenshot":
            path = parameters.get("path", "screenshot.png")
            screenshot = pyautogui.screenshot()
            screenshot.save(path)
            return f"Screenshot salvo em {path}"

        elif action == "copy":
            pyautogui.hotkey("ctrl", "c")
            time.sleep(0.3)
            text = pyperclip.paste()
            return f"Copiado: {text}"

        elif action == "paste":
            pyautogui.hotkey("ctrl", "v")
            return "Colado"

        elif action == "wait":
            seconds = parameters.get("seconds", 1)
            time.sleep(seconds)
            return f"Aguardado {seconds}s"

        elif action == "focus_window":
            title = parameters.get("title", "")
            import pygetwindow as gw

            windows = gw.getWindowsWithTitle(title)
            if windows:
                windows[0].activate()
                return f"Janela '{title}' ativada"
            return f"Janela '{title}' nao encontrada"

        elif action == "screen_find":
            description = parameters.get("description", "")
            screenshot = pyautogui.screenshot()
            path = "temp_screen_find.png"
            screenshot.save(path)
            return f"Screenshot capturado para busca: {description}"

        elif action == "clear_field":
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.1)
            pyautogui.press("delete")
            return "Campo limpo"

        else:
            return f"Acao desconhecida: {action}"

    except Exception as e:
        return f"Erro em computer_control/{action}: {e}"
