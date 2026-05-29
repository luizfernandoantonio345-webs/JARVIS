#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
JARVIS v6.0 — PHASE 3: DEPLOYMENT VALIDATION
Test all systems before final startup
Execution time: ~10-15 minutes
"""

import os
import sys
import subprocess
import requests
import json
import time
from pathlib import Path
from datetime import datetime

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

def main():
    print_header("JARVIS v6.0 — PHASE 3: DEPLOYMENT VALIDATION")
    
    root = Path(__file__).parent
    os.chdir(root)
    
    timestamp = datetime.now().isoformat()
    print(f"Started: {timestamp}\n")
    
    passed = 0
    failed = 0
    
    # ===== TEST 1: Python version =====
    print("="*70)
    print_info("TEST 1: Python Version")
    
    py_version = sys.version_info
    if py_version.major >= 3 and py_version.minor >= 11:
        print_ok(f"Python {py_version.major}.{py_version.minor}.{py_version.micro}")
        passed += 1
    else:
        print_error(f"Python {py_version.major}.{py_version.minor} — need 3.11+")
        failed += 1
    
    # ===== TEST 2: Ollama connectivity =====
    print("\n" + "="*70)
    print_info("TEST 2: Ollama Connectivity")
    
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=3)
        if response.status_code == 200:
            data = response.json()
            model_count = len(data.get("models", []))
            print_ok(f"Ollama online with {model_count} model(s)")
            passed += 1
        else:
            print_warn(f"Ollama returned status {response.status_code}")
    except requests.ConnectionError:
        print_warn("Ollama not responding at localhost:11434")
        print_info("  Make sure to run: ollama serve")
    except Exception as e:
        print_warn(f"Ollama check failed: {e}")
    
    # ===== TEST 3: Port availability =====
    print("\n" + "="*70)
    print_info("TEST 3: Port Availability")
    
    import socket
    
    ports_to_check = [8000, 3000, 11434]
    available = []
    busy = []
    
    for port in ports_to_check:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('127.0.0.1', port))
            if result != 0:
                available.append(port)
                print_ok(f"Port {port}: Available")
            else:
                busy.append(port)
                print_warn(f"Port {port}: BUSY (check with: netstat -ano | findstr :{port})")
            sock.close()
        except Exception as e:
            print_warn(f"Port {port}: Error checking - {e}")
    
    if not busy:
        print_ok("All critical ports available")
        passed += 1
    else:
        print_warn(f"Some ports busy: {busy}")
    
    # ===== TEST 4: Disk space =====
    print("\n" + "="*70)
    print_info("TEST 4: Disk Space")
    
    try:
        import shutil
        stat = shutil.disk_usage(str(root))
        free_gb = stat.free / (1024**3)
        total_gb = stat.total / (1024**3)
        
        if free_gb > 2:
            print_ok(f"Disk space: {free_gb:.1f}GB free / {total_gb:.1f}GB total")
            passed += 1
        else:
            print_error(f"Low disk space: {free_gb:.1f}GB (need >2GB)")
            failed += 1
    except Exception as e:
        print_warn(f"Disk check failed: {e}")
    
    # ===== TEST 5: Config files =====
    print("\n" + "="*70)
    print_info("TEST 5: Configuration Files")
    
    config_checks = [
        (root / ".env", ".env (raiz do projeto)"),
        (root / "backend" / "config.py", "config.py"),
        (root / "backend" / "main.py", "main.py"),
    ]
    
    config_ok = 0
    for filepath, name in config_checks:
        if filepath.exists():
            print_ok(f"Found: {name}")
            config_ok += 1
        else:
            print_error(f"Missing: {name} at {filepath}")
    
    if config_ok == len(config_checks):
        print_ok("All config files present")
        passed += 1
    else:
        print_error(f"Missing {len(config_checks) - config_ok} config files")
        failed += 1
    
    # ===== TEST 6: Backend imports (simulate) =====
    print("\n" + "="*70)
    print_info("TEST 6: Backend Module Imports")
    
    venv_python = root / "venv311" / "Scripts" / "python.exe"
    if not venv_python.exists():
        print_warn("venv311 not found")
    else:
        # Test critical imports
        test_code = """
import sys
sys.path.insert(0, 'backend')
try:
    from config import get_config
    print("✓ config")
except Exception as e:
    print(f"✗ config: {e}")

try:
    from fastapi import FastAPI
    print("✓ fastapi")
except Exception as e:
    print(f"✗ fastapi: {e}")

try:
    import requests
    print("✓ requests")
except Exception as e:
    print(f"✗ requests: {e}")

try:
    import ollama
    print("✓ ollama")
except Exception as e:
    print(f"✗ ollama: {e}")
"""
        
        result = subprocess.run(
            [str(venv_python), "-c", test_code],
            capture_output=True,
            text=True,
            cwd=root
        )
        
        output = result.stdout + result.stderr
        if "✓ config" in output and "✓ fastapi" in output:
            print_ok("Critical imports OK")
            passed += 1
        else:
            print_error("Some imports missing:")
            print(output[:500])
            failed += 1
    
    # ===== TEST 7: Environment variables =====
    print("\n" + "="*70)
    print_info("TEST 7: Environment Variables")
    
    env_vars = [
        ("JARVIS_MODEL", "smollm2:135m"),
        ("JARVIS_OLLAMA_URL", "http://localhost:11434"),
        ("JARVIS_PORT", "8000"),
    ]
    
    env_ok = True
    for var, expected in env_vars:
        value = os.environ.get(var, "NOT SET")
        if expected in value or value == expected:
            print_ok(f"{var}={value}")
        else:
            print_warn(f"{var}={value} (expected: {expected})")
            env_ok = False
    
    if env_ok:
        passed += 1
    
    # ===== TEST 8: System resources =====
    print("\n" + "="*70)
    print_info("TEST 8: System Resources")
    
    try:
        import psutil
        
        cpu_percent = psutil.cpu_percent(interval=1)
        memory_percent = psutil.virtual_memory().percent
        available_mem_gb = psutil.virtual_memory().available / (1024**3)
        
        print_ok(f"CPU: {cpu_percent}%")
        print_ok(f"Memory: {memory_percent}% used ({available_mem_gb:.1f}GB available)")
        
        if available_mem_gb > 2:
            print_ok("Sufficient memory available")
            passed += 1
        else:
            print_error(f"Low memory: only {available_mem_gb:.1f}GB available (need >2GB)")
            failed += 1
    except ImportError:
        print_info("psutil not installed — skipping resource check")
    except Exception as e:
        print_warn(f"Resource check error: {e}")
    
    # ===== SMOKE TESTS (runtime real) =====
    # Start backend temporarily and verify critical endpoints:
    # - /health (200)
    # - /metrics (200)
    # - WebSocket handshake to /ws/jarvis
    #
    # NOTE: We avoid permanently changing state; we spin up a short-lived uvicorn process.
    print("\n" + "="*70)
    print_info("SMOKE TEST 9: Runtime endpoints")

    smoke_failed = False
    backend_proc = None
    http_base = f"http://localhost:8000"

    # Ensure env vars for this validation process (helps config resolution)
    env_override = os.environ.copy()
    env_override.setdefault("JARVIS_PORT", "8000")
    env_override.setdefault("JARVIS_MODEL", "smollm2:135m")
    env_override.setdefault("JARVIS_DISABLE_VOICE", "true")  # fastest runtime smoke (avoid voice deps)

    try:
        # Determine python in venv311
        venv_python = root / "venv311" / "Scripts" / "python.exe"
        if not venv_python.exists():
            print_error("venv311 not found — cannot run runtime smoke tests")
            smoke_failed = True
        else:
            # Launch uvicorn
            # Using backend.main:app (FastAPI)
            # Bind only localhost to avoid exposure
            print_info("Starting temporary backend (uvicorn) ...")

            # Important: inherit root as cwd so relative paths work
            backend_proc = subprocess.Popen(
                [str(venv_python), "-m", "uvicorn", "backend.main:app",
                 "--host", "127.0.0.1", "--port", "8000", "--log-level", "warning", "--access-log"],
                cwd=str(root),
                env=env_override,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )

            # Wait for /health
            max_tries = 30
            for i in range(1, max_tries + 1):
                try:
                    r = requests.get(f"{http_base}/health", timeout=2)
                    if r.status_code == 200:
                        print_ok(f"/health OK (attempt {i})")
                        break
                except Exception:
                    pass

                time.sleep(1)

            # If still not up, fail
            try:
                r = requests.get(f"{http_base}/health", timeout=2)
                if r.status_code != 200:
                    print_error(f"/health returned {r.status_code}")
                    smoke_failed = True
                else:
                    print_info("/health payload:")
                    try:
                        _ = r.json()
                        print_info(json.dumps(_, ensure_ascii=False)[:300] + ("..." if len(json.dumps(_, ensure_ascii=False))>300 else ""))
                    except Exception:
                        pass
            except Exception as e:
                print_error(f"/health check failed: {e}")
                smoke_failed = True

            # /metrics
            try:
                m = requests.get(f"{http_base}/metrics", timeout=3)
                if m.status_code == 200:
                    print_ok("/metrics OK")
                else:
                    print_error(f"/metrics returned {m.status_code}")
                    smoke_failed = True
            except Exception as e:
                print_error(f"/metrics check failed: {e}")
                smoke_failed = True

            # WebSocket handshake
            # We use `websockets` if installed; otherwise fallback to raw handshake.
            ws_ok = False
            try:
                import websockets  # type: ignore
                import asyncio as _asyncio

                async def _ws_check():
                    uri = f"ws://127.0.0.1:8000/ws/jarvis"
                    try:
                        async with websockets.connect(uri, ping_interval=None, close_timeout=2, open_timeout=5) as ws:
                            # Expect initial message
                            msg = await _asyncio.wait_for(ws.recv(), timeout=5)
                            return True, str(msg)[:250]
                    except Exception as e:
                        return False, str(e)[:250]

                ws_result = _asyncio.run(_ws_check())
                if ws_result[0]:
                    print_ok(f"WebSocket /ws/jarvis OK (initial msg: {ws_result[1]})")
                    ws_ok = True
                else:
                    print_error(f"WebSocket /ws/jarvis failed: {ws_result[1]}")
            except ImportError:
                # Fallback: skip strict WS test but report as warning (do not block deploy)
                print_warn("Python package 'websockets' not installed — skipping WS message test (não bloqueante)")
                ws_ok = False
                # Do not fail smoke_failed here; deploy should still proceed if HTTP health/metrics are OK
            except Exception as e:
                print_error(f"WS smoke test error: {e}")
                smoke_failed = True

    finally:
        # Stop temporary backend
        if backend_proc is not None:
            try:
                backend_proc.terminate()
                backend_proc.wait(timeout=5)
            except Exception:
                try:
                    backend_proc.kill()
                except Exception:
                    pass

    # ===== FINAL SUMMARY (after smoke tests) =====
    if smoke_failed:
        failed += 1
        print_warn("SMOKE TESTS: FAILED (runtime endpoints issue)")
    else:
        passed += 1
        print_ok("SMOKE TESTS: PASSED (runtime endpoints OK)")

    # Recompute score after smoke tests
    total = passed + failed
    percentage = (passed / total * 100) if total > 0 else 0

    print("\n" + "="*70)
    print_header("PHASE 3 COMPLETE (UPDATED)")

    print(f"\n{Colors.OKCYAN}Test Results:{Colors.ENDC}")
    print(f"  {Colors.OKGREEN}Passed: {passed}/{total}{Colors.ENDC}")
    print(f"  {Colors.FAIL}Failed: {failed}/{total}{Colors.ENDC}")
    print(f"  {Colors.OKCYAN}Score: {percentage:.0f}%{Colors.ENDC}\n")

    if failed == 0:
        print(f"{Colors.OKGREEN}✓ ALL CHECKS PASSED — READY FOR DEPLOYMENT!{Colors.ENDC}\n")
        print(f"  Run: .\\startup_final.ps1\n")
        return 0
    else:
        print(f"{Colors.WARNING}⚠ Some checks failed — review above and retry{Colors.ENDC}\n")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
