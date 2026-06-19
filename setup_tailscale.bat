@echo off
title J.A.R.V.I.S. — Setup Tailscale (Acesso de Qualquer Lugar)
color 0B
cd /d "%~dp0"

echo.
echo  ================================================================
echo   J.A.R.V.I.S. — GUIA DE ACESSO REMOTO VIA TAILSCALE
echo   Permite acessar o JARVIS de qualquer lugar do mundo, gratis.
echo  ================================================================
echo.

:: ── Verificar se Tailscale esta instalado ────────────────────────────────────
tailscale --version >nul 2>&1
if errorlevel 1 (
    echo  [PASSO 1] Tailscale NAO instalado. Instalando...
    echo.
    winget install Tailscale.Tailscale --silent --accept-package-agreements 2>nul
    if errorlevel 1 (
        echo  [!] winget falhou. Baixe manualmente:
        echo      https://tailscale.com/download/windows
        echo.
        start "" "https://tailscale.com/download/windows"
        echo  Apos instalar, execute este script novamente.
        pause & exit /b 1
    )
    echo  [OK] Tailscale instalado.
    echo  [..] Aguardando inicializacao...
    timeout /t 5 /nobreak >nul
) else (
    echo  [OK] Tailscale ja instalado.
)

:: ── Status do Tailscale ───────────────────────────────────────────────────────
echo.
echo  [..] Status atual do Tailscale:
tailscale status 2>nul
if errorlevel 1 (
    echo  [!] Tailscale nao conectado. Iniciando login...
    tailscale up
)

:: ── Obter IP Tailscale ────────────────────────────────────────────────────────
echo.
for /f "tokens=*" %%a in ('tailscale ip -4 2^>nul') do set TAILSCALE_IP=%%a

if "%TAILSCALE_IP%"=="" (
    echo  [!] Nao foi possivel obter IP Tailscale.
    echo      Certifique-se de estar logado: tailscale up
) else (
    echo  [OK] SEU IP TAILSCALE: %TAILSCALE_IP%

    :: ── Atualizar .env com o IP Tailscale ────────────────────────────────────
    echo  [..] Atualizando .env com IP Tailscale...
    powershell -NoProfile -Command ^
        "(Get-Content '.env' -Raw) -replace 'JARVIS_TAILSCALE_IP=.*', 'JARVIS_TAILSCALE_IP=%TAILSCALE_IP%' | Set-Content '.env'"
    if exist ".env.escola" (
        powershell -NoProfile -Command ^
            "(Get-Content '.env.escola' -Raw) -replace 'JARVIS_TAILSCALE_IP=.*', 'JARVIS_TAILSCALE_IP=%TAILSCALE_IP%' | Set-Content '.env.escola'"
    )
    echo  [OK] .env atualizado.
)

:: ── Instrucoes ────────────────────────────────────────────────────────────────
echo.
echo  ================================================================
echo   COMO ACESSAR O JARVIS DE QUALQUER LUGAR:
echo.
echo   NESTE PC (servidor):
echo   1. Tailscale ja esta instalado e configurado
echo   2. Execute: install_autostart.bat (uma vez, como admin)
echo      O JARVIS vai iniciar automaticamente com o PC
echo.
echo   NO CELULAR / TABLET:
echo   1. Instale Tailscale (App Store ou Google Play) — GRATIS
echo   2. Faca login com a MESMA conta que usou no PC
echo   3. Abra o browser no celular
echo   4. Digite: http://%TAILSCALE_IP%:8000
echo   5. JARVIS aparece — instale como PWA (botao no browser)
echo.
echo   NO PC DA ESCOLA / QUALQUER OUTRO PC:
echo   1. Instale Tailscale (tailscale.com) ou use pelo browser
echo   2. Login com a mesma conta
echo   3. Acesse: http://%TAILSCALE_IP%:8000
echo.
echo   SEM INSTALAR NADA:
echo   Acesse https://login.tailscale.com → "Use Exit Node"
echo   Depois acesse: http://%TAILSCALE_IP%:8000
echo.
echo   VERIFICAR SE ESTA ONLINE:
echo   Execute: status_check.bat
echo  ================================================================
echo.
pause
