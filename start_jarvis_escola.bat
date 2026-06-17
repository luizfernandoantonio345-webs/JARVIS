@echo off
title J.A.R.V.I.S. v6.0 — ESCOLA (32GB / Ryzen 7)
color 0B
cd /d "%~dp0"

echo.
echo  =============================================
echo   J.A.R.V.I.S. — Neural Core v6.0
echo   Configuracao: PC Escola  [32GB / Ryzen 7]
echo  =============================================
echo.

:: ── [0] Carregar .env.escola como .env ─────────────────────────────────────
if exist ".env.escola" (
    copy /Y ".env.escola" ".env" >nul 2>&1
    echo [OK] .env.escola carregado como .env
) else (
    echo [!] .env.escola nao encontrado — usando .env atual
)

:: ── Variáveis de ambiente ───────────────────────────────────────────────────
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

:: ── [1] Verificar venv ──────────────────────────────────────────────────────
call venv311\Scripts\activate.bat >nul 2>&1
if errorlevel 1 (
    echo [ERR] venv311 nao encontrado.
    echo       Execute: python -m venv venv311
    echo       Depois:  venv311\Scripts\pip install -r backend\requirements.txt
    pause & exit /b 1
)
echo [OK] venv311 ativo

:: ── [2] Verificar/iniciar Ollama ────────────────────────────────────────────
echo [..] Verificando Ollama...
curl -s --connect-timeout 3 http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [..] Iniciando Ollama...
    start "" /min ollama serve
    echo [..] Aguardando Ollama inicializar (15s)...
    timeout /t 15 /nobreak >nul
    curl -s --connect-timeout 5 http://127.0.0.1:11434/api/tags >nul 2>&1
    if errorlevel 1 (
        echo [!] Ollama nao respondeu. Verifique: winget install Ollama.Ollama
    ) else (
        echo [OK] Ollama online.
    )
) else (
    echo [OK] Ollama online.
)

:: ── [3] Verificar se mistral:7b esta instalado ──────────────────────────────
echo [..] Verificando mistral:7b...
ollama list 2>nul | findstr /I "mistral:7b" >nul 2>&1
if errorlevel 1 (
    echo [..] mistral:7b nao encontrado. Baixando (~4.1GB)...
    echo      Isso pode demorar varios minutos na primeira vez.
    ollama pull mistral:7b
    if errorlevel 1 (
        echo [!] Falha ao baixar mistral:7b. Tentando llama3.2:3b como fallback...
        ollama pull llama3.2:3b
        set JARVIS_MODEL=llama3.2:3b
    ) else (
        echo [OK] mistral:7b instalado.
    )
) else (
    echo [OK] mistral:7b disponivel.
)

:: ── [4] Encerrar instancia anterior do backend ──────────────────────────────
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
timeout /t 1 /nobreak >nul

:: ── [5] Iniciar backend ─────────────────────────────────────────────────────
echo [..] Iniciando JARVIS backend...
start "JARVIS-Backend-Escola" cmd /k "cd /d "%~dp0" && set KMP_DUPLICATE_LIB_OK=TRUE && set OMP_NUM_THREADS=4 && set OLLAMA_HOST=127.0.0.1:11434 && set OLLAMA_KEEP_ALIVE=60m && set JARVIS_MODEL=mistral:7b && set JARVIS_TOTAL_RAM_GB=32 && venv311\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --log-level warning"

:: Aguardar backend inicializar
echo [..] Aguardando backend (12s)...
timeout /t 12 /nobreak >nul
curl -s --connect-timeout 5 http://localhost:8000/health >nul 2>&1
if errorlevel 1 (
    echo [!] Backend ainda inicializando — aguardando mais 10s...
    timeout /t 10 /nobreak >nul
)
echo [OK] Backend online.

:: ── [6] Pre-aquecimento do modelo (elimina cold start na 1a mensagem) ────────
echo [..] Pre-aquecendo mistral:7b em background (pode levar 30-60s)...
start "" /min cmd /c "curl -s --max-time 120 -X POST http://127.0.0.1:11434/api/generate -d \"{\"\"model\"\":\"\"mistral:7b\"\",\"\"prompt\"\":\"\"hi\"\",\"\"stream\"\":false,\"\"keep_alive\"\":\"\"60m\"\"}\" >nul 2>&1"

:: ── [7] Abrir interface ──────────────────────────────────────────────────────
start "" "http://localhost:8000"

echo.
echo  =============================================
echo   JARVIS ONLINE — Good day, Sir.
echo.
echo   Interface : http://localhost:8000
echo   Modelo    : mistral:7b (32GB mode)
echo   Backend   : http://localhost:8000/health
echo.
echo   Modelo aquecendo em background...
echo   1a resposta pronta em ~30-60s.
echo  =============================================
echo.
pause
