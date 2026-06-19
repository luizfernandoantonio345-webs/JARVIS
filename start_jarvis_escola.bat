@echo off
title J.A.R.V.I.S. v9.0 — ESCOLA (32GB / Ryzen 7)
color 0B
cd /d "%~dp0"

echo.
echo  =============================================
echo   J.A.R.V.I.S. v9.0 — Neural Core
echo   90+ Features Premium
echo   Config: PC Escola [32GB / Ryzen 7]
echo  =============================================
echo.

:: ── [0] Carregar config da escola ───────────────────────────────────────────
if exist ".env.escola" (
    copy /Y ".env.escola" ".env" >nul 2>&1
    echo [OK] Config escola carregada
) else (
    echo [!] .env.escola nao encontrado - usando .env atual
)

:: ── Variáveis de ambiente ────────────────────────────────────────────────────
set KMP_DUPLICATE_LIB_OK=TRUE
set OMP_NUM_THREADS=4
set KMP_WARNINGS=FALSE
set OPENBLAS_NUM_THREADS=4
set MKL_NUM_THREADS=4
set PYTHONIOENCODING=utf-8
set OLLAMA_HOST=127.0.0.1:11434
set OLLAMA_KEEP_ALIVE=60m
set JARVIS_MODEL=mistral:7b
set JARVIS_TOTAL_RAM_GB=32
set JARVIS_TEST_MODE=

:: ── [1] Verificar venv ───────────────────────────────────────────────────────
if not exist "venv311\Scripts\activate.bat" (
    echo [ERR] venv311 nao encontrado!
    echo.
    echo  SOLUCAO:
    echo    python -m venv venv311
    echo    venv311\Scripts\pip install -r backend\requirements.txt
    echo.
    pause & exit /b 1
)
call venv311\Scripts\activate.bat >nul 2>&1
echo [OK] Python venv311 ativo

:: ── [2] Verificar/iniciar Ollama ─────────────────────────────────────────────
echo [..] Verificando Ollama...
curl -s --connect-timeout 3 http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [..] Iniciando Ollama em background...
    start "" /min ollama serve
    echo [..] Aguardando Ollama (15s)...
    timeout /t 15 /nobreak >nul
    curl -s --connect-timeout 5 http://127.0.0.1:11434/api/tags >nul 2>&1
    if errorlevel 1 (
        echo [!] Ollama nao respondeu.
        echo     Instale: winget install Ollama.Ollama
        echo     Depois reinicie este script.
        pause & exit /b 1
    )
)
echo [OK] Ollama online

:: ── [3] Verificar modelo ─────────────────────────────────────────────────────
echo [..] Verificando mistral:7b...
ollama list 2>nul | findstr /I "mistral:7b" >nul 2>&1
if errorlevel 1 (
    echo [..] Baixando mistral:7b (~4.1GB) — pode demorar na 1a vez...
    ollama pull mistral:7b
    if errorlevel 1 (
        echo [!] Falha mistral:7b. Usando llama3.2:3b como fallback...
        ollama pull llama3.2:3b
        set JARVIS_MODEL=llama3.2:3b
    )
) else (
    echo [OK] mistral:7b disponivel
)

:: ── [4] Encerrar instancia anterior ──────────────────────────────────────────
echo [..] Encerrando instancia anterior (se houver)...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
timeout /t 2 /nobreak >nul

:: ── [5] Criar pasta de dados ─────────────────────────────────────────────────
if not exist "backend\data" mkdir "backend\data"
if not exist "backend\logs" mkdir "backend\logs"

:: ── [6] Iniciar backend JARVIS v9.0 ──────────────────────────────────────────
echo [..] Iniciando JARVIS v9.0 backend...
start "JARVIS-Backend" cmd /k ^
    "cd /d "%~dp0" && ^
     set KMP_DUPLICATE_LIB_OK=TRUE && ^
     set OMP_NUM_THREADS=4 && ^
     set OLLAMA_HOST=127.0.0.1:11434 && ^
     set OLLAMA_KEEP_ALIVE=60m && ^
     set JARVIS_MODEL=mistral:7b && ^
     set JARVIS_TOTAL_RAM_GB=32 && ^
     set PYTHONIOENCODING=utf-8 && ^
     venv311\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --log-level info"

:: ── [7] Aguardar backend ─────────────────────────────────────────────────────
echo [..] Aguardando backend inicializar...
timeout /t 10 /nobreak >nul
curl -s --connect-timeout 5 http://localhost:8000/health >nul 2>&1
if errorlevel 1 (
    echo [..] Backend ainda carregando — aguardando mais 15s...
    timeout /t 15 /nobreak >nul
)
curl -s --connect-timeout 5 http://localhost:8000/health >nul 2>&1
if errorlevel 1 (
    echo [!] Backend pode estar com erro. Verifique a janela JARVIS-Backend.
) else (
    echo [OK] Backend online - http://localhost:8000/health
)

:: ── [8] Pre-aquecer modelo (elimina cold start) ───────────────────────────────
echo [..] Pre-aquecendo mistral:7b em background...
start "" /min powershell -WindowStyle Hidden -Command "Invoke-RestMethod -Method POST -Uri 'http://127.0.0.1:11434/api/generate' -ContentType 'application/json' -Body '{\"model\":\"mistral:7b\",\"prompt\":\"ready\",\"stream\":false,\"keep_alive\":\"60m\"}' -TimeoutSec 120 | Out-Null" 2>nul

:: ── [9] Abrir interface no browser ───────────────────────────────────────────
timeout /t 2 /nobreak >nul
start "" "http://localhost:8000"

echo.
echo  =============================================
echo   JARVIS v9.0 ONLINE — Good day, Sir.
echo.
echo   Interface  : http://localhost:8000
echo   Modelo     : mistral:7b (32GB)
echo   API Docs   : http://localhost:8000/docs
echo   Health     : http://localhost:8000/health
echo.
echo   Atalhos do JARVIS:
echo     Ctrl+P  = Templates de Prompt
echo     Ctrl+T  = Lista de Tarefas
echo     Ctrl+F  = Modo Foco
echo     Ctrl+S  = Estatisticas
echo     F2=OSINT  F3=Analise  F4=Arquitetura
echo     F5=Codigo  F6=Resumir  F7=Testes
echo.
echo   Modelo aquecendo... 1a resposta pronta em ~30s.
echo  =============================================
echo.
pause
