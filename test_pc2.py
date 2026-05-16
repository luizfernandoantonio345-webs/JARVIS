import os

import httpx
from dotenv import load_dotenv


load_dotenv()

OLLAMA_URL = os.getenv("JARVIS_OLLAMA_URL", "http://192.168.0.106:11434")
MODEL = os.getenv("JARVIS_MODEL", "phi:latest")

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
    print("   Verifique se o PC2 esta ligado e o Ollama esta rodando")
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
print("OK PC2 conectado e funcionando!")
print("=" * 40)