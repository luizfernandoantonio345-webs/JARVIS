@echo off
title J.A.R.V.I.S. - Neural Core v6.0
color 0B
cd /d C:\Users\cibernetico\JARVIS

echo.
echo  ============================================
echo   J.A.R.V.I.S. v6.0 - Neural Core
echo   Just A Rather Very Intelligent System
echo  ============================================
echo.

call venv311\Scripts\activate.bat
if errorlevel 1 (
    echo [ERRO] venv311 nao encontrado.
    pause
    exit /b 1
)

echo [1/5] Verificando PC2 Ollama...
curl -s --connect-timeout 4 http://192.168.0.106:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [!] PC2 offline. Inicie o Ollama no PC2 primeiro.
    echo     No PC2: set OLLAMA_HOST=0.0.0.0 ^&^& ollama serve
    echo.
    choice /C YN /M "Continuar mesmo assim?"
    if errorlevel 2 exit /b 1
) else (
    echo [OK] PC2 acessivel com modelos.
)

echo [2/5] Matando instancia anterior...
for /f "tokens=5" %%a in (
    'netstat -ano 2^>nul ^| findstr ":8000 " ^| findstr "LISTENING"'
) do (
    taskkill /PID %%a /F >nul 2>&1
)
timeout /t 2 /nobreak >nul

echo [3/5] Iniciando JARVIS backend...
start "JARVIS-Backend" cmd /k ^
    "cd /d C:\Users\cibernetico\JARVIS && ^
     venv311\Scripts\python.exe -m uvicorn backend.main:app ^
     --host 0.0.0.0 --port 8000 --reload ^
     --log-level info"
timeout /t 6 /nobreak >nul

echo [4/5] Verificando saude...
curl -s http://localhost:8000/health >nul 2>&1
if errorlevel 1 (
    echo [!] Backend ainda iniciando...
    timeout /t 5 /nobreak >nul
)

echo [5/5] Abrindo interface JARVIS...
start "" "http://localhost:8000"

echo.
echo  ============================================
echo   JARVIS ONLINE
echo   Interface : http://localhost:8000
echo   Tailscale : http://100.X.X.X:8000
echo.
echo   Fale com o JARVIS usando o microfone.
echo   O sistema esta ouvindo, Senhor.
echo  ============================================
echo.
