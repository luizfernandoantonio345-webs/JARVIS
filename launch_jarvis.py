#!/usr/bin/env python3
"""
J.A.R.V.I.S. — Launcher Principal
Opção 1: Terminal JARVIS (rápido, sem dependências de frontend)
Opção 2: Interface Web completa (FastAPI + Vite)
"""
import subprocess
import time
import sys
import os
import webbrowser
from pathlib import Path

ROOT = Path(__file__).parent
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"

def check_ollama():
    try:
        import requests
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def launch_terminal():
    """Inicia o JARVIS Terminal diretamente."""
    print("\n  Iniciando J.A.R.V.I.S. Terminal...")
    os.execv(str(VENV_PY), [str(VENV_PY), str(ROOT / "jarvis.py")])


def launch_web():
    """Inicia o JARVIS com interface web (FastAPI + Vite)."""
    os.chdir(ROOT)
    print("\n" + "=" * 60)
    print("  J.A.R.V.I.S. — INICIALIZANDO INTERFACE WEB".center(60))
    print("=" * 60 + "\n")

    print("[1/3] Iniciando Backend FastAPI (porta 8000)...")
    try:
        subprocess.Popen(
            [str(VENV_PY), "-m", "uvicorn", "backend.main:app",
             "--host", "0.0.0.0", "--port", "8000"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(3)
        print("  [OK] Backend iniciado")
    except Exception as e:
        print(f"  [ERRO] {e}")
        return 1

    print("[2/3] Iniciando Frontend Vite (porta 3000)...")
    try:
        frontend_dir = ROOT / "frontend"
        if not (frontend_dir / "node_modules").exists():
            print("  Instalando dependências npm (primeira vez)...")
            subprocess.run(["npm", "install"], cwd=frontend_dir, check=True)
        subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=frontend_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(4)
        print("  [OK] Frontend iniciado")
    except Exception as e:
        print(f"  [ERRO] {e}")
        return 1

    print("[3/3] Abrindo navegador...")
    time.sleep(1)
    try:
        webbrowser.open("http://localhost:3000")
        print("  [OK] Browser aberto: http://localhost:3000")
    except Exception:
        print("  Abra no browser: http://localhost:3000")

    print("\n" + "=" * 60)
    print("  J.A.R.V.I.S. WEB ONLINE".center(60))
    print("=" * 60)
    print("\n  Pressione Ctrl+C para encerrar.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n  Encerrando sistemas...")
    return 0


def main():
    ollama_ok = check_ollama()

    print("\n" + "═" * 50)
    print("  J.A.R.V.I.S.  — Selecione o modo de inicialização")
    print("═" * 50)
    print()
    print("  [1] Terminal JARVIS   ← RECOMENDADO (rápido, funciona agora)")
    print("  [2] Interface Web     (requer Node.js e npm)")
    print()

    if not ollama_ok:
        print("  ⚠  Ollama não detectado em localhost:11434")
        print("     Inicie o Ollama antes de usar o JARVIS.")
        print()

    try:
        choice = input("  Escolha [1]: ").strip() or "1"
    except (KeyboardInterrupt, EOFError):
        print("\n  Abortado.")
        sys.exit(0)

    if choice == "2":
        sys.exit(launch_web())
    else:
        launch_terminal()


if __name__ == "__main__":
    main()
