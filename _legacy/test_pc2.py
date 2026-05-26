import os

import httpx
from dotenv import load_dotenv


load_dotenv()

OLLAMA_URL = os.getenv("JARVIS_OLLAMA_URL", "http://localhost:11434")
MODEL = os.getenv("JARVIS_MODEL", "qwen2:0.5b")

print(f"Testando conexao com: {OLLAMA_URL}")
print(f"Modelo: {MODEL}")
print("-" * 40)

try:
    response = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5)
    response.raise_for_status()
    models = [item["name"] for item in response.json().get("models", [])]
    print(f"OK Conexao OK - Modelos disponiveis: {models}")
except Exception as exc:
    print(f"FALHA na conexao: {exc}")
    print("   Verifique se o Ollama esta rodando e se JARVIS_OLLAMA_URL esta correto")
    raise SystemExit(1)

print("\nTestando geracao de resposta...")
try:
    response = httpx.post(
        f"{OLLAMA_URL}/api/generate",
        json={"model": MODEL, "prompt": "diga apenas: JARVIS online", "stream": False},
        timeout=90,
    )
    response.raise_for_status()
    result = response.json().get("response", "")
    print(f"OK Resposta do {MODEL}: {result.strip()}")
except Exception as exc:
    print(f"ERRO na geracao: {exc}")
    raise SystemExit(1)

print("\n" + "=" * 40)
print("OK Ollama conectado e funcionando!")
print("=" * 40)