import httpx, json, sys

BASE = "http://localhost:8000"
SESSION = "tony-stark-test"

def chat(msg):
    try:
        r = httpx.post(f"{BASE}/chat",
            json={"message": msg, "session_id": SESSION},
            timeout=30)
        if r.status_code != 200:
            return f"ERRO {r.status_code}: {r.text[:150]}"
        d = r.json()
        return d.get("response") or d.get("message") or d.get("reply") or str(d)[:200]
    except Exception as e:
        return f"EXCEPTION: {e}"

conversas = [
    "Olá JARVIS",
    "Qual é o seu nome?",
    "O que você consegue fazer?",
    "Que horas são agora?",
    "Quanto é 15% de 3500?",
    "Me cria um script Python que imprime Hello World",
    "Qual foi o último comando que executei?",
    "Valeu JARVIS, pode descansar",
]

print("=" * 60)
ok = 0
fail = 0
for msg in conversas:
    print(f"\n[HUMANO] {msg}")
    resp = chat(msg)
    preview = resp[:200] if resp else ""
    print(f"[JARVIS] {preview}")
    if "ERRO" in resp or "EXCEPTION" in resp or not resp.strip():
        print("  ⚠️  PROBLEMA")
        fail += 1
    else:
        ok += 1

print(f"\n{'='*60}")
print(f"RESULTADO: {ok} OK | {fail} FALHAS")
