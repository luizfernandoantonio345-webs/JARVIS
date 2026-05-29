import requests
import time

for model in ['phi', 'phi:latest']:
    print('Testing', model)
    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': 'Responda em português.'},
            {'role': 'user', 'content': 'Diga apenas JARVIS online'}
        ],
        'stream': False,
        'keep_alive': '30m'
    }
    try:
        t0 = time.time()
        r = requests.post('http://192.168.0.106:11434/api/chat', json=payload, timeout=120)
        print('status', r.status_code, 'elapsed', time.time() - t0)
        print(r.text[:2000])
    except Exception as e:
        print('ERROR', e)
    print('-' * 60)
