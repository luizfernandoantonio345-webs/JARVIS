@echo off
REM JARVIS OMEGA v6.0 — gerado automaticamente
title JARVIS OMEGA v6.0
color 0B
cd /d C:\Users\cibernetico\JARVIS

echo.
echo  ╔══════════════════════════════════════╗
echo  ║        JARVIS OMEGA v6.0            ║
echo  ║   AI Operating System — PC1 Only   ║
echo  ╚══════════════════════════════════════╝
echo.

echo [1/4] Verificando Ollama local...
curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [AVISO] Ollama offline — iniciando...
    start "OLLAMA" cmd /c "ollama serve"
    timeout /t 5 /nobreak >nul
) else (
    echo [OK] Ollama online
)

echo [2/4] Limpando portas...
REM Prevenir crash forrtl Intel MKL/OpenBLAS com numpy/faster_whisper
set KMP_DUPLICATE_LIB_OK=TRUE
set OMP_NUM_THREADS=1
set KMP_WARNINGS=FALSE
set OPENBLAS_NUM_THREADS=1
set MKL_NUM_THREADS=1
set PYTHONIOENCODING=utf-8
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000 " ^| findstr "LISTENING"') do taskkill /f /pid %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3000 " ^| findstr "LISTENING"') do taskkill /f /pid %%a >nul 2>&1

echo [3/4] Iniciando Backend JARVIS...
start "JARVIS-Backend" cmd /k "cd /d C:\Users\cibernetico\JARVIS && set KMP_DUPLICATE_LIB_OK=TRUE && set OMP_NUM_THREADS=1 && set OPENBLAS_NUM_THREADS=1 && venv311\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --log-level info"

timeout /t 5 /nobreak >nul

echo [4/4] Iniciando Frontend...
start "JARVIS-Frontend" cmd /k "cd /d C:\Users\cibernetico\JARVIS\frontend && npm run dev"

timeout /t 4 /nobreak >nul

start "" "http://localhost:3000"

echo.
echo  ╔══════════════════════════════════════╗
echo  ║   JARVIS OMEGA ONLINE               ║
echo  ║   Backend:  http://localhost:8000   ║
echo  ║   Frontend: http://localhost:3000   ║
echo  ╚══════════════════════════════════════╝
echo.
pause
