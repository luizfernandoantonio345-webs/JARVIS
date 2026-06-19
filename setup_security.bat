@echo off
title J.A.R.V.I.S. — Setup de Segurança
color 0B
cd /d "%~dp0"

echo.
echo  =============================================
echo   J.A.R.V.I.S. — CONFIGURAR SEGURANÇA
echo  =============================================
echo.

:: ── 1. Verificar se já tem chave ──────────────────────────────────────────────
set HAS_KEY=0
if exist ".env" (
    for /f "usebackq tokens=1,2 delims==" %%a in (".env") do (
        if "%%a"=="JARVIS_SECRET_KEY" (
            if not "%%b"=="" set HAS_KEY=1
        )
    )
)

if "%HAS_KEY%"=="1" (
    echo  [OK] JARVIS_SECRET_KEY ja existe em .env
    echo.
    set /p REGEN="Deseja gerar uma nova chave? (s/N): "
    if /i not "%REGEN%"=="s" goto :gen_tokens
)

:: ── 2. Gerar chave criptográfica ─────────────────────────────────────────────
echo  Gerando chave HMAC-SHA256 (32 bytes / 256 bits)...
echo.

set PYTHON_CMD=python
where python >nul 2>&1 || set PYTHON_CMD=python3

for /f "usebackq tokens=*" %%k in (`%PYTHON_CMD% -c "import secrets; print(secrets.token_hex(32))"`) do set NEW_KEY=%%k

if "%NEW_KEY%"=="" (
    echo  [ERRO] Nao foi possivel gerar chave — Python nao encontrado.
    echo  Instale Python 3 e tente novamente.
    pause
    exit /b 1
)

echo  Nova chave gerada: %NEW_KEY:~0,16%... (truncada)
echo.

:: ── 3. Criar/atualizar .env ───────────────────────────────────────────────────
if not exist ".env" (
    if exist ".env.escola" (
        copy ".env.escola" ".env" >nul
        echo  .env criado a partir de .env.escola
    ) else (
        echo  # JARVIS Config > ".env"
        echo  JARVIS_HOST=0.0.0.0 >> ".env"
        echo  JARVIS_PORT=8000 >> ".env"
        echo  JARVIS_MODEL=qwen2:0.5b >> ".env"
        echo  JARVIS_OLLAMA_URL=http://127.0.0.1:11434 >> ".env"
        echo  .env criado com configuracao padrao
    )
)

:: Remover linha antiga da chave e adicionar nova
%PYTHON_CMD% -c "
import re, sys
key = '%NEW_KEY%'
try:
    with open('.env', 'r', encoding='utf-8') as f:
        content = f.read()
    # Remove linha existente da chave
    content = re.sub(r'^JARVIS_SECRET_KEY=.*$', '', content, flags=re.MULTILINE)
    content = content.strip() + '\nJARVIS_SECRET_KEY=' + key + '\n'
    with open('.env', 'w', encoding='utf-8') as f:
        f.write(content)
    print('  [OK] Chave salva em .env')
except Exception as e:
    print(f'  [ERRO] {e}')
    sys.exit(1)
"

if errorlevel 1 (
    echo  [FALLBACK] Adicionando chave manualmente...
    echo JARVIS_SECRET_KEY=%NEW_KEY% >> ".env"
)

echo.
echo  [OK] Seguranca configurada!
echo.

:gen_tokens
:: ── 4. Gerar tokens de acesso ────────────────────────────────────────────────
echo  ── Gerando tokens de acesso ─────────────────────────────────────────
echo.
call "%~dp0generate_token.bat"
goto :done

:done
echo.
echo  =============================================
echo   PROXIMOS PASSOS:
echo   1. Inicie o JARVIS: start_jarvis.bat
echo   2. Use a URL com token no iPhone via Tailscale
echo   3. O token fica salvo no browser automaticamente
echo  =============================================
echo.
pause
