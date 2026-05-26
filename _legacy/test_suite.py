#!/usr/bin/env python3
"""JARVIS Test Suite - Validacao TIER 1 + TIER 2"""

import sys
from pathlib import Path

def test_imports():
    """Testa imports do backend"""
    print("\n[TESTE 1] Validar Imports Backend")
    print("-" * 50)
    try:
        sys.path.insert(0, "backend")
        import pyttsx3
        print("[OK] pyttsx3 (TTS) importado")

        from main import app
        print("[OK] Backend main.py carregado")
        return True
    except Exception as e:
        print(f"[ERRO] {e}")
        return False

def test_html_structure():
    """Valida estrutura do HTML"""
    print("\n[TESTE 2] Validar HTML Frontend")
    print("-" * 50)
    try:
        html_path = Path("frontend/index.html")
        if not html_path.exists():
            print("[ERRO] index.html nao encontrado")
            return False

        with open(html_path, encoding='utf-8') as f:
            html = f.read()

        checks = {
            "WebSocket URL correta": 'ws://localhost:8000/ws/jarvis' in html,
            "Widget historico (w4)": 'id="w4"' in html,
            "Tema Iron Man": 'theme-iron' in html,
            "Sugestoes dropdown": 'suggestions-dropdown' in html,
            "Thinking indicator": 'thinking-indicator' in html,
            "Funcao setOrbState": 'setOrbState' in html,
            "Funcao playTTS": 'playTTS' in html,
            "Funcao addToHistory": 'addToHistory' in html,
        }

        all_ok = True
        for check, result in checks.items():
            status = "[OK]" if result else "[FALHOU]"
            print(f"{status} {check}")
            all_ok = all_ok and result

        size_kb = len(html) / 1024
        lines = len(html.split('\n'))
        print(f"[INFO] Tamanho: {size_kb:.1f} KB ({lines} linhas)")
        return all_ok
    except Exception as e:
        print(f"[ERRO] {e}")
        return False

def test_vite_config():
    """Valida configuracao Vite"""
    print("\n[TESTE 3] Validar Vite Config")
    print("-" * 50)
    try:
        config_path = Path("frontend/vite.config.ts")
        if not config_path.exists():
            print("[ERRO] vite.config.ts nao encontrado")
            return False

        with open(config_path) as f:
            config = f.read()

        checks = {
            "Porta 3000": "port: 3000" in config,
            "Proxy WebSocket": "'/ws'" in config,
            "Proxy /chat": "'/chat'" in config,
            "Proxy /computer": "'/computer'" in config,
        }

        all_ok = True
        for check, result in checks.items():
            status = "[OK]" if result else "[FALHOU]"
            print(f"{status} Vite: {check}")
            all_ok = all_ok and result
        return all_ok
    except Exception as e:
        print(f"[ERRO] {e}")
        return False

def test_backend_endpoints():
    """Valida endpoints do backend"""
    print("\n[TESTE 4] Validar Endpoints Backend")
    print("-" * 50)
    try:
        sys.path.insert(0, "backend")
        from main import app

        endpoints = {
            "WebSocket /ws/jarvis": False,
            "POST /tts": False,
            "POST /process": False,
        }

        for route in app.routes:
            if "/ws/jarvis" in str(route.path):
                endpoints["WebSocket /ws/jarvis"] = True
            if route.path == "/tts" and "POST" in str(route.methods):
                endpoints["POST /tts"] = True
            if route.path == "/process" and "POST" in str(route.methods):
                endpoints["POST /process"] = True

        all_ok = True
        for endpoint, found in endpoints.items():
            status = "[OK]" if found else "[FALHOU]"
            print(f"{status} {endpoint}")
            all_ok = all_ok and found
        return all_ok
    except Exception as e:
        print(f"[ERRO] {e}")
        return False

def test_dependencies():
    """Valida dependencias Python"""
    print("\n[TESTE 5] Validar Dependencias")
    print("-" * 50)

    deps = ["fastapi", "uvicorn", "pyttsx3", "websockets"]
    all_ok = True

    for dep in deps:
        try:
            __import__(dep)
            print(f"[OK] {dep}")
        except ImportError:
            print(f"[FALHOU] {dep} nao encontrado")
            all_ok = False

    return all_ok

def main():
    print("\n" + "="*50)
    print("JARVIS TEST SUITE - TIER 1 + TIER 2")
    print("="*50)

    results = {}
    results["Imports"] = test_imports()
    results["HTML"] = test_html_structure()
    results["Vite"] = test_vite_config()
    results["Endpoints"] = test_backend_endpoints()
    results["Dependencias"] = test_dependencies()

    # Resumo
    print("\n" + "="*50)
    print("RESUMO")
    print("="*50)

    for test, result in results.items():
        status = "PASSOU" if result else "FALHOU"
        print(f"  {test:20} [{status}]")

    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"\nResultado: {passed}/{total} testes passaram\n")

    if passed == total:
        print("[OK] TODOS OS TESTES PASSARAM!")
        print("[INFO] Sistema pronto para iniciar.")
        print("[INFO] Execute: start_jarvis.bat")
        return 0
    else:
        print(f"[ERRO] {total - passed} teste(s) falharam.")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
