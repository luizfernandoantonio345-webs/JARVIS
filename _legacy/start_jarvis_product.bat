@echo off
setlocal enabledelayedexpansion

title J.A.R.V.I.S. v6.0 — PRODUCT START (Ollama + Backend)

cd /d C:\Users\cibernetico\JARVIS

echo.
echo =============================================
echo   J.A.R.V.I.S. — PRODUCT START (v6.0)
echo =============================================
echo.

:: Config
set OLLAMA_HOST=127.0.0.1:11434
set BACKEND_URL=http://localhost:8000
set WS_URL=ws://localhost:8000/ws/jarvis

:: Optional: allow forcing RAM used by model selector (backend reads it)
:: set JARVIS_TOTAL_RAM_GB=8

:: Env vars for backend
set KMP_DUPLICATE_LIB_OK=TRUE
set OMP_NUM_THREADS=1
set PYTHONIOENCODING=utf-8

:: [1] Activate venv
call venv311\Scripts\activate.bat >nul 2>&1
if errorlevel 1 (
    echo [ERR] venv311 nao encontrado.
    echo       Execute: python -m venv venv311 ^&^& venv311\Scripts\pip install -r backend\requirements.txt
    pause & exit /b 1
)
echo [OK] venv311 ativo

:: [2] Start/verify Ollama
echo [..] Checking Ollama...
curl -s --connect-timeout 2 http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [..] Ollama nao responde. Iniciando: ollama serve
    start "" /min ollama serve
    timeout /t 3 /nobreak >nul
)

:: Wait until online
set /a i=0
:wait_ollama
timeout /t 1 /nobreak >nul
curl -s --connect-timeout 2 http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (
    set /a i+=1
    if !i! LSS 30 (
        echo [..] Aguardando Ollama online (!i!/30)...
        goto wait_ollama
    ) else (
        echo [ERR] Ollama nao ficou online a tempo.
        echo       Abra um terminal e rode: ollama serve
        pause & exit /b 1
    )
)

echo [OK] Ollama online.

:: [3] Start backend
echo [..] Starting backend (FastAPI) on %BACKEND_URL% ...
start "JARVIS-Backend" cmd /k ^
    "cd /d C:\Users\cibernetico\JARVIS && ^
     set KMP_DUPLICATE_LIB_OK=TRUE && set OMP_NUM_THREADS=1 && ^
     set OLLAMA_HOST=%OLLAMA_HOST% && ^
     venv311\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --log-level warning"

:: [4] Wait backend health
echo [..] Waiting for backend /health ...
set /a j=0
:wait_backend
timeout /t 1 /nobreak >nul
curl -s --connect-timeout 2 http://localhost:8000/health >nul 2>&1
if errorlevel 1 (
    set /a j+=1
    if !j! LSS 20 (
        echo [..] Backend ainda inicializando (!j!/20)...
        goto wait_backend
    ) else (
        echo [ERR] Backend nao ficou online a tempo.
        pause & exit /b 1
    )
)
echo [OK] Backend online.

:: [5] Smoke tests
echo.
echo [..] Running smoke tests (scripts/smoke_test.py) ...
venv311\Scripts\python.exe scripts/smoke_test.py --categories health,chat,websocket,voice,memory --verbose

echo.
echo [OK] Smoke tests finalizados.
echo.

:: [6] Open interface (if running)
start "" "http://localhost:8000"

echo =============================================
echo   JARVIS ONLINE — PRODUCT MODE
echo   Local  : %BACKEND_URL%
echo   WebSocket : %WS_URL%
echo   Status : READY
echo =============================================
echo.
pause
