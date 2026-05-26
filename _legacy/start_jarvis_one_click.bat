@echo off
setlocal
title JARVIS - Inicio Rapido (1 clique)
color 0A

set "ROOT=%~dp0"
cd /d "%ROOT%"

echo.
echo ==============================================
echo   JARVIS - INICIO RAPIDO (1 CLIQUE)
echo ==============================================
echo.

echo [1/3] Iniciando JARVIS...
call "%ROOT%start_jarvis.bat"

echo.
echo [2/3] Aguardando 20s para o warmup do modelo completar...
timeout /t 20 /nobreak >nul

echo.
echo [3/3] Validando stack local (chat + audio + modelo)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%final_validation.ps1"
set "VALIDATION_EXIT=%ERRORLEVEL%"

echo.
if "%VALIDATION_EXIT%"=="0" (
  echo [OK] JARVIS pronto para uso.
  echo      Interface: http://localhost:8000
) else (
  echo [WARN] Validacao retornou falha. Verifique a saida acima.
  echo        Dica: rode novamente final_validation.ps1 apos 20-30s.
  pause
)

endlocal