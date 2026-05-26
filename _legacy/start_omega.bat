@echo off
title JARVIS OMEGA v6.0 — PC1 Local
color 0B
cd /d C:\Users\cibernetico\JARVIS

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║        JARVIS OMEGA v6.0                ║
echo  ║   AI Operating System — PC1 Only       ║
echo  ║   Backend: FastAPI + Ollama Local      ║
echo  ╚══════════════════════════════════════════╝
echo.

echo [1/4] Verificando Ollama local (localhost:11434)...
curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [AVISO] Ollama offline — iniciando servico...
    start "OLLAMA" cmd /c "ollama serve"
    timeout /t 5 /nobreak >nul
) else (
    echo [OK] Ollama online
)

echo [2/4] Limpando portas 8000 e 3000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000 " ^| findstr "LISTENING"') do taskkill /f /pid %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3000 " ^| findstr "LISTENING"') do taskkill /f /pid %%a >nul 2>&1

echo [3/4] Ativando venv311 e iniciando Backend JARVIS...
start "JARVIS-Backend" cmd /k "cd /d C:\Users\cibernetico\JARVIS && .\venv311\Scripts\activate.bat && python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --log-level info"

timeout /t 5 /nobreak >nul

echo [4/4] Iniciando Frontend React...
start "JARVIS-Frontend" cmd /k "cd /d C:\Users\cibernetico\JARVIS\frontend && npm run dev"

timeout /t 4 /nobreak >nul

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║   JARVIS OMEGA v6.0 INICIANDO           ║
echo  ║   Backend:  http://localhost:8000       ║
echo  ║   Frontend: http://localhost:3000       ║
echo  ║   WebSocket: ws://localhost:8000/ws     ║
echo  ║   Aguarde 10s para o frontend iniciar   ║
echo  ╚══════════════════════════════════════════╝
echo.

timeout /t 10 /nobreak >nul

start "" "http://localhost:3000"

echo.
echo  ═══════════════════════════════════════════════════════════
echo  ✅ JARVIS OMEGA Online! Verifique os terminais abertos.
echo  🔊 Máquina deve estar com Ollama rodando em localhost:11434
echo  📊 Smoke test: python smoke_final.py
echo  ═══════════════════════════════════════════════════════════
echo.

pause
