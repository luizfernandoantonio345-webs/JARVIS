#!/usr/bin/env python3
"""
Test full JARVIS stack: Ollama + Backend + Chat endpoint
"""
import requests
import json
import time
import sys

def test_ollama_tags():
    """Test Ollama /api/tags endpoint"""
    print("\n[1/4] Testing Ollama /api/tags...")
    try:
        r = requests.get('http://127.0.0.1:11434/api/tags', timeout=5)
        if r.status_code == 200:
            models = r.json().get('models', [])
            print(f"      OK - Found {len(models)} models")
            if models:
                print(f"      Model: {models[0].get('name')}")
            return True
        else:
            print(f"      FAIL - Status {r.status_code}")
            return False
    except Exception as e:
        print(f"      ERROR: {str(e)[:100]}")
        return False

def test_ollama_generate():
    """Test Ollama /api/generate endpoint"""
    print("\n[2/4] Testing Ollama /api/generate...")
    try:
        payload = {'model': 'tinyllama:latest', 'prompt': 'test', 'stream': False}
        t = time.time()
        r = requests.post('http://127.0.0.1:11434/api/generate', json=payload, timeout=120)
        elapsed = time.time() - t
        
        if r.status_code == 200:
            resp = r.json().get('response', '')[:50]
            print(f"      OK ({elapsed:.1f}s) - Response: {resp}")
            return True
        else:
            print(f"      FAIL - Status {r.status_code}")
            return False
    except requests.Timeout:
        print(f"      TIMEOUT after {time.time() - t:.1f}s")
        return False
    except Exception as e:
        print(f"      ERROR: {str(e)[:100]}")
        return False

def test_backend_health():
    """Test Backend /health endpoint"""
    print("\n[3/4] Testing Backend /health...")
    try:
        r = requests.get('http://127.0.0.1:8000/health', timeout=5)
        if r.status_code == 200:
            health = r.json()
            status = health.get('status', 'unknown')
            ollama_ok = health.get('components', {}).get('ollama', False)
            print(f"      OK - Status: {status}, Ollama: {ollama_ok}")
            return True
        else:
            print(f"      FAIL - Status {r.status_code}")
            return False
    except Exception as e:
        print(f"      ERROR: {str(e)[:100]}")
        return False

def test_backend_chat():
    """Test Backend /chat endpoint"""
    print("\n[4/4] Testing Backend /chat...")
    try:
        payload = {'message': 'hello', 'session_id': 'test'}
        t = time.time()
        r = requests.post('http://127.0.0.1:8000/chat', json=payload, timeout=60)
        elapsed = time.time() - t
        
        if r.status_code == 200:
            resp = r.json().get('message', '')[:50] or r.text[:50]
            print(f"      OK ({elapsed:.1f}s) - Response: {resp}")
            return True
        else:
            print(f"      FAIL - Status {r.status_code}")
            return False
    except requests.Timeout:
        print(f"      TIMEOUT after {time.time() - t:.1f}s")
        return False
    except Exception as e:
        print(f"      ERROR: {str(e)[:100]}")
        return False

if __name__ == '__main__':
    print("="*60)
    print("JARVIS FULL STACK TEST")
    print("="*60)
    
    results = []
    results.append(("Ollama /api/tags", test_ollama_tags()))
    results.append(("Ollama /api/generate", test_ollama_generate()))
    results.append(("Backend /health", test_backend_health()))
    results.append(("Backend /chat", test_backend_chat()))
    
    print("\n" + "="*60)
    print("SUMMARY:")
    print("="*60)
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")
    
    all_passed = all(p for _, p in results)
    print("\n" + ("="*60))
    if all_passed:
        print("✓ ALL TESTS PASSED!")
        sys.exit(0)
    else:
        print("✗ Some tests failed")
        sys.exit(1)
