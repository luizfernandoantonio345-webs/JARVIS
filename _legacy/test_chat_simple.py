#!/usr/bin/env python
"""Test chat endpoint"""
import requests
import json

url = "http://localhost:8000/chat"
payload = {
    "message": "What is 2+2?",
    "session_id": "test_session"
}

try:
    r = requests.post(url, json=payload, timeout=30)
    print(f'Status: {r.status_code}')
    if r.status_code == 200:
        data = r.json()
        print(f'Response: {data.get("response", "NO RESPONSE")}')
        print('✅ Chat works!')
    else:
        print(f'Error: {r.text[:500]}')
except Exception as e:
    print(f'❌ Error: {e}')
