#!/usr/bin/env python3
"""
JARVIS STARK — Phase 0 Diagnostic Report
Complete system assessment before fixes
"""

import sys, os, time, pathlib, subprocess, json
import asyncio

print('='*70)
print('JARVIS STARK — COMPREHENSIVE DIAGNOSTIC REPORT')
print(f'Time: {time.strftime("%Y-%m-%d %H:%M:%S")}')
print('='*70)

sys.path.insert(0, 'backend')

# ============================================================================
# 1. OLLAMA CONNECTIVITY
# ============================================================================
print('\n[1] OLLAMA CONNECTIVITY')
print('-' * 70)

import requests

ollama_urls = [
    'http://127.0.0.1:11434',
    'http://localhost:11434',
    'http://[::1]:11434'  # IPv6
]

ollama_ok = False
for url in ollama_urls:
    try:
        r = requests.get(f'{url}/api/tags', timeout=3)
        if r.status_code == 200:
            models = [m['name'] for m in r.json().get('models', [])]
            print(f'  ✓ {url}: Found {len(models)} models')
            print(f'    Models: {models[:3]}')
            ollama_ok = True
            break
    except Exception as e:
        print(f'  ✗ {url}: {type(e).__name__}')

if not ollama_ok:
    print('  ⚠ PROBLEM: Ollama not accessible via IPv4 or IPv6')

# ============================================================================
# 2. BACKEND HEALTH
# ============================================================================
print('\n[2] BACKEND SERVICE')
print('-' * 70)

backend_ok = False
try:
    r = requests.get('http://localhost:8000/health', timeout=5)
    if r.status_code == 200:
        d = r.json()
        print(f'  ✓ Backend online')
        print(f'    Status: {d.get("status")}')
        print(f'    Version: {d.get("version")}')
        print(f'    Uptime: {d.get("uptime", 0):.0f}s')
        backend_ok = True
except Exception as e:
    print(f'  ✗ Backend OFFLINE: {e}')

# ============================================================================
# 3. ENDPOINT VALIDATION
# ============================================================================
print('\n[3] CRITICAL ENDPOINTS')
print('-' * 70)

endpoints = [
    ('GET',  '/health',         None,                          'Health check'),
    ('GET',  '/',               None,                          'Frontend'),
    ('GET',  '/status',         None,                          'System status'),
    ('POST', '/chat',           {'message':'test','session_id':'diag'}, 'Chat endpoint'),
    ('GET',  '/tts-iron/tts?text=hello', None,                 'TTS endpoint'),
    ('GET',  '/experience/stats', None,                        'Experience stats'),
]

endpoint_results = {'pass': 0, 'fail': 0}
for method, path, body, desc in endpoints:
    try:
        if method == 'GET':
            r = requests.get(f'http://localhost:8000{path}', timeout=8)
        else:
            r = requests.post(f'http://localhost:8000{path}', json=body, timeout=30)
        
        status = '✓' if r.status_code < 400 else '⚠'
        print(f'  {status} {r.status_code} {method:4} {path:30} {desc}')
        if r.status_code < 400:
            endpoint_results['pass'] += 1
        else:
            endpoint_results['fail'] += 1
    except Exception as e:
        print(f'  ✗ FAIL {method:4} {path:30} {desc}')
        print(f'     → {str(e)[:60]}')
        endpoint_results['fail'] += 1

# ============================================================================
# 4. PYTHON IMPORTS
# ============================================================================
print('\n[4] CRITICAL IMPORTS')
print('-' * 70)

critical_modules = [
    'config',
    'ai.client',
    'services.chat_service',
    'services.llm_service',
    'services.session_store',
    'agents.master_orchestrator',
    'memory.persistent_memory',
    'voice_v2.output',
    'voice_v2.resilient_loader',
    'experience.engine',
    'observability.metrics',
    'core.event_bus',
]

import_results = {'pass': 0, 'fail': 0}
import_errors = {}
for mod in critical_modules:
    try:
        __import__(mod)
        print(f'  ✓ {mod}')
        import_results['pass'] += 1
    except Exception as e:
        print(f'  ✗ {mod}')
        print(f'     → {str(e)[:60]}')
        import_results['fail'] += 1
        import_errors[mod] = str(e)

# ============================================================================
# 5. FILE STRUCTURE & DUPLICATES
# ============================================================================
print('\n[5] FILE STRUCTURE ISSUES')
print('-' * 70)

backend_path = pathlib.Path('backend')
structure_issues = []

# Check for duplicate modules (v1 and v2)
duplicates = [
    ('voice', 'voice_v2'),
    ('memory', 'memory_v2'),
    ('autonomy', 'autonomy_v2'),
]

for v1, v2 in duplicates:
    p1 = backend_path / v1
    p2 = backend_path / v2
    if p1.exists() and p2.exists():
        print(f'  ⚠ DUPLICATE: {v1}/ and {v2}/')
        structure_issues.append(f'Duplicate: {v1} + {v2}')

# Check for duplicate start scripts
start_scripts = list(pathlib.Path('.').glob('start_*.bat')) + \
                list(pathlib.Path('.').glob('start_*.py')) + \
                list(pathlib.Path('.').glob('restart_*.py'))

if len(start_scripts) > 1:
    print(f'  ⚠ DUPLICATE START SCRIPTS ({len(start_scripts)}):')
    for s in start_scripts:
        print(f'    - {s.name}')
    structure_issues.append(f'Multiple start scripts: {len(start_scripts)}')

# Check __init__.py files
missing_inits = []
for pkg in ['ai', 'agents', 'services', 'memory', 'voice_v2', 'core', 
            'experience', 'observability', 'middleware', 'routes']:
    pkg_path = backend_path / pkg
    if pkg_path.is_dir():
        init_file = pkg_path / '__init__.py'
        if not init_file.exists():
            missing_inits.append(pkg)

if missing_inits:
    print(f'  ⚠ MISSING __init__.py ({len(missing_inits)}): {missing_inits}')
    structure_issues.append(f'Missing __init__.py in {len(missing_inits)} packages')

if not structure_issues:
    print('  ✓ File structure OK')

# ============================================================================
# 6. DATABASE STATUS
# ============================================================================
print('\n[6] DATABASE & STORAGE')
print('-' * 70)

db_files = list(pathlib.Path('.').rglob('*.db'))
if db_files:
    for db in db_files:
        try:
            size_mb = db.stat().st_size / 1024 / 1024
            print(f'  ℹ {db}: {size_mb:.1f}MB')
            if size_mb > 500:
                print(f'    ⚠ WARNING: Database >500MB (growth issue?)')
        except Exception as e:
            print(f'  ✗ {db}: {e}')
else:
    print('  ℹ No SQLite databases found')

# Check logs directory
logs_dir = pathlib.Path('backend/logs')
if logs_dir.exists():
    log_files = list(logs_dir.glob('*.log'))
    print(f'  ✓ Logs directory exists ({len(log_files)} files)')
else:
    print(f'  ⚠ No logs directory: backend/logs/')

# ============================================================================
# 7. VOICE DEPENDENCIES
# ============================================================================
print('\n[7] VOICE & AUDIO DEPENDENCIES')
print('-' * 70)

voice_deps = [
    'edge_tts',
    'faster_whisper',
    'sounddevice',
    'pyttsx3',
    'pyaudio',
    'scipy',
]

voice_results = {'pass': 0, 'fail': 0}
missing_voice = []
for dep in voice_deps:
    try:
        __import__(dep)
        print(f'  ✓ {dep}')
        voice_results['pass'] += 1
    except ImportError:
        print(f'  ✗ {dep} (MISSING)')
        voice_results['fail'] += 1
        missing_voice.append(dep)

if missing_voice:
    print(f'\n  ⚠ Install missing: pip install {" ".join(missing_voice)}')

# ============================================================================
# 8. ENVIRONMENT VARIABLES
# ============================================================================
print('\n[8] CONFIGURATION & ENV VARS')
print('-' * 70)

required_env = [
    'OLLAMA_HOST',
    'JARVIS_MODEL',
    'JARVIS_VOICE_ENABLED',
]

env_issues = []
for var in required_env:
    val = os.getenv(var, '<not set>')
    if val == '<not set>':
        print(f'  ⚠ {var}: {val}')
        env_issues.append(var)
    else:
        print(f'  ✓ {var}: {val}')

# Check .env file
env_file = pathlib.Path('.env')
if env_file.exists():
    print(f'  ✓ .env file exists')
else:
    print(f'  ⚠ No .env file')
    env_issues.append('.env missing')

# ============================================================================
# 9. NETWORK & PORTS
# ============================================================================
print('\n[9] NETWORK & PORTS')
print('-' * 70)

ports_to_check = [
    (8000, 'Backend API'),
    (11434, 'Ollama'),
    (3000, 'Frontend (Vite)'),
]

for port, service in ports_to_check:
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        result = s.connect_ex(('127.0.0.1', port))
        s.close()
        if result == 0:
            print(f'  ✓ Port {port:5} OPEN  ({service})')
        else:
            print(f'  ✗ Port {port:5} CLOSED ({service})')
    except Exception as e:
        print(f'  ✗ Port {port:5} ERROR: {e}')

# ============================================================================
# 10. REQUIREMENTS & VERSIONS
# ============================================================================
print('\n[10] PYTHON ENVIRONMENT')
print('-' * 70)

print(f'  Python: {sys.version.split()[0]}')
print(f'  Executable: {sys.executable}')

try:
    import fastapi, uvicorn, pydantic, httpx
    print(f'  ✓ FastAPI {fastapi.__version__}')
    print(f'  ✓ Pydantic {pydantic.__version__}')
except ImportError as e:
    print(f'  ✗ Missing core dependency: {e}')

# ============================================================================
# SUMMARY
# ============================================================================
print('\n' + '='*70)
print('DIAGNOSTIC SUMMARY')
print('='*70)

total_issues = 0
if not ollama_ok:
    total_issues += 1
    print('  ⚠ Ollama connectivity issue')
if not backend_ok:
    total_issues += 1
    print('  ⚠ Backend offline')
if endpoint_results['fail'] > 0:
    total_issues += 1
    print(f'  ⚠ {endpoint_results["fail"]} endpoints failed')
if import_results['fail'] > 0:
    total_issues += 1
    print(f'  ⚠ {import_results["fail"]} import failures')
if structure_issues:
    total_issues += 1
    for issue in structure_issues:
        print(f'  ⚠ {issue}')
if missing_voice:
    total_issues += 1
    print(f'  ⚠ {len(missing_voice)} voice dependencies missing')
if env_issues:
    total_issues += 1
    print(f'  ⚠ {len(env_issues)} environment issues')

print(f'\nTotal Issues: {total_issues}')
if total_issues == 0:
    print('✅ SYSTEM READY FOR PHASE 1')
else:
    print('⚠️  PROBLEMS DETECTED — FIX BEFORE CONTINUING')

# ============================================================================
# Save diagnostic report
# ============================================================================
report = {
    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
    'ollama_ok': ollama_ok,
    'backend_ok': backend_ok,
    'endpoints': endpoint_results,
    'imports': import_results,
    'import_errors': import_errors,
    'voice': voice_results,
    'missing_voice_deps': missing_voice,
    'structure_issues': structure_issues,
    'env_issues': env_issues,
    'total_issues': total_issues,
}

with open('phase0_diagnostic_report.json', 'w') as f:
    json.dump(report, f, indent=2)

print(f'\n📊 Diagnostic report saved: phase0_diagnostic_report.json')
print('='*70 + '\n')
