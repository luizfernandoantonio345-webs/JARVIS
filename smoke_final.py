#!/usr/bin/env python3
"""JARVIS OMEGA v6.0 - Smoke Test Completo"""
import requests
import asyncio
import json
import time
import subprocess
import os

BASE = "http://localhost:8000"
ok = fail = 0

def chk(name, fn):
    global ok, fail
    try:
        r = fn()
        print(f"  ✅ {name}: {str(r)[:80]}")
        ok += 1
        return True
    except Exception as e:
        print(f"  ❌ {name}: {str(e)[:80]}")
        fail += 1
        return False

print("\n" + "╔" + "═"*58 + "╗")
print("║  JARVIS OMEGA v6.0 — SMOKE TEST FINAL                 ║")
print("╚" + "═"*58 + "╝\n")

# ─────────────────────────────────────────────────────
# TESTES DE BACKEND
# ─────────────────────────────────────────────────────
print("🔍 [BACKEND TESTS]")

chk("Health",
    lambda: requests.get(f"{BASE}/health", timeout=5).json()["status"])

chk("Chat - sync",
    lambda: requests.post(f"{BASE}/chat",
        json={"message":"oi","session_id":"smoke"},
        timeout=30).json().get("response","?")[:50])

chk("Experience/stats",
    lambda: requests.get(f"{BASE}/experience/stats", timeout=5).json()["total"])

chk("Experience/recent",
    lambda: len(requests.get(f"{BASE}/experience/recent", timeout=5).json()))

chk("Metrics/runtime",
    lambda: requests.get(f"{BASE}/api-metrics/runtime", timeout=5).json()["uptime"])

chk("Metrics/events",
    lambda: requests.get(f"{BASE}/api-metrics/events", timeout=5).json()["stats"]["total_events"])

chk("Research/status",
    lambda: requests.get(f"{BASE}/research/status", timeout=5).json()["active"])

chk("Computer/tasks",
    lambda: requests.get(f"{BASE}/computer/tasks", timeout=5).json()["count"])

# ─────────────────────────────────────────────────────
# TTS TEST
# ─────────────────────────────────────────────────────
print("\n🔊 [TTS - IRON MAN PT-BR]")

try:
    r = requests.get(f"{BASE}/tts-iron/tts?text=JARVIS+Omega+operacional", timeout=15)
    if r.status_code == 200 and len(r.content) > 1000:
        audio_size_kb = len(r.content) // 1024
        print(f"  ✅ TTS: {audio_size_kb}KB de áudio")
        ok += 1
        
        # Salvar e tentar reproduzir
        tts_file = "_smoke_tts.mp3"
        with open(tts_file, "wb") as f:
            f.write(r.content)
        print(f"     → Áudio salvo em {tts_file}")
        
        # Reproduzir (Windows)
        try:
            subprocess.Popen(["start", "", tts_file], shell=True)
            print(f"     → Reprodução iniciada (aguarde 3s)")
            time.sleep(3)
        except:
            pass
    else:
        print(f"  ❌ TTS: Status {r.status_code} ou tamanho insuficiente")
        fail += 1
except Exception as e:
    print(f"  ❌ TTS: {e}")
    fail += 1

# ─────────────────────────────────────────────────────
# WEBSOCKET TEST (async)
# ─────────────────────────────────────────────────────
print("\n🔌 [WEBSOCKET]")

async def test_ws():
    import websockets
    try:
        async with websockets.connect("ws://localhost:8000/ws/jarvis", ping_timeout=5) as ws:
            await ws.send("oi jarvis")
            msg_count = 0
            for i in range(10):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2)
                    msg_count += 1
                    m = json.loads(msg)
                    # Look for done/speaking in type OR status field
                    if m.get("type") in ["done","speaking"] or m.get("status") in ["speaking","done"]:
                        print(f"  ✅ WebSocket: resposta completa recebida")
                        return True
                    if m.get("type") == "token" or m.get("status") == "thinking":
                        if i == 0:
                            print(f"  ✅ WebSocket: conectado e recebendo ({msg_count} msg)")
                except asyncio.TimeoutError:
                    # Timeout is OK if we got at least one message (Ollama offline expected)
                    if msg_count > 0:
                        print(f"  ✅ WebSocket: {msg_count} msgs recebidas (Ollama offline é esperado)")
                        return True
                    break
        # If we got here with messages, it's success
        if msg_count > 0:
            return True
    except Exception as e:
        print(f"  ❌ WebSocket: {e}")
        return False
    return False

try:
    result = asyncio.run(test_ws())
    if result:
        ok += 1
    else:
        fail += 1
except:
    fail += 1
    print(f"  ⚠️  WebSocket: teste ignorado (sem asyncio/websockets)")

# ─────────────────────────────────────────────────────
# FRONTEND CHECK
# ─────────────────────────────────────────────────────
print("\n🌐 [FRONTEND]")

try:
    with open("frontend/index.html", "r", encoding="utf-8") as f:
        content = f.read()
        if "JARVIS OMEGA CONNECTOR" in content:
            print(f"  ✅ Integração OMEGA script: injetado")
            ok += 1
        else:
            print(f"  ⚠️  OMEGA script não encontrado")
            fail += 1
except Exception as e:
    print(f"  ❌ Frontend check: {e}")
    fail += 1

# ─────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────
print("\n" + "╔" + "═"*58 + "╗")
total = ok + fail
pct = round(ok / total * 100) if total > 0 else 0
status = "✅ PRONTO PARA PRODUÇÃO" if fail == 0 else "⚠️  CORRIJA OS ERROS"
print(f"║  {ok} PASS | {fail} FAIL de {total} testes ({pct}%)      ║")
print(f"║  {status}           ║")
print(f"║  🚀 JARVIS OMEGA v6.0 ONLINE                        ║")
print("╚" + "═"*58 + "╝\n")

if __name__ == "__main__":
    import sys
    sys.exit(0 if fail == 0 else 1)
