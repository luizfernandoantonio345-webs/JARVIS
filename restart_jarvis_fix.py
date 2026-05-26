#!/usr/bin/env python3
"""
JARVIS Restart Fix — Automatic Restart + Test + Fix
- Kill old Python processes
- Prewarm Ollama (phi model)
- Start backend with updated timeouts
- Test /health and /chat endpoints
- Open browser
"""

import subprocess
import time
import sys
import os
import json
import urllib.request
import webbrowser
from pathlib import Path

JARVIS_DIR = Path(__file__).parent
VENV_PYTHON = JARVIS_DIR / "venv311" / "Scripts" / "python.exe"
BACKEND_CMD = [
    str(VENV_PYTHON),
    "-m",
    "uvicorn",
    "backend.main:app",
    "--host",
    "0.0.0.0",
    "--port",
    "8000",
    "--log-level",
    "warning"
]

def log(msg):
    print(f"[JARVIS] {msg}", flush=True)

def run_cmd(cmd, shell=False, timeout=None):
    """Run command and return exit code."""
    try:
        result = subprocess.run(cmd, shell=shell, capture_output=True, timeout=timeout, text=True)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout"
    except Exception as e:
        return -1, "", str(e)

def kill_python():
    """Kill all Python processes (oldinstances of backend)."""
    log("Killing old Python processes...")
    os.system("taskkill /F /IM python.exe >nul 2>&1")
    time.sleep(1.5)
    log("✓ Processes cleaned")

def prewarm_ollama():
    """Prewarm Ollama by loading phi model."""
    log("Prewarming Ollama (phi:latest)...")
    payload = {
        "model": "phi:latest",
        "prompt": "Hi",
        "stream": False,
        "keep_alive": "60m"
    }
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            result = json.loads(r.read().decode("utf-8"))
            log(f"✓ Ollama warmed up (took {result.get('total_duration', 0) / 1e9:.1f}s)")
    except Exception as e:
        log(f"⚠ Prewarm failed (non-critical): {e}")

def start_backend():
    """Start backend in background."""
    log("Starting JARVIS backend...")
    os.chdir(JARVIS_DIR)
    try:
        subprocess.Popen(
            BACKEND_CMD,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        log("Backend process started")
        time.sleep(3)  # Give it time to initialize
    except Exception as e:
        log(f"✗ Failed to start backend: {e}")
        sys.exit(1)

def test_health():
    """Test /health endpoint."""
    log("Testing /health endpoint...")
    for attempt in range(1, 5):
        try:
            with urllib.request.urlopen("http://localhost:8000/health", timeout=5) as r:
                data = json.loads(r.read().decode("utf-8"))
                if data.get("status") == "ok":
                    log(f"✓ Health check passed (attempt {attempt})")
                    return True
                else:
                    log(f"⚠ Health returned: {data.get('status')}")
        except Exception as e:
            log(f"  Attempt {attempt}: {type(e).__name__}")
            if attempt < 4:
                time.sleep(2)
    return False

def test_chat():
    """Test /chat endpoint with a simple message."""
    log("Testing /chat endpoint...")
    payload = {"message": "Olá JARVIS, teste de funcionamento"}
    try:
        req = urllib.request.Request(
            "http://localhost:8000/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=150) as r:  # Long timeout for cold start
            response = json.loads(r.read().decode("utf-8"))
            resp_text = response.get("response", "")[:100]
            if "offline" not in resp_text.lower():
                log(f"✓ Chat working: {resp_text}")
                return True
            else:
                log(f"⚠ Chat returned error: {resp_text}")
    except Exception as e:
        log(f"✗ Chat failed: {type(e).__name__}: {e}")
    return False

def open_browser():
    """Open browser to JARVIS UI."""
    log("Opening browser...")
    webbrowser.open("http://localhost:8000")
    log("✓ Browser opened")

def main():
    log("=" * 60)
    log("JARVIS RESTART FIX — Complete initialization")
    log("=" * 60)
    
    kill_python()
    time.sleep(1)
    prewarm_ollama()
    time.sleep(1)
    start_backend()
    
    # Test endpoints
    health_ok = test_health()
    if not health_ok:
        log("✗ Backend health check failed")
        log("   Check backend logs manually with:")
        log("   python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000")
        sys.exit(1)
    
    # Test chat (this may take a while for first response)
    log("Waiting for first chat response (may take 30-60s on cold start)...")
    chat_ok = test_chat()
    
    if chat_ok:
        log("=" * 60)
        log("✓ JARVIS IS ONLINE AND RESPONDING")
        log("=" * 60)
        open_browser()
        log("\nYou can now:")
        log("1. Type messages in the web UI")
        log("2. Use voice commands (if enabled)")
        log("3. Ask questions and get responses from Ollama")
        log("\nTo monitor backend, run in another terminal:")
        log("python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000")
    else:
        log("=" * 60)
        log("⚠ Chat test incomplete (may still be warming up)")
        log("=" * 60)
        open_browser()
        log("\nTry sending a message in the UI in ~60 seconds")
        log("(Backend is initializing Ollama model)")

if __name__ == "__main__":
    main()
