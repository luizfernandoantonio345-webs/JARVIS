@echo off
title J.A.R.V.I.S. v10.0
color 0B
cd /d "%~dp0"

echo.
echo  =============================================
echo   J.A.R.V.I.S. v10.0 -- Neural Core
echo   Just A Rather Very Intelligent System
echo   Powered by Ollama + FastAPI
echo  =============================================
echo.

:: ── Prevent OpenBLAS/MKL thread conflicts ────────────────
set KMP_DUPLICATE_LIB_OK=TRUE
set OMP_NUM_THREADS=2
set KMP_WARNINGS=FALSE
set OPENBLAS_NUM_THREADS=2
set MKL_NUM_THREADS=2
set PYTHONIOENCODING=utf-8
set OLLAMA_HOST=127.0.0.1:11434
set OLLAMA_KEEP_ALIVE=30m

:: ── [1] Auto-detect RAM and select model ─────────────────
set JARVIS_MODEL=qwen2:0.5b
for /f "tokens=2 delims==" %%a in ('wmic OS get TotalVisibleMemorySize /value 2^>nul') do (
    set /a _RAM_MB=%%a/1024
)
if defined _RAM_MB (
    if %_RAM_MB% GEQ 28000 (
        set JARVIS_MODEL=mistral:7b
        echo [OK] RAM: %_RAM_MB%MB -- Model: mistral:7b
    ) else if %_RAM_MB% GEQ 12000 (
        set JARVIS_MODEL=llama3.2:3b
        echo [OK] RAM: %_RAM_MB%MB -- Model: llama3.2:3b
    ) else if %_RAM_MB% GEQ 6000 (
        set JARVIS_MODEL=qwen2:1.5b
        echo [OK] RAM: %_RAM_MB%MB -- Model: qwen2:1.5b
    ) else (
        echo [OK] RAM: %_RAM_MB%MB -- Model: qwen2:0.5b (baixa RAM)
    )
) else (
    echo [OK] Model: qwen2:0.5b (RAM nao detectada)
)

:: ── [2] Check virtual environment ────────────────────────
if not exist "venv311\Scripts\activate.bat" (
    echo.
    echo [ERR] venv311 nao encontrado. Execute primeiro:
    echo.
    echo   python -m venv venv311
    echo   venv311\Scripts\pip install -r backend\requirements.txt
    echo.
    pause & exit /b 1
)
call venv311\Scripts\activate.bat >nul 2>&1
echo [OK] Python venv ativo

:: ── [3] Start Ollama if not running ──────────────────────
echo [..] Verificando Ollama...
curl -s --connect-timeout 2 http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [..] Iniciando Ollama...
    start "" /min ollama serve
    timeout /t 6 /nobreak >nul
    curl -s --connect-timeout 4 http://127.0.0.1:11434/api/tags >nul 2>&1
    if errorlevel 1 (
        echo [!] Ollama nao iniciou. Instale em: https://ollama.com
        echo     Depois execute este script novamente.
        pause & exit /b 1
    )
)
echo [OK] Ollama online

:: ── [4] Pull model if missing ────────────────────────────
ollama list 2>nul | findstr /I "%JARVIS_MODEL%" >nul 2>&1
if errorlevel 1 (
    echo [..] Baixando %JARVIS_MODEL% (pode demorar na 1a vez)...
    ollama pull %JARVIS_MODEL%
)
echo [OK] Modelo %JARVIS_MODEL% pronto

:: ── [5] Kill previous backend instance ───────────────────
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
timeout /t 1 /nobreak >nul

:: ── [6] Create required directories ─────────────────────
if not exist "data" mkdir "data"

:: ── [7] Start JARVIS backend ─────────────────────────────
echo [..] Iniciando backend JARVIS...
start "JARVIS" cmd /k ^
    "cd /d "%~dp0" && ^
     set KMP_DUPLICATE_LIB_OK=TRUE && ^
     set OMP_NUM_THREADS=2 && ^
     set OLLAMA_HOST=127.0.0.1:11434 && ^
     set JARVIS_MODEL=%JARVIS_MODEL% && ^
     set PYTHONIOENCODING=utf-8 && ^
     venv311\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --log-level warning"

:: ── [8] Wait for backend ─────────────────────────────────
echo [..] Aguardando backend...
timeout /t 8 /nobreak >nul
curl -s --connect-timeout 5 http://localhost:8000/health >nul 2>&1
if errorlevel 1 (
    timeout /t 8 /nobreak >nul
)
echo [OK] Backend online

:: ── [9] Pre-warm model (eliminates ~20s cold start) ─────
start "" /min cmd /c "curl -s --max-time 60 -X POST http://127.0.0.1:11434/api/generate -d \"{\"\"model\"\":\"\"%JARVIS_MODEL%\"\",\"\"prompt\"\":\"\"ready\"\",\"\"stream\"\":false,\"\"keep_alive\"\":\"\"30m\"\"}\" >nul 2>&1"

:: ── [10] Open browser ────────────────────────────────────
start "" "http://localhost:8000"

echo.
echo  =============================================
echo   JARVIS ONLINE -- Good day, Sir.
echo.
echo   Interface : http://localhost:8000
echo   API Docs  : http://localhost:8000/docs
echo   Health    : http://localhost:8000/health
echo   Model     : %JARVIS_MODEL%
echo.
echo   Press any key to stop JARVIS.
echo  =============================================
echo.
pause

:: ── Stop ─────────────────────────────────────────────────
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
echo [OK] JARVIS encerrado.
