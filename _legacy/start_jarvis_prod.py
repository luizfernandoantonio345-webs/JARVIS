#!/usr/bin/env python
"""
JARVIS v6.0 Production Startup Script
Starts the backend server on localhost:8000 with full diagnostics
"""

import subprocess
import time
import sys
import os

print("🚀 JARVIS v6.0 - Starting Backend Server")
print("=" * 60)

# Check Ollama
print("\n1. Checking Ollama...")
try:
    import requests
    response = requests.get("http://localhost:11434/api/tags", timeout=2)
    if response.status_code == 200:
        print("   ✓ Ollama is running on localhost:11434")
    else:
        print("   ⚠️  Ollama not responding (will use fallback LLM)")
except Exception as e:
    print(f"   ⚠️  Ollama check failed: {e}")
    print("   Start Ollama with: ollama serve")

# Check config
print("\n2. Loading configuration...")
try:
    from backend.config import get_config
    cfg = get_config()
    print(f"   ✓ Voice enabled: {cfg.voice_enabled}")
    print(f"   ✓ TTS voice: {cfg.tts_voice}")
    print(f"   ✓ Model: {cfg.model}")
except Exception as e:
    print(f"   ✗ Config failed: {e}")
    sys.exit(1)

# Check audio
print("\n3. Checking audio devices...")
try:
    import sounddevice as sd
    devices = sd.query_devices()
    input_count = sum(1 for d in devices if d["max_input_channels"] > 0)
    print(f"   ✓ Found {input_count} audio input device(s)")
except Exception as e:
    print(f"   ⚠️  Audio check failed: {e}")

# Start server
print("\n4. Starting server...")
print("   Command: uvicorn backend.main:app --host 0.0.0.0 --port 8000")
print("=" * 60)
print("\n🔗 JARVIS Backend running on http://localhost:8000")
print("📊 Metrics: http://localhost:8000/metrics")
print("🔌 WebSocket: ws://localhost:8000/ws/jarvis")
print("\nPress Ctrl+C to stop.\n")

os.system("uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload")
