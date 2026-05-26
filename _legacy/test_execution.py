import subprocess
import sys
import os
from pathlib import Path

# Direct execution test
print("Testing Python execution...")
print(f"Python version: {sys.version}")
print(f"Python executable: {sys.executable}")

# Try to run the verification script
jarvis_path = Path("c:\\Users\\cibernetico\\JARVIS")
os.chdir(jarvis_path)

print(f"\nChanging to: {jarvis_path}")
print(f"Current directory: {os.getcwd()}")
print(f"Files in directory: {len(list(jarvis_path.iterdir()))} items")

# Try to import and start verification
sys.path.insert(0, str(jarvis_path))

import json
import time
import urllib.error
import urllib.request

PYTHON_VENV = jarvis_path / ".venv" / "Scripts" / "python.exe"
PORT = 8000

print(f"\nVenv Python exists: {PYTHON_VENV.exists()}")
print(f"Venv Python path: {PYTHON_VENV}")

# Check if already running
def health_check():
    try:
        with urllib.request.urlopen(f"http://localhost:{PORT}/health", timeout=3) as r:
            return json.loads(r.read().decode())
    except:
        return None

print(f"\nHealth check result: {health_check()}")
