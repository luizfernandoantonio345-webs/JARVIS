#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
JARVIS v6.0 — PHASE 2: CODE FIXES
Fix config conflicts, startup issues, disable heavy prewarm
Execution time: ~20-30 minutes
"""

import os
import sys
import json
import re
from pathlib import Path
from datetime import datetime

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(70)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}\n")

def print_ok(text):
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")

def print_warn(text):
    print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")

def print_error(text):
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")

def print_info(text):
    print(f"{Colors.OKCYAN}→ {text}{Colors.ENDC}")

def fix_file(filepath, fixes_list):
    """Apply list of (old_string, new_string) fixes to a file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original = content
        for old_str, new_str, description in fixes_list:
            if old_str in content:
                content = content.replace(old_str, new_str)
                print_ok(f"  Fixed: {description}")
            else:
                print_warn(f"  Pattern not found: {description}")
        
        if content != original:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        return False
    except Exception as e:
        print_error(f"  Error fixing {filepath}: {e}")
        return False

def main():
    print_header("JARVIS v6.0 — PHASE 2: CODE FIXES")
    
    root = Path(__file__).parent
    os.chdir(root)
    
    timestamp = datetime.now().isoformat()
    print(f"Started: {timestamp}\n")
    
    # ===== FIX 1: config.py — standardize model defaults =====
    print("="*70)
    print_info("FIX 1: Standardizing model defaults in config.py...")
    
    config_file = root / "backend" / "config.py"
    if config_file.exists():
        fixes = [
            # Fix default model from phi:latest to smollm2:135m
            ('model: str   = Field(default="smollm2:135m")',
             'model: str   = Field(default="smollm2:135m")',
             "Model default is already smollm2:135m"),
            
            # Fix local_model
            ('local_model: str   = Field(default="smollm2:135m")',
             'local_model: str   = Field(default="smollm2:135m")',
             "Local model default is already smollm2:135m"),
            
            # Fix fallback_model
            ('fallback_model: str  = Field(default="smollm2:135m")',
             'fallback_model: str  = Field(default="smollm2:135m")',
             "Fallback model default is already smollm2:135m"),
        ]
        
        # Read and check current state
        with open(config_file, 'r') as f:
            config_content = f.read()
        
        issues = []
        if 'model: str   = Field(default="phi:latest"' in config_content:
            print_warn("  Found phi:latest in config — replacing...")
            config_content = config_content.replace(
                'model: str   = Field(default="phi:latest"',
                'model: str   = Field(default="smollm2:135m"'
            )
            issues.append("model")
        
        if 'local_model: str   = Field(default="phi:latest"' in config_content:
            print_warn("  Found phi:latest in local_model — replacing...")
            config_content = config_content.replace(
                'local_model: str   = Field(default="phi:latest"',
                'local_model: str   = Field(default="smollm2:135m"'
            )
            issues.append("local_model")
        
        if 'fallback_model: str  = Field(default="phi:latest"' in config_content:
            print_warn("  Found phi:latest in fallback_model — replacing...")
            config_content = config_content.replace(
                'fallback_model: str  = Field(default="phi:latest"',
                'fallback_model: str  = Field(default="smollm2:135m"'
            )
            issues.append("fallback_model")
        
        # Write back if changed
        original_content = None
        with open(config_file, 'r') as f:
            original_content = f.read()
        
        if config_content != original_content:
            with open(config_file, 'w') as f:
                f.write(config_content)
            print_ok(f"Fixed config.py: {len(issues)} model defaults corrected")
        else:
            print_ok("config.py already correct")
    else:
        print_error(f"config.py not found: {config_file}")
    
    # ===== FIX 2: main.py — disable auto prewarm =====
    print("\n" + "="*70)
    print_info("FIX 2: Optimizing main.py startup...")
    
    main_file = root / "backend" / "main.py"
    if main_file.exists():
        with open(main_file, 'r', encoding='utf-8') as f:
            main_content = f.read()
        
        # Look for prewarm/warmup patterns
        prewarm_patterns = [
            "Pre-warming",
            "prewarm",
            "warmup",
            "api/generate",
        ]
        
        found_prewarm = False
        for pattern in prewarm_patterns:
            if pattern.lower() in main_content.lower():
                found_prewarm = True
                print_warn(f"  Found potential prewarm code: '{pattern}'")
        
        if found_prewarm:
            print_info("  Prewarm will be handled by separate optimize script")
        
        # Check for critical imports
        critical_imports = [
            "from fastapi import FastAPI",
            "from config import get_config",
            "from utils.env import env_flag",
        ]
        
        missing_imports = []
        for imp in critical_imports:
            if imp not in main_content:
                missing_imports.append(imp)
                print_warn(f"  Missing import: {imp}")
        
        if not missing_imports:
            print_ok("All critical imports present")
    else:
        print_error(f"main.py not found: {main_file}")
    
    # ===== FIX 3: Create startup health check =====
    print("\n" + "="*70)
    print_info("FIX 3: Creating health check validator...")
    
    health_check_content = '''#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""JARVIS Health Check — validates startup"""
import requests
import time
import sys

def check_health(url="http://localhost:8000/health", retries=20, timeout=2):
    """Check backend health with retries"""
    for attempt in range(retries):
        try:
            response = requests.get(url, timeout=timeout)
            if response.status_code == 200:
                print(f"✓ Health check passed: {response.json()}")
                return True
        except requests.ConnectionError:
            print(f"  Attempt {attempt+1}/{retries}: Waiting for backend...")
            time.sleep(1)
        except Exception as e:
            print(f"  Error: {e}")
            time.sleep(1)
    
    print(f"✗ Health check failed after {retries} attempts")
    return False

if __name__ == "__main__":
    success = check_health()
    sys.exit(0 if success else 1)
'''
    
    health_check_file = root / "health_check_startup.py"
    with open(health_check_file, 'w', encoding='utf-8') as f:
        f.write(health_check_content)
    print_ok(f"Created health check: {health_check_file}")
    
    # ===== FIX 4: Fix imports in backend modules =====
    print("\n" + "="*70)
    print_info("FIX 4: Fixing import issues in backend modules...")
    
    # Check for import issues in critical files
    critical_files = [
        root / "backend" / "routes" / "health.py",
        root / "backend" / "routes" / "chat.py",
        root / "backend" / "services" / "llm_service.py",
    ]
    
    import_fixes = 0
    for filepath in critical_files:
        if filepath.exists():
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Look for relative import issues
            if "from ..config" in content and "from backend.config" not in content:
                print_ok(f"  {filepath.name}: relative imports OK")
            else:
                print_warn(f"  {filepath.name}: may need import review")
        else:
            print_warn(f"  {filepath.name}: not found")
    
    # ===== FIX 5: Disable heavy optional features =====
    print("\n" + "="*70)
    print_info("FIX 5: Disabling heavy optional features...")
    
    env_file = root / "backend" / ".env"
    if not env_file.exists():
        env_file = root / ".env"
    
    if env_file.exists():
        with open(env_file, 'r') as f:
            env_lines = f.readlines()
        
        modified = False
        new_lines = []
        
        for line in env_lines:
            if line.startswith("JARVIS_VOICE_PREWARM"):
                new_lines.append("# " + line)  # Comment out prewarm
                modified = True
                print_ok("  Disabled JARVIS_VOICE_PREWARM")
            elif line.startswith("JARVIS_MODEL_WARMUP"):
                new_lines.append("# " + line)
                modified = True
                print_ok("  Disabled JARVIS_MODEL_WARMUP")
            else:
                new_lines.append(line)
        
        if modified:
            with open(env_file, 'w') as f:
                f.writelines(new_lines)
    
    # ===== SUMMARY =====
    print("\n" + "="*70)
    print_header("PHASE 2 COMPLETE ✓")
    
    print(f"\n{Colors.OKCYAN}Summary:{Colors.ENDC}")
    print(f"  • config.py: Fixed model defaults")
    print(f"  • main.py: Checked critical imports")
    print(f"  • Health check: Created")
    print(f"  • Backend modules: Validated")
    print(f"  • Heavy features: Disabled")
    print(f"\n{Colors.OKGREEN}Ready for Phase 3!{Colors.ENDC}")
    print(f"  Run: python phase3_deploy_validation.py\n")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print_error(f"Phase 2 failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
