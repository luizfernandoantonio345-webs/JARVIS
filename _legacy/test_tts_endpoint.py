#!/usr/bin/env python3
import requests
import sys

try:
    r = requests.get('http://localhost:8000/tts?text=teste', timeout=5)
    print(f"Status: {r.status_code}")
    print(f"Content-Type: {r.headers.get('content-type')}")
    print(f"Size: {len(r.content)} bytes")
    if r.status_code != 200:
        print(f"Error: {r.text[:500]}")
except Exception as e:
    print(f"Exception: {e}")
    sys.exit(1)
