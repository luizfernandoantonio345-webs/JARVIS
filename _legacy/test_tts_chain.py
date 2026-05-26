import httpx, asyncio, os, sys

BASE = "http://localhost:8000"

print("=" * 60)
print("DIAGNOSTICO COMPLETO DE VOZ")
print("=" * 60)

# A: endpoint /tts
print("\n[A] GET /tts...")
try:
    r = httpx.get(f"{BASE}/tts", params={"text": "JARVIS online. All systems operational.", "lang": "pt"}, timeout=15)
    print(f"  Status: {r.status_code}")
    print(f"  Content-Type: {r.headers.get('content-type')}")
    print(f"  Size: {len(r.content)} bytes")
    if r.status_code == 200 and len(r.content) > 1000:
        with open("jarvis_voice_test.mp3","wb") as f: f.write(r.content)
        print("  ✅ /tts OK — arquivo: jarvis_voice_test.mp3")
    else:
        print(f"  ❌ /tts FALHOU: {r.text[:200]}")
except Exception as e:
    print(f"  ❌ {e}")

# B: edge-tts direto
print("\n[B] edge-tts direto (Iron Man voice)...")
try:
    import edge_tts
    async def test_edge():
        c = edge_tts.Communicate(
            "Good morning. I am JARVIS, your personal assistant. All systems are online.",
            "en-GB-RyanNeural", rate="-8%", pitch="-12Hz"
        )
        await c.save("jarvis_ryan_test.mp3")
        sz = os.path.getsize("jarvis_ryan_test.mp3")
        print(f"  ✅ en-GB-RyanNeural OK — {sz} bytes")
        return sz
    asyncio.run(test_edge())
except ImportError:
    print("  ❌ edge-tts não instalado")
except Exception as e:
    print(f"  ❌ {e}")

# C: vozes britânicas disponíveis
print("\n[C] Vozes en-GB / en-AU disponíveis:")
try:
    import edge_tts
    async def list_v():
        vs = await edge_tts.list_voices()
        brit = [v for v in vs if "en-GB" in v["Locale"] or "en-AU" in v["Locale"]]
        for v in brit:
            print(f"  {v['ShortName']} — {v.get('Gender','?')} — {v['Locale']}")
    asyncio.run(list_v())
except Exception as e:
    print(f"  ❌ {e}")

# D: rotas registradas
print("\n[D] Rotas /tts no OpenAPI:")
try:
    r = httpx.get(f"{BASE}/openapi.json", timeout=5)
    paths = list(r.json().get("paths",{}).keys())
    tts = [p for p in paths if "tts" in p.lower()]
    print(f"  TTS routes: {tts}")
    print(f"  Total routes: {len(paths)}")
except Exception as e:
    print(f"  ❌ {e}")

print("\n[E] Testando POST /chat direto ao LLM...")
try:
    r = httpx.post(f"{BASE}/chat",
        json={"message":"responda apenas a palavra: ONLINE","session_id":"test-llm"},
        timeout=30)
    print(f"  Status: {r.status_code}")
    if r.status_code == 200:
        d = r.json()
        resp = d.get("response") or d.get("message") or str(d)[:200]
        print(f"  Resposta: {resp[:150]}")
        print(f"  ✅ LLM OK")
    else:
        print(f"  ❌ {r.text[:200]}")
except Exception as e:
    print(f"  ❌ {e}")
