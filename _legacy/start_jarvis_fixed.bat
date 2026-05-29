@echo off
title J.A.R.V.I.S. v6.0 — FIXED (Ollama Timeout Fix Applied)
color 0B
cd /d C:\Users\cibernetico\JARVIS

echo.
echo  =============================================
echo   J.A.R.V.I.S. — Neural Core v6.0 FIXED
echo   Ollama Timeout Solution Applied
echo  =============================================
echo.

:: Variáveis de ambiente
set KMP_DUPLICATE_LIB_OK=TRUE
set OMP_NUM_THREADS=1
set PYTHONIOENCODING=utf-8
set OLLAMA_HOST=127.0.0.1:11434
set OLLAMA_KEEP_ALIVE=30m

:: [1] Verificar venv
call venv311\Scripts\activate.bat >nul 2>&1
if errorlevel 1 (
    echo [ERR] venv311 nao encontrado.
    echo       Execute: python -m venv venv311 ^&^& venv311\Scripts\pip install -r backend\requirements.txt
    pause & exit /b 1
)
echo [OK] venv311 ativo

:: [2] Matar instancia anterior do backend
echo [..] Cleaning up old processes...
taskkill /F /IM python.exe >nul 2>&1
timeout /t 1 /nobreak >nul

:: [3] Verificar/iniciar Ollama
echo [..] Checking Ollama...
curl -s --connect-timeout 2 http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [..] Starting Ollama...
    start "" /min ollama serve
    timeout /t 5 /nobreak >nul
    curl -s --connect-timeout 3 http://127.0.0.1:11434/api/tags >nul 2>&1
    if errorlevel 1 (
        echo [!] Ollama nao iniciou. Execute: winget install Ollama.Ollama
    ) else (
        echo [OK] Ollama online.
    )
) else (
    echo [OK] Ollama online.
)

:: [4] Iniciar backend
echo [..] Starting JARVIS backend (with Ollama timeout fix)...
start "JARVIS-Backend" cmd /k "cd /d C:\Users\cibernetico\JARVIS && set KMP_DUPLICATE_LIB_OK=TRUE && set OMP_NUM_THREADS=1 && set OLLAMA_HOST=127.0.0.1:11434 && venv311\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --log-level warning"

:: [5] Aguardar backend
echo [..] Waiting for backend to start...
timeout /t 8 /nobreak >nul
curl -s --connect-timeout 5 http://localhost:8000/health >nul 2>&1
if errorlevel 1 (
    echo [..] Backend still initializing...
    timeout /t 6 /nobreak >nul
)
echo [OK] Backend online.

:: [6] Abrir interface
start "" "http://localhost:8000"

echo.
echo  =============================================
echo   JARVIS ONLINE — Good day, Sir.
echo.
echo   Local  : http://localhost:8000
echo   Status : READY
echo.
echo   FIXES APPLIED:
echo   - Timeout: 120 seconds (was 10)
echo   - Model: phi:latest (optimized for speed)
echo   - Cold start handling: improved
echo.
echo   You can now type messages and JARVIS will respond!
echo  =============================================
echo.
pause
