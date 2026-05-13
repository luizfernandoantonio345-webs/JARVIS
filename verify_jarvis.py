#!/usr/bin/env python3
import json, os, subprocess, sys, time, urllib.error, urllib.request
from pathlib import Path

ROOT = Path("c:\\Users\\cibernetico\\JARVIS")
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
PORT = 8000
HEALTH_URL = f"http://localhost:{PORT}/health"

def health_check():
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=3) as r:
            return json.loads(r.read().decode())
    except: return None

def test_endpoint(cmd):
    try:
        url = f"http://localhost:{PORT}/process"
        data = json.dumps({"command": cmd}).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode('utf-8')
    except Exception as e:
        return f"Error: {e}"

print("="*70)
print("  JARVIS Backend Server - Start & Verify")
print("="*70)

print("\n[1] Checking if server is already running...")
h = health_check()
if h:
    print("    ✓ Server is ALREADY RUNNING!")
    print("\n    Health response:")
    print(json.dumps(h, indent=6, ensure_ascii=False))
    sys.exit(0)

print("    No server running, starting fresh...\n")

print("[2] Starting JARVIS backend server...")
env = {**os.environ, "JARVIS_DISABLE_VOICE": "1"}

# Test imports
print("    Testing backend.main import...")
r = subprocess.run([str(PYTHON), "-c", "import backend.main; print('ok')"], capture_output=True, text=True, cwd=str(ROOT), env=env, timeout=15)
if r.returncode == 0:
    entry = "backend.main:app"
    print("    ✓ backend.main imports successfully")
else:
    print("    ✗ Trying backend.main_simple...")
    r = subprocess.run([str(PYTHON), "-c", "import backend.main_simple; print('ok')"], capture_output=True, text=True, cwd=str(ROOT), env=env, timeout=15)
    if r.returncode == 0:
        entry = "backend.main_simple:app"
        print("    ✓ backend.main_simple imports successfully")
    else:
        print(f"\n    [ERROR] Import failed!\n    {r.stderr[:500]}")
        sys.exit(1)

cmd = [str(PYTHON), "-m", "uvicorn", entry, "--host", "0.0.0.0", "--port", str(PORT)]
print(f"    Command: {' '.join(cmd)}\n")

proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0)
print(f"    PID: {proc.pid}")

print("\n[3] Waiting for server to start (up to 30 seconds)...")
online = False
for i in range(30):
    time.sleep(1)
    h = health_check()
    if h:
        print(f"    ✓ Server ONLINE after {i+1}s!\n")
        online = True
        break
    if (i + 1) % 5 == 0:
        print(f"    ... {i+1}s elapsed")

if not online:
    print("\n    [ERROR] Health check failed after 30s")
    try:
        proc.terminate()
        stdout, stderr = proc.communicate(timeout=5)
        print(f"\n    stdout: {stdout[:500]}")
        print(f"    stderr: {stderr[:500]}")
    except Exception as e:
        print(f"    Error: {e}")
    sys.exit(1)

print("[4] Health endpoint response:")
print(json.dumps(h, indent=4, ensure_ascii=False))

print("\n[5] Testing /process endpoint...")
r = test_endpoint("echo Hello from JARVIS")
print("    Response:")
try:
    print(json.dumps(json.loads(r), indent=6, ensure_ascii=False))
except:
    print(f"    {r[:500]}")

print("\n" + "="*70)
print("  ✓ SUCCESS: JARVIS Backend is running!")
print("="*70)
print(f"\n  API Base: http://localhost:{PORT}")
print(f"  API Docs: http://localhost:{PORT}/docs")
print(f"  Health:   http://localhost:{PORT}/health")
print(f"  PID:      {proc.pid}")
print("\n="*70)
