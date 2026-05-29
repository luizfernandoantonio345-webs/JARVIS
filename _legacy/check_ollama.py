#!/usr/bin/env python
"""Check Ollama status"""
import requests
import json

try:
    r = requests.get('http://localhost:11434/api/tags', timeout=3)
    print(f'✓ Ollama responding: {r.status_code}')
    data = r.json()
    print(f'✓ Models loaded: {len(data["models"])}')
    for m in data['models']:
        print(f'  - {m["name"]}')
except Exception as e:
    print(f'✗ Ollama error: {e}')
