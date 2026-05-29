#!/usr/bin/env python
"""Quick health check test"""
import requests
import json
import sys

print("🔍 Testing JARVIS Health Endpoint...")
print("=" * 60)

try:
    print("\n1️⃣ Connecting to http://localhost:8000/health...")
    response = requests.get("http://localhost:8000/health", timeout=10)
    
    print(f"   Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n✅ SUCCESS! Response:")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        
        # Check components
        if "components" in data:
            print(f"\n📊 Components Status:")
            for comp, status in data["components"].items():
                symbol = "✅" if status else "❌"
                print(f"   {symbol} {comp}: {status}")
    else:
        print(f"\n❌ Unexpected status code: {response.status_code}")
        print(f"Response: {response.text[:200]}")
        sys.exit(1)
        
except requests.exceptions.Timeout:
    print("\n❌ TIMEOUT: Server didn't respond within 10 seconds")
    print("   → Check if backend is running (python start_server_stable.py)")
    sys.exit(1)
except requests.exceptions.ConnectionError as e:
    print(f"\n❌ CONNECTION ERROR: {e}")
    print("   → Check if backend is running on port 8000")
    sys.exit(1)
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("✅ Health check PASSED!")
