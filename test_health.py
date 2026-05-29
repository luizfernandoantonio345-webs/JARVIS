#!/usr/bin/env python
"""Quick server health check"""
import requests
import sys

try:
    print("Testing server health endpoint...")
    r = requests.get("http://localhost:8000/health", timeout=3)
    print(f"OK Status: {r.status_code}")
    print(f"OK Response: {r.json()}")
except Exception as e:
    print(f"FAILED: {e}")
    sys.exit(1)
