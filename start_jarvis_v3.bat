@echo off
title JARVIS — Sistema Completo
color 0B
echo ======================================================
echo   JARVIS v5.2 — Iniciando sistema completo
echo ======================================================
cd /d "%~dp0"

:: Mata instancias anteriores na porta 8000
echo [1/3] Liberando porta 8000...
for /f "tokens=5" %%P in ('netstat -ano 2^>nul ^| findstr ":8000"') do (
    taskkill /PID %%P /F >nul 2>&1
)

:: Inicia backend em nova janela
echo [2/3] Iniciando backend...
start "JARVIS Backend" cmd /c "%~dp0start_backend.bat"
timeout /t 8 /nobreak >nul

:: Verifica health
curl -s --connect-timeout 10 "http://localhost:8000/health" >nul 2>&1
if %errorlevel%==0 (
    echo   [OK] Backend ativo
) else (
    echo   [WARN] Backend pode estar ainda inicializando...
)

:: Inicia frontend em nova janela
echo [3/3] Iniciando frontend...
start "JARVIS Frontend" cmd /c "%~dp0start_frontend.bat"
timeout /t 4 /nobreak >nul

echo.
echo ======================================================
echo   JARVIS ONLINE
echo   Frontend: http://localhost:3000
echo   API:      http://localhost:8000
echo   WS:       ws://localhost:8000/ws/jarvis
echo   Health:   http://localhost:8000/health
echo ======================================================
echo   Para verificar: healthcheck.bat
echo ======================================================
pause
