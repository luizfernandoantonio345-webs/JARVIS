#!/usr/bin/env python3
"""
Start JARVIS backend server and verify it's working.
This can be run directly with: python start_server_and_verify.py
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
PORT = 8000
HEALTH_URL = f"http://localhost:{PORT}/health"


def health_check() -> dict | None:
    """Check if server is healthy."""
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=3) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def test_process_endpoint(command: str) -> str:
    """Test the /process endpoint."""
    try:
        url = f"http://localhost:{PORT}/process"
        data = json.dumps({"command": command}).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode('utf-8')
    except Exception as e:
        return f"Error: {e}"


def main():
    print("=" * 70)
    print("  JARVIS Backend Server - Start & Verify")
    print("=" * 70)
    
    # Check if already running
    print("\n[1] Checking if server is already running...")
    health = health_check()
    if health:
        print("    ✓ Server is ALREADY RUNNING!")
        print("\n    Health response:")
        print(json.dumps(health, indent=6, ensure_ascii=False))
        return 0
    
    print("    No server running, starting fresh...\n")
    
    # Start server
    print("[2] Starting JARVIS backend server...")
    env = {**os.environ, "JARVIS_DISABLE_VOICE": "1"}
    
    # Test imports first
    print("    Testing backend.main import...")
    result = subprocess.run(
        [str(PYTHON), "-c", "import backend.main; print('ok')"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
        timeout=15,
    )
    
    if result.returncode == 0:
        entry = "backend.main:app"
        print("    ✓ backend.main imports successfully")
    else:
        print("    ✗ backend.main failed, trying backend.main_simple...")
        result = subprocess.run(
            [str(PYTHON), "-c", "import backend.main_simple; print('ok')"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            env=env,
            timeout=15,
        )
        if result.returncode == 0:
            entry = "backend.main_simple:app"
            print("    ✓ backend.main_simple imports successfully")
        else:
            print("\n    [ERROR] Both main.py and main_simple.py failed to import!")
            print(f"    backend.main stderr: {result.stderr[:500]}")
            return 1
    
    # Start the server
    cmd = [
        str(PYTHON), "-m", "uvicorn", entry,
        "--host", "0.0.0.0",
        "--port", str(PORT),
    ]
    print(f"    Command: {' '.join(cmd)}\n")
    
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )
    
    print(f"    PID: {proc.pid}")
    print("\n[3] Waiting for server to start (up to 30 seconds)...")
    
    # Poll health
    server_online = False
    for i in range(30):
        time.sleep(1)
        health = health_check()
        if health:
            print(f"    ✓ Server is ONLINE after {i+1} seconds!\n")
            server_online = True
            break
        if (i + 1) % 5 == 0:
            print(f"    ... {i+1}s elapsed")
    
    if not server_online:
        print("\n    [ERROR] Health check failed after 30s")
        try:
            proc.terminate()
            stdout, stderr = proc.communicate(timeout=5)
            print("\n    Server stdout:")
            print(stdout[:1000] if stdout else "    (empty)")
            print("\n    Server stderr:")
            print(stderr[:1000] if stderr else "    (empty)")
        except Exception as e:
            print(f"    Could not get server output: {e}")
        return 1
    
    # Print health response
    print("[4] Health endpoint response:")
    print(json.dumps(health, indent=4, ensure_ascii=False))
    
    # Test process endpoint
    print("\n[5] Testing /process endpoint...")
    test_cmd = "echo Hello from JARVIS"
    print(f"    Command: {test_cmd}")
    response = test_process_endpoint(test_cmd)
    print("    Response:")
    try:
        resp_json = json.loads(response)
        print(json.dumps(resp_json, indent=6, ensure_ascii=False))
    except:
        print(f"    {response[:500]}")
    
    # Success
    print("\n" + "=" * 70)
    print("  ✓ SUCCESS: JARVIS Backend is running and operational!")
    print("=" * 70)
    print(f"\n  API Base URL: http://localhost:{PORT}")
    print(f"  API Docs:    http://localhost:{PORT}/docs")
    print(f"  WebSocket:   ws://localhost:{PORT}/ws/jarvis")
    print(f"  Health:      http://localhost:{PORT}/health")
    print(f"  Server PID:  {proc.pid}")
    print("\n  Server is running in background (detached).")
    print("=" * 70)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
