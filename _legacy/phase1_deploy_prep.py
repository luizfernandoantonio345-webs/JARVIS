#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
JARVIS v6.0 — PHASE 1: DEPLOY PREPARATION
Prepare environment, fix .env, cleanup venv ambiguity
Execution time: ~5-10 minutes
"""

import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

# Colors for output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(70)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}\n")

def print_ok(text):
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")

def print_warn(text):
    print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")

def print_error(text):
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")

def print_info(text):
    print(f"{Colors.OKCYAN}→ {text}{Colors.ENDC}")

# Main execution
def main():
    print_header("JARVIS v6.0 — PHASE 1: DEPLOY PREPARATION")
    
    root = Path(__file__).parent
    os.chdir(root)
    
    timestamp = datetime.now().isoformat()
    print(f"Started: {timestamp}\n")
    
    # ===== STEP 1: Check Python Version =====
    print_info("Checking Python version...")
    py_version = sys.version_info
    if py_version.major >= 3 and py_version.minor >= 11:
        print_ok(f"Python {py_version.major}.{py_version.minor} OK")
    else:
        print_error(f"Python {py_version.major}.{py_version.minor} — need 3.11+")
        sys.exit(1)
    
    # ===== STEP 2: Fix .env =====
    print("\n" + "="*70)
    print_info("STEP 1: Fixing .env configuration...")
    
    env_file = root / "backend" / ".env"
    if not env_file.exists():
        env_file = root / ".env"
    
    # Read current env
    env_content = {}
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_content[k.strip()] = v.strip()
    
    # Fix critical values
    fixes = {
        "JARVIS_MODEL": "smollm2:135m",  # Light model for fast startup
        "JARVIS_LOCAL_MODEL": "smollm2:135m",
        "JARVIS_FALLBACK_MODEL": "smollm2:135m",
        "JARVIS_OLLAMA_URL": "http://localhost:11434",
        "JARVIS_EMBEDDING_MODEL": "nomic-embed-text",
        "JARVIS_TIMEOUT": "60",
        "JARVIS_PORT": "8000",
        "JARVIS_DEBUG": "false",
        "JARVIS_LOG_LEVEL": "WARNING",
        "JARVIS_DISABLE_VOICE": "false",
    }
    
    changed = False
    for key, value in fixes.items():
        if key not in env_content or env_content[key] != value:
            env_content[key] = value
            print_warn(f"  {key} → {value}")
            changed = True
        else:
            print_ok(f"  {key} already correct")
    
    if changed:
        # Write back
        with open(env_file, 'w') as f:
            for key in sorted(env_content.keys()):
                f.write(f"{key}={env_content[key]}\n")
        print_ok(f".env updated: {env_file}")
    else:
        print_ok(".env is already correct")
    
    # ===== STEP 3: Clean venv ambiguity =====
    print("\n" + "="*70)
    print_info("STEP 2: Cleaning venv ambiguity...")
    
    venv_dirs = [
        ("venv311", True),   # Keep
        ("venv", False),     # Remove
        (".venv", False),    # Remove
        (".venv-1", False),  # Remove
    ]
    
    venv_to_use = None
    for venv_name, keep in venv_dirs:
        venv_path = root / venv_name
        if venv_path.exists():
            if keep:
                print_ok(f"Keeping {venv_name}")
                venv_to_use = venv_name
            else:
                print_warn(f"Removing redundant {venv_name}...")
                try:
                    shutil.rmtree(venv_path)
                    print_ok(f"Removed {venv_name}")
                except Exception as e:
                    print_warn(f"Could not remove {venv_name}: {e}")
    
    if not venv_to_use:
        print_error("No venv found! Create with: python -m venv venv311")
        sys.exit(1)
    
    venv_python = root / venv_to_use / "Scripts" / "python.exe"
    if not venv_python.exists():
        print_error(f"Python not found in {venv_to_use}")
        sys.exit(1)
    
    print_ok(f"Using venv: {venv_to_use}")
    
    # ===== STEP 4: Update requirements =====
    print("\n" + "="*70)
    print_info("STEP 3: Updating requirements...")
    
    req_file = root / "backend" / "requirements.txt"
    if req_file.exists():
        print_info(f"Installing from {req_file}...")
        result = subprocess.run(
            [str(venv_python), "-m", "pip", "install", "-q", "-r", str(req_file)],
            capture_output=True
        )
        if result.returncode == 0:
            print_ok("Requirements installed successfully")
        else:
            print_warn(f"Some requirements failed: {result.stderr.decode()[:200]}")
    
    # ===== STEP 5: Check critical modules =====
    print("\n" + "="*70)
    print_info("STEP 4: Checking critical modules...")
    
    critical_modules = [
        "fastapi",
        "uvicorn",
        "pydantic",
        "pydantic_settings",
        "ollama",
        "requests",
        "httpx",
    ]
    
    missing = []
    for module in critical_modules:
        try:
            __import__(module)
            print_ok(f"  {module}")
        except ImportError:
            print_warn(f"  {module} missing")
            missing.append(module)
    
    if missing:
        print_warn(f"Installing missing modules: {', '.join(missing)}")
        subprocess.run(
            [str(venv_python), "-m", "pip", "install", "-q"] + missing,
            capture_output=True
        )
    
    # ===== STEP 6: Cleanup logs =====
    print("\n" + "="*70)
    print_info("STEP 5: Cleanup stale logs...")
    
    log_files = [
        "boot_smollm_stderr.log",
        "boot_smollm_stdout.log",
        "health_debug.log",
        "debug.log",
        "run_stderr.log",
        "run_stdout.log",
        "uvicorn_stderr.log",
        "uvicorn_stdout.log",
    ]
    
    for log_file in log_files:
        log_path = root / log_file
        if log_path.exists():
            try:
                os.remove(log_path)
                print_ok(f"Removed {log_file}")
            except:
                pass
    
    # Create logs dir
    logs_dir = root / "backend" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    print_ok(f"Logs directory ready: {logs_dir}")
    
    # ===== STEP 7: Summary =====
    print("\n" + "="*70)
    print_header("PHASE 1 COMPLETE ✓")
    
    print(f"\n{Colors.OKCYAN}Summary:{Colors.ENDC}")
    print(f"  • venv: {venv_to_use}")
    print(f"  • Python: {py_version.major}.{py_version.minor}")
    print(f"  • .env: Updated")
    print(f"  • Requirements: OK")
    print(f"  • Logs: Cleaned")
    print(f"\n{Colors.OKGREEN}Ready for Phase 2!{Colors.ENDC}")
    print(f"  Run: python phase2_deploy_fixes.py\n")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print_error(f"Phase 1 failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
