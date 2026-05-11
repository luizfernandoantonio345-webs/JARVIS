"""Captura e analisa a tela usando Ollama vision."""

import base64

import httpx
import pyautogui


def screen_process(parameters: dict, response=None, player=None, session_memory=None) -> str:
    angle = parameters.get("angle", "screen")
    question = parameters.get("text", "O que esta na tela?")

    try:
        if angle == "screen":
            screenshot = pyautogui.screenshot()
            path = "temp_screen_analysis.png"
            screenshot.save(path)
        elif angle == "camera":
            import cv2

            cap = cv2.VideoCapture(0)
            ret, frame = cap.read()
            cap.release()
            if not ret:
                return "Camera nao disponivel"
            path = "temp_camera.png"
            cv2.imwrite(path, frame)
        else:
            return "Angulo invalido: use 'screen' ou 'camera'"

        with open(path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()

        # Tenta com Ollama vision (llava ou moondream)
        for model in ["llava", "moondream", "bakllava"]:
            try:
                resp = httpx.post(
                    "http://localhost:11434/api/generate",
                    json={
                        "model": model,
                        "prompt": question,
                        "images": [img_b64],
                        "stream": False,
                    },
                    timeout=30,
                )
                if resp.status_code == 200:
                    result = resp.json().get("response", "")
                    if result:
                        if player:
                            player.write_log(f"Visao ({model}): {result[:200]}")
                        return result
            except Exception:
                continue

        return "Modelo de visao nao disponivel. Instale com: ollama pull llava"

    except Exception as e:
        return f"Erro screen_processor: {e}"
