@echo off
title J.A.R.V.I.S. — Modo Rede (Acesso de Qualquer Dispositivo)
color 0B
cd /d "%~dp0"

echo.
echo  =============================================
echo   J.A.R.V.I.S. — MODO REDE
echo   Acesso de celular, tablet e qualquer PC
echo  =============================================
echo.

:: ── Carregar config ───────────────────────────────────────────────────────────
if exist ".env.escola" (
    copy /Y ".env.escola" ".env" >nul 2>&1
    echo [OK] Config escola carregada
) else if exist ".env" (
    echo [OK] Usando .env existente
)

set KMP_DUPLICATE_LIB_OK=TRUE
set OMP_NUM_THREADS=4
set PYTHONIOENCODING=utf-8

:: ── Verificar venv ────────────────────────────────────────────────────────────
if not exist "venv311\Scripts\activate.bat" (
    echo [ERR] venv311 nao encontrado! Execute setup_escola.bat primeiro.
    pause & exit /b 1
)
call venv311\Scripts\activate.bat >nul 2>&1

:: ── Verificar Ollama ──────────────────────────────────────────────────────────
curl -s --connect-timeout 3 http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [..] Iniciando Ollama...
    start "" /min ollama serve
    timeout /t 12 /nobreak >nul
)

:: ── Obter IP local ────────────────────────────────────────────────────────────
echo [..] Detectando IP local...
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /C:"IPv4" ^| findstr /V "127.0.0.1" ^| findstr /V "169.254"') do (
    set LOCAL_IP=%%a
    goto :got_ip
)
:got_ip
:: Remover espaço inicial do IP
set LOCAL_IP=%LOCAL_IP: =%

if "%LOCAL_IP%"=="" set LOCAL_IP=localhost

:: ── Encerrar instancia anterior ───────────────────────────────────────────────
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
timeout /t 1 /nobreak >nul

:: ── Criar pastas ──────────────────────────────────────────────────────────────
if not exist "backend\data" mkdir "backend\data"
if not exist "backend\data\tts" mkdir "backend\data\tts"
if not exist "backend\logs" mkdir "backend\logs"

:: ── Iniciar backend ───────────────────────────────────────────────────────────
echo [..] Iniciando JARVIS na rede...
start "JARVIS-Backend-Rede" cmd /k ^
    "cd /d "%~dp0" && ^
     set KMP_DUPLICATE_LIB_OK=TRUE && ^
     set OMP_NUM_THREADS=4 && ^
     set PYTHONIOENCODING=utf-8 && ^
     venv311\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --log-level info"

echo [..] Aguardando backend...
timeout /t 12 /nobreak >nul

:: ── Verificar backend ─────────────────────────────────────────────────────────
curl -s --connect-timeout 5 http://localhost:8000/health >nul 2>&1
if errorlevel 1 (
    echo [!] Backend ainda carregando — aguardando mais 15s...
    timeout /t 15 /nobreak >nul
)

:: ── Gerar QR Code via PowerShell ──────────────────────────────────────────────
echo [..] Gerando QR code para acesso mobile...
powershell -NoProfile -Command ^
    "try { ^
        $url='http://%LOCAL_IP%:8000'; ^
        $qrUrl='https://api.qrserver.com/v1/create-qr-code/?size=200x200&data='+[uri]::EscapeDataString($url); ^
        Invoke-WebRequest -Uri $qrUrl -OutFile 'backend\data\jarvis_qr.png' -ErrorAction Stop; ^
        Write-Host '[OK] QR code salvo em backend\data\jarvis_qr.png'; ^
        Start-Process 'backend\data\jarvis_qr.png' ^
    } catch { Write-Host '[!] Sem internet para gerar QR (normal)' }" 2>nul

:: ── Abrir browser local ───────────────────────────────────────────────────────
start "" "http://localhost:8000"

:: ── Exibir informações de acesso ─────────────────────────────────────────────
echo.
echo  =============================================
echo   J.A.R.V.I.S. ONLINE — MODO REDE
echo.
echo   ESTE PC:    http://localhost:8000
echo   REDE LOCAL: http://%LOCAL_IP%:8000
echo.
echo   PARA ACESSAR DO CELULAR/TABLET:
echo   1. Conecte o celular na MESMA rede Wi-Fi
echo   2. Abra o navegador no celular
echo   3. Digite: http://%LOCAL_IP%:8000
echo   4. Instale como PWA: menu do browser → "Adicionar à tela inicial"
echo.
echo   ACESSO REMOTO (fora da rede):
echo   Use Tailscale: https://tailscale.com (gratuito)
echo   Depois acesse: http://[SEU-IP-TAILSCALE]:8000
echo.
echo   Docs API:  http://%LOCAL_IP%:8000/docs
echo   Health:    http://%LOCAL_IP%:8000/health
echo   Rede:      http://%LOCAL_IP%:8000/network
echo  =============================================
echo.
pause
