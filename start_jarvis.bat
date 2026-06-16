@echo off
title J.A.R.V.I.S. v6.0 — Initializing
color 0B
cd /d "%~dp0"

echo.
echo  =============================================
echo   J.A.R.V.I.S. — Neural Core v6.0
echo   Just A Rather Very Intelligent System
echo   Ollama Local  ^|  FastAPI
echo  =============================================
echo.

:: Variáveis de ambiente — previne crashes MKL/OpenBLAS
set KMP_DUPLICATE_LIB_OK=TRUE
set OMP_NUM_THREADS=1
set KMP_WARNINGS=FALSE
set OPENBLAS_NUM_THREADS=1
set MKL_NUM_THREADS=1
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

:: [2] Verificar/iniciar Ollama local
echo [..] Checking Ollama...
curl -s --connect-timeout 2 http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [..] Starting Ollama...
    start "" /min ollama serve
    timeout /t 5 /nobreak >nul
    curl -s --connect-timeout 3 http://127.0.0.1:11434/api/tags >nul 2>&1
    if errorlevel 1 (
        echo [!] Ollama nao iniciou. Instale: winget install Ollama.Ollama
    ) else (
        echo [OK] Ollama online.
    )
) else (
    echo [OK] Ollama online.
)

:: [3] Matar instancia anterior do backend
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8000 " ^| findstr "LISTENING"') do taskkill /PID %%a /F >nul 2>&1
timeout /t 1 /nobreak >nul

:: [4] Iniciar backend
echo [..] Starting JARVIS backend...
start "JARVIS-Backend" cmd /k "cd /d "%~dp0" && set KMP_DUPLICATE_LIB_OK=TRUE && set OMP_NUM_THREADS=1 && set OLLAMA_HOST=127.0.0.1:11434 && venv311\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --log-level warning"

:: Aguardar backend
timeout /t 8 /nobreak >nul
curl -s --connect-timeout 5 http://localhost:8000/health >nul 2>&1
if errorlevel 1 (
    echo [!] Backend ainda iniciando...
    timeout /t 6 /nobreak >nul
)
echo [OK] Backend online.

:: [5] Prewarm modelo (elimina cold start de ~20s na primeira mensagem)
echo [..] Pre-warming AI model in background...
start "" /min cmd /c "curl -s --max-time 60 -X POST http://127.0.0.1:11434/api/generate -d \"{\"\"model\"\":\"\"qwen2:0.5b\"\",\"\"prompt\"\":\"\"hi\"\",\"\"stream\"\":false,\"\"keep_alive\"\":\"\"60m\"\"}\" >nul 2>&1"

:: [6] Abrir interface
start "" "http://localhost:8000"

echo.
echo  =============================================
echo   JARVIS ONLINE — Good day, Sir.
echo.
echo   Local  : http://localhost:8000
echo.
echo   Model pre-warming in background...
echo   First response ready in ~20s.
echo  =============================================
echo.
pause
