#!/usr/bin/env python
"""Test Ollama /api/chat endpoint directly"""
import requests
import json

url = "http://127.0.0.1:11434/api/chat"
payload = {
    "model": "phi:latest",
    "messages": [
        {"role": "system", "content": "Você é JARVIS. Responda em português."},
        {"role": "user", "content": "O que é 2+2?"}
    ],
    "stream": False
}

try:
    r = requests.post(url, json=payload, timeout=30)
    print(f'Status: {r.status_code}')
    if r.status_code == 200:
        print('✓ Ollama /api/chat works!')
        print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    else:
        print(f'✗ Error: {r.status_code}')
        print(r.text[:500])
except Exception as e:
    print(f'✗ Error: {e}')
