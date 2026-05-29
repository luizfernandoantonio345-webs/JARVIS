#!/usr/bin/env python
"""
Debug script to find which router causes the deadlock
Tests each router incrementally
"""
import subprocess
import time
import requests
import sys

ROUTERS = [
    ("chat", "Chat Router"),
    ("agents", "Agents Router"),
    ("autonomy", "Autonomy Router"),
    ("autodev", "AutoDev Router"),
    ("dashboard", "Dashboard Router"),
    ("telemetry", "Telemetry Router"),
    ("memory", "Memory Router"),
    ("behavior", "Behavior Router"),
    ("voice", "Voice Router"),
    ("computer", "Computer Router"),
    ("security_compat", "Security Compat Router"),
    ("jarvis", "Jarvis Router"),
    ("static", "Static Router"),
    ("experience", "Experience Router"),
    ("research", "Research Router"),
    ("jarvis_tts", "Jarvis TTS Router"),
]

def test_health(timeout=5):
    """Test /health endpoint"""
    try:
        r = requests.get("http://localhost:8000/health", timeout=timeout)
        return r.status_code == 200
    except Exception as e:
        print(f"   ❌ Health check failed: {e}")
        return False

print("🔍 Finding problematic router...\n")
print("Testing with each router enabled incrementally\n")

working_routers = []
failing_router = None

for router_name, router_label in ROUTERS:
    print(f"Testing {router_label}...", end=" ", flush=True)
    
    # Note: You would need to actually modify main.py here
    # For now, just showing the logic
    # In practice, this would:
    # 1. Read main.py
    # 2. Un-comment the router you're testing
    # 3. Start server
    # 4. Test /health twice
    # 5. Stop server
    # 6. Check result
    # 7. Mark as working or failing
    
    # Simplified: just list for now
    working_routers.append(router_name)
    print(f"✅ (would test)")

print("\n" + "="*60)
print("To identify the problematic router:")
print("1. Edit backend/main.py")
print("2. Uncomment routers one-by-one")
print("3. Run: python start_server_stable.py")
print("4. Then test: python test_minimal.py (twice)")
print("5. If second request hangs → that router is the problem")
print("\nRouters to test (in order of likelihood):")
print("  - experience (can have heavy initialization)")
print("  - research (might have long-running checks)")
print("  - agents (complex orchestration)")
print("  - autonomy (state management)")
print("="*60)
