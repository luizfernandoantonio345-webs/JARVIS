import requests
import time

try:
    print('Testando chat com phi via PC2...')
    t0 = time.time()
    r = requests.post('http://localhost:8000/chat', json={'message': 'diga apenas: JARVIS online', 'session_id': 'test'}, timeout=180)
    elapsed = time.time() - t0
    if r.status_code == 200:
        resp = r.json().get('response', '')
        print(f'PASSOU ({elapsed:.1f}s): {resp}')
    else:
        print(f'FALHOU ({r.status_code}): {r.text}')
except Exception as e:
    print('ERROR', e)
