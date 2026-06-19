@echo off
title J.A.R.V.I.S. — Setup PC Escola (Executa 1x)
color 0A
cd /d "%~dp0"

echo.
echo  ============================================================
echo   J.A.R.V.I.S. — INSTALACAO COMPLETA PC ESCOLA
echo   Execute este script UMA VEZ antes de usar o JARVIS.
echo   Requer: Python 3.11+, conexao com internet.
echo  ============================================================
echo.

:: ── [0] Verificar Python 3.11+ ──────────────────────────────────────────────
echo [1/7] Verificando Python...
python --version 2>nul | findstr /C:"Python 3" >nul
if errorlevel 1 (
    echo [ERR] Python nao encontrado!
    echo.
    echo  SOLUCAO: Instale Python 3.11+ em https://python.org/downloads
    echo  Marque "Add Python to PATH" durante a instalacao.
    echo.
    pause & exit /b 1
)
python --version
echo [OK] Python encontrado.

:: ── [1] Verificar/instalar Ollama ───────────────────────────────────────────
echo.
echo [2/7] Verificando Ollama...
ollama --version >nul 2>&1
if errorlevel 1 (
    echo [..] Ollama nao instalado. Instalando via winget...
    winget install Ollama.Ollama --silent --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo [!] winget falhou. Baixe manualmente em: https://ollama.ai/download
        echo     Depois de instalar, feche e reabra este script.
        pause & exit /b 1
    )
    echo [OK] Ollama instalado.
) else (
    echo [OK] Ollama ja instalado.
)

:: ── [2] Criar venv311 ────────────────────────────────────────────────────────
echo.
echo [3/7] Criando ambiente virtual Python (venv311)...
if exist "venv311\Scripts\activate.bat" (
    echo [OK] venv311 ja existe.
) else (
    python -m venv venv311
    if errorlevel 1 (
        echo [ERR] Falha ao criar venv311!
        echo  Tente: python -m pip install virtualenv
        pause & exit /b 1
    )
    echo [OK] venv311 criado.
)

:: ── [3] Instalar dependencias Python ─────────────────────────────────────────
echo.
echo [4/7] Instalando dependencias Python (pode demorar 5-10min)...
call venv311\Scripts\activate.bat >nul 2>&1

:: Atualizar pip primeiro
venv311\Scripts\python.exe -m pip install --upgrade pip --quiet

:: Instalar requirements
venv311\Scripts\pip.exe install -r backend\requirements.txt --quiet
if errorlevel 1 (
    echo [!] Algumas dependencias falharam. Tentando instalacao individual...
    venv311\Scripts\pip.exe install fastapi uvicorn pydantic httpx aiofiles psutil --quiet
    venv311\Scripts\pip.exe install edge-tts sounddevice soundfile --quiet
    venv311\Scripts\pip.exe install chromadb sentence-transformers --quiet
    venv311\Scripts\pip.exe install ollama cryptography python-multipart --quiet
)
echo [OK] Dependencias instaladas.

:: ── [4] Criar pastas de dados ─────────────────────────────────────────────────
echo.
echo [5/7] Criando estrutura de dados...
if not exist "backend\data" mkdir "backend\data"
if not exist "backend\logs" mkdir "backend\logs"
if not exist "backend\data\chroma" mkdir "backend\data\chroma"
if not exist "backend\memory" mkdir "backend\memory"
echo [OK] Pastas criadas.

:: ── [5] Copiar config escola ──────────────────────────────────────────────────
echo.
echo [6/7] Configurando ambiente escola...
copy /Y ".env.escola" ".env" >nul 2>&1
echo [OK] Config escola ativa (.env.escola → .env).

:: ── [6] Baixar mistral:7b ─────────────────────────────────────────────────────
echo.
echo [7/7] Baixando modelo mistral:7b (~4.1 GB)...
echo  Isso pode demorar 10-30 minutos dependendo da internet.
echo  Progresso aparecera abaixo:
echo.

:: Iniciar Ollama se nao estiver rodando
curl -s --connect-timeout 3 http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [..] Iniciando Ollama...
    start "" /min ollama serve
    timeout /t 8 /nobreak >nul
)

ollama pull mistral:7b
if errorlevel 1 (
    echo [!] mistral:7b falhou. Baixando llama3.2:3b como alternativa...
    ollama pull llama3.2:3b
    echo [!] Use llama3.2:3b — edite .env e mude JARVIS_MODEL=llama3.2:3b
) else (
    echo [OK] mistral:7b pronto!
)

:: ── Verificacao final ─────────────────────────────────────────────────────────
echo.
echo  ============================================================
echo   VERIFICACAO FINAL
echo  ============================================================

:: Testar Python
venv311\Scripts\python.exe -c "import fastapi, uvicorn, pydantic; print('[OK] FastAPI stack OK')" 2>nul || echo [!] FastAPI nao instalado

:: Testar Ollama
curl -s --connect-timeout 5 http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (echo [!] Ollama nao respondendo) else (echo [OK] Ollama online)

:: Testar modelo
ollama list 2>nul | findstr /I "mistral:7b" >nul && echo [OK] mistral:7b disponivel || echo [!] mistral:7b nao encontrado

echo.
echo  ============================================================
echo   SETUP CONCLUIDO!
echo.
echo   Agora use: start_jarvis_escola.bat  para iniciar o JARVIS.
echo  ============================================================
echo.
pause
