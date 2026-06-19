@echo off
title J.A.R.V.I.S. — Status Check
color 0B
cd /d "%~dp0"

echo.
echo  =============================================
echo   J.A.R.V.I.S. — STATUS DO SISTEMA
echo  =============================================
echo.

:: ── Obter IP local ────────────────────────────────────────────────────────────
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /C:"IPv4" ^| findstr /V "127.0.0.1" ^| findstr /V "169.254"') do (
    set LOCAL_IP=%%a
    goto :got_lan
)
:got_lan
set LOCAL_IP=%LOCAL_IP: =%

:: ── Obter IP Tailscale ────────────────────────────────────────────────────────
for /f "tokens=*" %%a in ('tailscale ip -4 2^>nul') do set TAILSCALE_IP=%%a
if "%TAILSCALE_IP%"=="" set TAILSCALE_IP=nao_configurado

:: ── Verificar servicos ────────────────────────────────────────────────────────
echo  Verificando servicos...
echo.

:: Backend JARVIS
curl -s --connect-timeout 3 http://localhost:8000/ping >nul 2>&1
if errorlevel 1 (
    echo  [OFFLINE] JARVIS Backend       http://localhost:8000
) else (
    echo  [ONLINE ] JARVIS Backend       http://localhost:8000
)

:: Ollama
curl -s --connect-timeout 3 http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo  [OFFLINE] Ollama LLM           http://localhost:11434
) else (
    echo  [ONLINE ] Ollama LLM           http://localhost:11434
)

:: Tailscale
tailscale status >nul 2>&1
if errorlevel 1 (
    echo  [OFFLINE] Tailscale VPN        nao conectado
) else (
    echo  [ONLINE ] Tailscale VPN        IP: %TAILSCALE_IP%
)

echo.
echo  ── URLs de Acesso ─────────────────────────────────────────────
echo.
echo  Local:      http://localhost:8000
echo  Rede Wi-Fi: http://%LOCAL_IP%:8000
if not "%TAILSCALE_IP%"=="nao_configurado" (
    echo  Tailscale:  http://%TAILSCALE_IP%:8000   [qualquer lugar]
)
echo.
echo  ── Health Check ───────────────────────────────────────────────
curl -s --connect-timeout 3 http://localhost:8000/health 2>nul
echo.
echo.

:: ── Modelo carregado ──────────────────────────────────────────────────────────
echo  ── Modelo Ollama ──────────────────────────────────────────────
ollama list 2>nul | findstr /V "NAME" | findstr /V "^$"
echo.

:: ── Uso de recursos ───────────────────────────────────────────────────────────
echo  ── Recursos do Sistema ────────────────────────────────────────
curl -s --connect-timeout 3 http://localhost:8000/metrics 2>nul | ^
    powershell -NoProfile -Command ^
    "$j=($input|ConvertFrom-Json -ErrorAction SilentlyContinue); ^
     if($j){Write-Host \"CPU: $($j.cpu_percent)%  RAM: $($j.ram_percent)%  Disco: $($j.disk_percent)%\"}"
echo.

echo  =============================================
echo   Para iniciar:  start_jarvis.bat
echo   Para parar:    stop_jarvis.bat
echo   Para rede:     start_jarvis_rede.bat
echo  =============================================
echo.
pause
