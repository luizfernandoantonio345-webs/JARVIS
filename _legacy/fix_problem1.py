#!/usr/bin/env python3
"""
PROBLEM 1: Remove duplicate start scripts
Keep ONLY start_jarvis.bat, move rest to _legacy/
"""

import pathlib
import shutil
import time

print('='*70)
print('PROBLEM 1: REMOVING DUPLICATE START SCRIPTS')
print(f'Time: {time.strftime("%Y-%m-%d %H:%M:%S")}')
print('='*70)

root = pathlib.Path('.')
legacy = root / '_legacy'
legacy.mkdir(exist_ok=True)

# Files to keep (ONLY)
keep = {'start_jarvis.bat'}

# Patterns to move
patterns = ['start_*.bat', 'start_*.py', 'restart_*.py', 'start_server*.py']

moved = []
errors = []

for pattern in patterns:
    for file in root.glob(pattern):
        if file.name in keep:
            print(f'  ✓ KEEP  : {file.name}')
        else:
            try:
                dest = legacy / file.name
                shutil.move(str(file), str(dest))
                moved.append(file.name)
                print(f'  ↦ MOVED : {file.name} → _legacy/')
            except Exception as e:
                errors.append((file.name, str(e)))
                print(f'  ✗ ERROR: {file.name} — {e}')

# Also move test files from root to tests/
print('\n[Moving test files to tests/]')
test_patterns = ['test_*.py']
tests_dir = root / 'tests'
tests_dir.mkdir(exist_ok=True)

for pattern in test_patterns:
    for file in root.glob(pattern):
        # Don't move if already in tests/
        if file.parent.name == 'tests':
            continue
        try:
            dest = tests_dir / file.name
            if not dest.exists():
                shutil.move(str(file), str(dest))
                moved.append(file.name)
                print(f'  ↦ MOVED : {file.name} → tests/')
        except Exception as e:
            errors.append((file.name, str(e)))
            print(f'  ✗ ERROR: {file.name} — {e}')

print('\n' + '='*70)
print(f'Summary: Moved {len(moved)} files')
if errors:
    print(f'Errors: {len(errors)}')
else:
    print('✅ PROBLEM 1 RESOLVED')
print('='*70 + '\n')
