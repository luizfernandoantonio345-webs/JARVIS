@echo off
title J.A.R.V.I.S. — Instalar Auto-Start no Windows
color 0A
cd /d "%~dp0"

echo.
echo  =============================================
echo   J.A.R.V.I.S. — INSTALAR INICIO AUTOMATICO
echo   O JARVIS vai iniciar sozinho quando o PC ligar.
echo  =============================================
echo.

:: ── Verificar permissao de administrador ─────────────────────────────────────
net session >nul 2>&1
if errorlevel 1 (
    echo [ERR] Este script precisa ser executado como ADMINISTRADOR.
    echo.
    echo  SOLUCAO: Clique com botao direito neste arquivo
    echo           e selecione "Executar como administrador"
    echo.
    pause & exit /b 1
)
echo [OK] Executando como administrador.

:: ── Caminho absoluto do JARVIS ────────────────────────────────────────────────
set "JARVIS_DIR=%~dp0"
:: Remover barra final
if "%JARVIS_DIR:~-1%"=="\" set "JARVIS_DIR=%JARVIS_DIR:~0,-1%"

echo [..] Diretorio JARVIS: %JARVIS_DIR%

:: ── Criar script de inicializacao silenciosa ──────────────────────────────────
echo [..] Criando script de boot silencioso...
set "BOOT_SCRIPT=%JARVIS_DIR%\start_jarvis_boot.bat"

(
echo @echo off
echo cd /d "%JARVIS_DIR%"
echo set KMP_DUPLICATE_LIB_OK=TRUE
echo set OMP_NUM_THREADS=4
echo set PYTHONIOENCODING=utf-8
echo.
echo :: Aguardar 30s para rede inicializar apos boot
echo timeout /t 30 /nobreak ^>nul
echo.
echo :: Copiar config
echo if exist ".env.escola" copy /Y ".env.escola" ".env" ^>nul 2^>^&1
echo.
echo :: Iniciar Ollama
echo start "" /min ollama serve
echo timeout /t 15 /nobreak ^>nul
echo.
echo :: Criar pastas necessarias
echo if not exist "backend\data" mkdir "backend\data"
echo if not exist "backend\data\tts" mkdir "backend\data\tts"
echo if not exist "backend\logs" mkdir "backend\logs"
echo.
echo :: Iniciar JARVIS backend (silencioso, sem janela)
echo venv311\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --log-level info ^>^> backend\logs\jarvis_boot.log 2^>^&1
) > "%BOOT_SCRIPT%"

echo [OK] Script criado: %BOOT_SCRIPT%

:: ── Remover task antiga se existir ────────────────────────────────────────────
schtasks /delete /tn "JARVIS_AutoStart" /f >nul 2>&1

:: ── Criar Task Scheduler ──────────────────────────────────────────────────────
echo [..] Registrando no Task Scheduler do Windows...

schtasks /create ^
  /tn "JARVIS_AutoStart" ^
  /tr "cmd.exe /c \"%BOOT_SCRIPT%\"" ^
  /sc ONLOGON ^
  /ru "%USERNAME%" ^
  /delay 0000:30 ^
  /f ^
  >nul 2>&1

if errorlevel 1 (
    echo [!] Falha com ONLOGON. Tentando ONSTART...
    schtasks /create ^
      /tn "JARVIS_AutoStart" ^
      /tr "cmd.exe /c \"%BOOT_SCRIPT%\"" ^
      /sc ONSTART ^
      /ru SYSTEM ^
      /delay 0000:45 ^
      /f ^
      >nul 2>&1
)

if errorlevel 1 (
    echo [ERR] Nao foi possivel criar a task.
    echo.
    echo  ALTERNATIVA: Adicionar %BOOT_SCRIPT% ao startup manual:
    echo    Win+R → shell:startup → colar atalho do script
    pause & exit /b 1
)

echo [OK] Task "JARVIS_AutoStart" criada no Task Scheduler.

:: ── Verificar task criada ─────────────────────────────────────────────────────
echo.
echo [..] Verificando task criada:
schtasks /query /tn "JARVIS_AutoStart" /fo LIST 2>nul | findstr /C:"Task Name" /C:"Status" /C:"Next Run"

echo.
echo  =============================================
echo   SUCESSO! JARVIS vai iniciar automaticamente
echo.
echo   O que acontece quando o PC ligar:
echo   1. Windows inicia
echo   2. Aguarda 30s (rede subir)
echo   3. Inicia Ollama automaticamente
echo   4. Inicia JARVIS na porta 8000
echo   5. Acessivel via Tailscale de qualquer lugar
echo.
echo   Para verificar: http://localhost:8000/health
echo   Para parar:     stop_jarvis.bat
echo   Para desativar: schtasks /delete /tn JARVIS_AutoStart /f
echo  =============================================
echo.
pause
