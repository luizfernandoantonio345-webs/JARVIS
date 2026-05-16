@echo off
title JARVIS - Sistema Neural v6.0
color 0B
cd /d C:\Users\cibernetico\JARVIS

echo.
echo  ==========================================
echo   JARVIS - Just A Rather Very Intelligent
echo            System - v6.0 PRODUCTION
echo  ==========================================
echo.

call venv311\Scripts\activate.bat

echo [1/4] Verificando PC2 (Ollama)...
curl -s --connect-timeout 3 http://192.168.0.106:11434/api/tags >nul 2>&1
if errorlevel 1 (
  echo [!] AVISO: PC2 offline. JARVIS sobe em modo degradado.
) else (
  echo [OK] PC2 acessivel.
)

echo [2/4] Iniciando backend FastAPI...
start "JARVIS-Backend" cmd /k "cd /d C:\Users\cibernetico\JARVIS && venv311\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload --log-level info"
timeout /t 5 /nobreak >nul

echo [3/4] Iniciando frontend Vite...
start "JARVIS-Frontend" cmd /k "cd /d C:\Users\cibernetico\JARVIS\frontend && npm run dev"
timeout /t 5 /nobreak >nul

echo [4/4] Abrindo interface...
start "" "http://localhost:3000"

echo.
echo  ==========================================
echo   JARVIS ONLINE
echo   Backend : http://localhost:8000/health
echo   Frontend: http://localhost:3000
echo   Ollama  : http://192.168.0.106:11434
echo   Status  : SYSTEMS OPERATIONAL
echo  ==========================================
echo.

