#!/usr/bin/env python3
"""
JARVIS Launcher — run this directly with the venv python:
  .venv\Scripts\python.exe launch_jarvis.py

- Checks if already running
- Starts uvicorn in the background (JARVIS_DISABLE_VOICE=1)
- Polls health for up to 30 seconds
- Prints the full health response
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
LOGS_DIR = ROOT / "backend" / "logs"
LOG_FILE = LOGS_DIR / "uvicorn.log"
PORT = 8000
HEALTH_URL = f"http://localhost:{PORT}/health"


def _health() -> dict | None:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=3) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def main():
    print("=" * 60)
    print("  JARVIS AI Backend Launcher")
    print("=" * 60)

    # ── 1. Check if already running ──────────────────────────────
    h = _health()
    if h:
        print(f"\n[✓] JARVIS is already running!\n")
        print(json.dumps(h, indent=2, ensure_ascii=False))
        print(f"\n  API:  http://localhost:{PORT}")
        print(f"  Docs: http://localhost:{PORT}/docs")
        print(f"  WS:   ws://localhost:{PORT}/ws/jarvis")
        return

    # ── 2. Ensure logs dir ────────────────────────────────────────
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\n[+] Logs → {LOG_FILE}")

    # ── 3. Determine entry point ──────────────────────────────────
    env = {**os.environ, "JARVIS_DISABLE_VOICE": "1"}

    def _test_import(module: str) -> bool:
        r = subprocess.run(
            [str(PYTHON), "-c", f"import {module}; print('ok')"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            env=env,
            timeout=15,
        )
        return r.returncode == 0

    print("\n[+] Testing backend.main import...")
    if _test_import("backend.main"):
        entry = "backend.main:app"
        print("    ✓ backend.main OK — using full backend")
    else:
        print("    ✗ backend.main failed — trying backend.main_simple")
        if _test_import("backend.main_simple"):
            entry = "backend.main_simple:app"
            print("    ✓ backend.main_simple OK — using simple backend")
        else:
            print("\n[ERROR] Both main.py and main_simple.py failed to import!")
            print("        Run: .venv\\Scripts\\pip.exe install -r backend\\requirements.txt")
            sys.exit(1)

    # ── 4. Start server ───────────────────────────────────────────
    cmd = [
        str(PYTHON), "-m", "uvicorn", entry,
        "--host", "0.0.0.0",
        "--port", str(PORT),
    ]
    print(f"\n[+] Starting: {' '.join(cmd)}")

    with open(LOG_FILE, "w") as log_f:
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            env=env,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )

    print(f"    PID: {proc.pid}")

    # ── 5. Poll health ────────────────────────────────────────────
    print("\n[+] Waiting for JARVIS to come online (up to 30s)...")
    for i in range(30):
        time.sleep(1)
        h = _health()
        if h:
            print(f"\n[✓] JARVIS is ONLINE after {i+1}s!\n")
            print(json.dumps(h, indent=2, ensure_ascii=False))
            print(f"\n  API:  http://localhost:{PORT}")
            print(f"  Docs: http://localhost:{PORT}/docs")
            print(f"  WS:   ws://localhost:{PORT}/ws/jarvis")
            print(f"  Log:  {LOG_FILE}")
            return
        if (i + 1) % 5 == 0:
            print(f"    ... {i+1}s elapsed")

    # ── 6. Failure: dump log ──────────────────────────────────────
    print(f"\n[ERROR] Health check failed after 30s. Last log lines:\n")
    try:
        with open(LOG_FILE) as f:
            lines = f.readlines()
        for line in lines[-40:]:
            print("  ", line.rstrip())
    except Exception as e:
        print(f"  Could not read log: {e}")
    print(f"\n  Full log: {LOG_FILE}")
    proc.terminate()
    sys.exit(1)


if __name__ == "__main__":
    main()
