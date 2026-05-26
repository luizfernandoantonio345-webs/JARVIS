@echo off
:: JARVIS Diagnostic Script
:: Run this to diagnose import issues before starting the server
set "ROOT=%~dp0"
cd /d "%ROOT%"
set "PYTHON=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=%ROOT%\venv311\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=%ROOT%\venv\Scripts\python.exe"
set PORT=8000

if not exist "%PYTHON%" (
echo [ERRO] Python de venv nao encontrado.
echo [DICA] Esperado em .venv\Scripts\python.exe, venv311\Scripts\python.exe ou venv\Scripts\python.exe
pause
exit /b 1
)

echo ============================================================
echo  JARVIS Diagnostics
echo ============================================================

echo.
echo [1] Python version:
%PYTHON% --version 2>&1

echo.
echo [2] FastAPI / Uvicorn installed?
%PYTHON% -c "import fastapi, uvicorn; print('fastapi', fastapi.__version__); print('uvicorn', uvicorn.__version__)" 2>&1

echo.
echo [3] Pydantic installed?
%PYTHON% -c "import pydantic; print('pydantic', pydantic.__version__)" 2>&1

echo.
echo [4] backend.main import test (JARVIS_DISABLE_VOICE=1):
set JARVIS_DISABLE_VOICE=1
%PYTHON% -c "import sys; sys.path.insert(0,'backend'); import backend.main; print('[OK] backend.main imported successfully')" 2>&1

echo.
echo [5] backend.main_simple import test:
%PYTHON% -c "import backend.main_simple; print('[OK] backend.main_simple imported successfully')" 2>&1

echo.
echo [6] Server health check (if running):
%PYTHON% -c "import urllib.request; print(urllib.request.urlopen('http://localhost:%PORT%/health',timeout=3).read().decode())" 2>&1

echo.
echo [7] Config check:
%PYTHON% -c "import sys; sys.path.insert(0,'backend'); from config import get_config; c=get_config(); print('Ollama URL:', c.ollama_url); print('Model:', c.model)" 2>&1

echo.
echo ============================================================
echo  If [4] failed, install requirements:
echo    %PYTHON% -m pip install -r backend\requirements.txt
echo  Then re-run: start_jarvis.bat
echo ============================================================
pause
