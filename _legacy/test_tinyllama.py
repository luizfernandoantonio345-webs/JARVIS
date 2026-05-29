#!/usr/bin/env python
"""Test tinyllama model with limited memory"""
import requests
import json

url = "http://127.0.0.1:11434/api/chat"
payload = {
    "model": "tinyllama:latest",
    "messages": [
        {"role": "user", "content": "2+2=?"}
    ],
    "stream": False
}

try:
    r = requests.post(url, json=payload, timeout=30)
    print(f'Status: {r.status_code}')
    if r.status_code == 200:
        data = r.json()
        resp = data.get('message', {}).get('content', '')
        print(f'✓ tinyllama works!')
        print(f'Response: {resp[:100]}')
    else:
        print(f'✗ Error {r.status_code}: {r.text[:300]}')
except Exception as e:
    print(f'✗ Exception: {e}')
