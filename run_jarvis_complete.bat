@echo off
REM Master script para iniciar JARVIS + Ollama completo

cd /d C:\Users\cibernetico\JARVIS

echo.
echo ════════════════════════════════════════════════════════════════
echo  JARVIS — INITIALIZATION MASTER
echo ════════════════════════════════════════════════════════════════
echo.

REM Verificar Ollama
echo [1/5] Verificando Ollama...
ollama --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Ollama nao instalado
    echo [INFO] Instale em: https://ollama.ai
    echo [INFO] Depois execute: setup_ollama.bat
    pause
    exit /b 1
)
echo [OK] Ollama disponivel

REM Verificar modelo
echo [2/5] Verificando modelo neural-chat...
ollama list | find "neural-chat" >nul 2>&1
if errorlevel 1 (
    echo [AVISO] Modelo nao encontrado
    echo [INFO] Execute setup_ollama.bat para baixar
    echo.
    call setup_ollama.bat
)
echo [OK] Modelo disponivel

REM Iniciar Ollama
echo [3/5] Iniciando Ollama em background...
tasklist | find "ollama" >nul 2>&1
if errorlevel 1 (
    echo [INICIANDO] Ollama serve...
    start "Ollama Service" cmd /k "ollama serve"
    timeout /t 2 /nobreak
)
echo [OK] Ollama rodando

REM Ativar venv
echo [4/5] Ativando venv311...
call venv311\Scripts\activate.bat >nul 2>&1
if errorlevel 1 (
    call .venv\Scripts\activate.bat
)
echo [OK] venv ativo

REM Iniciar backend
echo [5/5] Iniciando backend FastAPI...
start "JARVIS Backend" cmd /k "python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload"
timeout /t 2 /nobreak

REM Iniciar frontend
echo [6/6] Iniciando frontend Vite...
start "JARVIS Frontend" cmd /k "cd frontend && npm run dev"
timeout /t 4 /nobreak

REM Abrir navegador
echo [7/7] Abrindo localhost:3000...
start "" "http://localhost:3000"

echo.
echo ════════════════════════════════════════════════════════════════
echo  JARVIS INICIALIZADO!
echo ════════════════════════════════════════════════════════════════
echo.
echo Frontend: http://localhost:3000
echo Backend:  http://localhost:8000
echo Ollama:   http://localhost:11434
echo.
echo JARVIS esta pronto. Fale com ele!
echo.
pause
