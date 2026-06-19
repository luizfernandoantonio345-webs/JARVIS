@echo off
title J.A.R.V.I.S. — Gerador de Tokens de Acesso
color 0B
cd /d "%~dp0"

echo.
echo  =============================================
echo   J.A.R.V.I.S. — GERAR TOKEN DE ACESSO
echo  =============================================
echo.
echo  Gerando tokens HMAC-SHA256 para seus dispositivos...
echo.

:: ── Obter IP Tailscale ────────────────────────────────────────────────────────
for /f "tokens=*" %%a in ('tailscale ip -4 2^>nul') do set TAILSCALE_IP=%%a
if "%TAILSCALE_IP%"=="" set TAILSCALE_IP=100.110.105.46

:: ── Carregar .env se existir ──────────────────────────────────────────────────
if exist ".env" (
    for /f "usebackq tokens=1,2 delims==" %%a in (".env") do (
        if "%%a"=="JARVIS_SECRET_KEY" set SECRET_KEY=%%b
    )
)
if exist ".env.escola" (
    for /f "usebackq tokens=1,2 delims==" %%a in (".env.escola") do (
        if "%%a"=="JARVIS_SECRET_KEY" set SECRET_KEY=%%b
    )
)

if "%SECRET_KEY%"=="" (
    echo  [ERRO] JARVIS_SECRET_KEY nao encontrada em .env ou .env.escola
    echo.
    echo  Execute primeiro: setup_security.bat
    echo.
    pause
    exit /b 1
)

echo  Chave HMAC: %SECRET_KEY:~0,16%... (truncada para seguranca)
echo.

:: ── Gerar tokens via Python ───────────────────────────────────────────────────
set PYTHON_CMD=python
where python >nul 2>&1 || set PYTHON_CMD=python3

echo  Gerando tokens...
echo.

%PYTHON_CMD% -c "
import hmac, hashlib, time, sys

secret = b'%SECRET_KEY%'
tailscale_ip = '%TAILSCALE_IP%'

def gen(name):
    payload = f'{name}:{int(time.time() // 86400)}'
    return hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()

pc_token = gen('PC_Casa')
iphone_token = gen('iPhone')

print()
print('  == TOKEN PC (Casa) ==')
print(f'  Token: {pc_token}')
print(f'  URL:   http://{tailscale_ip}:8000/?auth={pc_token}')
print()
print('  == TOKEN iPHONE ==')
print(f'  Token: {iphone_token}')
print(f'  URL:   http://{tailscale_ip}:8000/?auth={iphone_token}')
print()
print('  INSTRUCOES:')
print('  1. No celular, abra a URL do iPhone acima via Tailscale')
print('  2. O token e salvo automaticamente no navegador (localStorage)')
print('  3. Todas as requisicoes futuras ja serao autenticadas')
print('  4. Para revogar: acesse /security/token/revoke via API')
print()
" 2>&1

if errorlevel 1 (
    echo  [AVISO] Python nao encontrado. Gerando token manualmente...
    echo.
    echo  Para gerar token sem Python, inicie o JARVIS e acesse:
    echo  POST http://localhost:8000/security/token/generate
    echo  Body: {"device_name": "iPhone"}
    echo.
)

echo  =============================================
echo   SALVE ESTES TOKENS — sao sua senha de acesso
echo   Nao compartilhe com ninguem!
echo  =============================================
echo.
pause
