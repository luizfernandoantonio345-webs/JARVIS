@echo off
title JARVIS Backend
color 0B
echo ======================================================
echo   JARVIS v5.2 — Backend FastAPI + Ollama Remoto
echo   Ollama: http://192.168.0.106:11434
echo   API:    http://localhost:8000
echo   WS:     ws://localhost:8000/ws/jarvis
echo ======================================================
cd /d "%~dp0"

:: Ativa venv se existir
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else if exist "venv311\Scripts\activate.bat" (
    call venv311\Scripts\activate.bat
)

:: Carrega variáveis do .env
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        if not "%%A"=="" if not "%%A:~0,1%"=="#" set "%%A=%%B"
    )
)

echo [JARVIS] Iniciando backend na porta 8000...
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload --log-level info

pause
