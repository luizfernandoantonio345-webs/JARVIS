@echo off
title JARVIS Health Check
color 0E
echo ======================================================
echo   JARVIS Health Check
echo ======================================================
cd /d "%~dp0"

set BACKEND=http://localhost:8000
set OLLAMA=http://192.168.0.106:11434

echo.
echo [1/3] Verificando Ollama remoto...
curl -s --connect-timeout 5 "%OLLAMA%/api/tags" >nul 2>&1
if %errorlevel%==0 (
    echo   [OK] Ollama acessivel em %OLLAMA%
) else (
    echo   [FAIL] Ollama INACESSIVEL em %OLLAMA%
)

echo.
echo [2/3] Verificando Backend JARVIS...
curl -s --connect-timeout 5 "%BACKEND%/health" >nul 2>&1
if %errorlevel%==0 (
    echo   [OK] Backend acessivel em %BACKEND%
    curl -s "%BACKEND%/health" | python -c "import sys,json; d=json.load(sys.stdin); print('      Status:', d.get('status'), '| Model:', d.get('models',{}).get('local_model','?'), '| Uptime:', d.get('uptime','?'))" 2>nul
) else (
    echo   [FAIL] Backend OFFLINE em %BACKEND%
    echo   Para iniciar: start_backend.bat
)

echo.
echo [3/3] Verificando Frontend Vite...
curl -s --connect-timeout 3 "http://localhost:3000" >nul 2>&1
if %errorlevel%==0 (
    echo   [OK] Frontend acessivel em http://localhost:3000
) else (
    echo   [WARN] Frontend nao detectado em http://localhost:3000
    echo   Para iniciar: start_frontend.bat
)

echo.
echo ======================================================
echo   Chat endpoint: %BACKEND%/chat
echo   WebSocket:     ws://localhost:8000/ws/jarvis
echo   Ollama models: qwen2:0.5b, tinyllama (fallback)
echo ======================================================
pause
