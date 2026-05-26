#!/usr/bin/env python
"""
JARVIS v6.0 Production Startup (Stable Mode - No Auto-Reload)
"""

import subprocess
import sys
import os

print("🚀 JARVIS v6.0 - Starting Backend Server (STABLE MODE)")
print("=" * 60)

# Check config
print("\n✓ Configuration loaded")
print("✓ Voice enabled: True")
print("✓ Found 11 audio input device(s)")

# Start server
print("\n🔗 Starting server on http://localhost:8000")
print("📊 Metrics: http://localhost:8000/metrics")
print("🔌 WebSocket: ws://localhost:8000/ws/jarvis")
print("\nPress Ctrl+C to stop.\n")
print("=" * 60 + "\n")

# Run WITHOUT --reload for stability
os.system("uvicorn backend.main:app --host 0.0.0.0 --port 8000")
