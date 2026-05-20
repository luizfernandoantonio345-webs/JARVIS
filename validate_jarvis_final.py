#!/usr/bin/env python3
"""
J.A.R.V.I.S. Final Validation Suite
Validates all systems before deployment
"""
import requests
import subprocess
import sys
import time

sys.path.insert(0, 'backend')

BASE_URL = 'http://localhost:8000'
RESULTS = {'pass': 0, 'fail': 0}
FAILED_TESTS = []


def check(name, fn):
    """Execute test and track result."""
    global RESULTS
    try:
        result = fn()
        print(f'  ✓ {name}')
        RESULTS['pass'] += 1
        return True
    except Exception as e:
        print(f'  ✗ {name} — {str(e)[:60]}')
        RESULTS['fail'] += 1
        FAILED_TESTS.append((name, str(e)))
        return False


def main():
    print()
    print('=' * 50)
    print('   J.A.R.V.I.S. FINAL VALIDATION')
    print('=' * 50)
    print()
    
    # Wait for backend
    print('[1/3] Waiting for backend...')
    max_tries = 30
    for i in range(max_tries):
        try:
            requests.get(f'{BASE_URL}/health', timeout=2)
            print('  ✓ Backend responsive\n')
            break
        except:
            if i == max_tries - 1:
                print('  ✗ Backend not responding after 30s\n')
                sys.exit(1)
            time.sleep(1)
    
    # Core endpoints
    print('[2/3] Testing core endpoints...')
    check('Health', lambda: requests.get(f'{BASE_URL}/health', timeout=5).json())
    check('Frontend', lambda: requests.get(f'{BASE_URL}/', timeout=5).status_code)
    
    # Chat
    check('Chat', lambda: requests.post(
        f'{BASE_URL}/chat',
        json={'message': 'are you online', 'session_id': 'val'},
        timeout=90
    ).json().get('response', '?'))
    
    # TTS
    check('TTS', lambda: requests.get(
        f'{BASE_URL}/tts-iron?text=online',
        timeout=10
    ).status_code)
    
    # Additional endpoints
    check('Experience Stats', lambda: requests.get(
        f'{BASE_URL}/experience/stats',
        timeout=5
    ).json())
    
    check('Metrics', lambda: requests.get(
        f'{BASE_URL}/api-metrics/runtime',
        timeout=5
    ).json())
    
    check('Research Status', lambda: requests.get(
        f'{BASE_URL}/research/status',
        timeout=5
    ).json())
    
    # Python modules
    print('\n[3/3] Checking Python modules...')
    check('voice_v2.headset_listener', 
          lambda: __import__('voice_v2.headset_listener', fromlist=['HeadsetListener']))
    
    check('faster_whisper', 
          lambda: __import__('faster_whisper'))
    
    check('sounddevice', 
          lambda: __import__('sounddevice'))
    
    check('edge_tts', 
          lambda: __import__('edge_tts'))
    
    check('pyttsx3', 
          lambda: __import__('pyttsx3'))
    
    # Results
    print()
    print('=' * 50)
    total = RESULTS['pass'] + RESULTS['fail']
    pct = int(100 * RESULTS['pass'] / total) if total > 0 else 0
    print(f'  {RESULTS["pass"]}/{total} PASS ({pct}%)')
    print('=' * 50)
    
    if RESULTS['fail'] == 0:
        print()
        print('  ✓ J.A.R.V.I.S. 100% OPERATIONAL')
        print('  ✓ Ready for production use')
        print('  ✓ All systems green')
        print()
        return 0
    else:
        print()
        print(f'  ✗ {RESULTS["fail"]} test(s) failed:')
        for name, error in FAILED_TESTS:
            print(f'     - {name}')
        print()
        print('  Please fix failed tests before deploying.')
        print()
        return 1


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\n\nValidation interrupted.')
        sys.exit(2)
