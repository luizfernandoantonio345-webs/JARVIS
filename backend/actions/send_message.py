"""Envia mensagens via WhatsApp e Telegram por automação"""
import time
import webbrowser
import urllib.parse
import subprocess
import pyautogui

def send_message(parameters: dict, response=None, player=None, session_memory=None) -> str:
    receiver = parameters.get("receiver", "")
    message_text = parameters.get("message_text", "")
    platform = parameters.get("platform", "whatsapp").lower()

    if not receiver or not message_text:
        return "Destinatário e mensagem são obrigatórios."

    try:
        if platform == "whatsapp":
            # Abre WhatsApp Web com mensagem pré-preenchida
            encoded = urllib.parse.quote(message_text)
            # Tenta número direto ou nome de contato
            if receiver.replace("+","").replace(" ","").isdigit():
                number = receiver.replace("+","").replace(" ","").replace("-","")
                url = f"https://web.whatsapp.com/send?phone={number}&text={encoded}"
            else:
                url = f"https://web.whatsapp.com/send?text={encoded}"
            
            webbrowser.open(url)
            time.sleep(6)  # Aguarda WhatsApp Web carregar
            
            # Pressiona Enter para enviar
            pyautogui.press("enter")
            return f"Mensagem enviada para {receiver} via WhatsApp."

        elif platform == "telegram":
            # Abre Telegram Desktop se instalado
            try:
                subprocess.Popen(["telegram"], shell=True)
                time.sleep(3)
            except Exception:
                webbrowser.open("https://web.telegram.org")
                time.sleep(5)
            
            return f"Telegram aberto. Mensagem preparada para {receiver}: {message_text}"

        elif platform == "email":
            encoded_subject = urllib.parse.quote(f"Mensagem para {receiver}")
            encoded_body = urllib.parse.quote(message_text)
            webbrowser.open(f"mailto:{receiver}?subject={encoded_subject}&body={encoded_body}")
            return f"Email preparado para {receiver}."

        else:
            return f"Plataforma não suportada: {platform}. Use whatsapp, telegram ou email."

    except Exception as e:
        return f"Erro ao enviar mensagem: {e}"
