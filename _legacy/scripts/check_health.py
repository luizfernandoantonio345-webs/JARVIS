import requests
import json

try:
    r = requests.get('http://localhost:8000/health', timeout=20)
    print(r.status_code)
    print(json.dumps(r.json(), ensure_ascii=False))
except Exception as e:
    print('ERROR', e)
