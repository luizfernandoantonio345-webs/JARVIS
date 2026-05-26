import httpx

BASE = "http://localhost:8000"
client = httpx.Client(timeout=15)

tests = [
    ("GET", "/health", None),
    ("POST", "/chat", {"message": "oi jarvis", "session_id": "test"}),
    ("POST", "/computer/weather", {"city": "São Paulo"}),
    ("POST", "/computer/youtube", {"action": "trending", "region": "BR"}),
    ("POST", "/computer/websearch", {"query": "capital do Brasil"}),
    ("POST", "/computer/memory", {"category": "identity", "key": "nome", "value": "Ricardo"}),
    ("GET", "/computer/memory/summary", None),
    ("GET", "/computer/memory/context", None),
    ("POST", "/computer/task", {"goal": "listar arquivos do desktop", "priority": "normal"}),
    ("GET", "/computer/tasks", None),
    ("POST", "/computer/control", {"action": "screenshot", "path": "test_screen.png"}),
    ("POST", "/computer/desktop", {"action": "stats"}),
    ("POST", "/computer/settings", {"action": "volume", "description": "mute"}),
    ("POST", "/computer/open-app", {"app_name": "notepad"}),
    ("POST", "/computer/filemanager", {"action": "list", "path": "desktop"}),
    ("POST", "/computer/code", {"action": "write", "description": "hello world", "language": "python"}),
    ("POST", "/computer/reminder", {"date": "2025-12-31", "time": "23:59", "message": "Feliz Ano Novo!"}),
    ("POST", "/computer/flights", {"origin": "GRU", "destination": "LIS", "date": "2025-12-01"}),
    ("POST", "/computer/games", {"action": "list"}),
]

print("=" * 60)
print("JARVIS — SMOKE TEST COMPLETO")
print("=" * 60)

passed = 0
failed = 0

for method, path, body in tests:
    try:
        if method == "GET":
            r = client.get(BASE + path)
        else:
            r = client.post(BASE + path, json=body)

        status = "✅" if r.status_code < 400 else "❌"
        if r.status_code < 400:
            passed += 1
        else:
            failed += 1
        print(f"{status} {method} {path} → {r.status_code}")
        if r.status_code >= 400:
            print(f"   Erro: {r.text[:100]}")
    except Exception as e:
        failed += 1
        print(f"❌ {method} {path} → EXCEPTION: {e}")

print("=" * 60)
print(f"Resultado: {passed} ✅  {failed} ❌  de {len(tests)} testes")
print("=" * 60)