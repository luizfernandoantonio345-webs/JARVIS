#!/usr/bin/env python
"""Test minimal health endpoint"""
import requests
import json
import sys

print("Testing minimal health endpoint...")
try:
    r = requests.get("http://localhost:8000/health", timeout=5)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        print(json.dumps(r.json(), indent=2))
        print("\n✅ SUCCESS!")
    else:
        print(f"❌ Unexpected status")
        print(r.text)
        sys.exit(1)
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
