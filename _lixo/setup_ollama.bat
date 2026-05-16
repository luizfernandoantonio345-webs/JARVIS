@echo off
REM Script para iniciar Ollama e baixar modelo para JARVIS

echo.
echo ================================================================
echo  JARVIS — OLLAMA SETUP
echo ================================================================
echo.

echo [1/4] Verificando Ollama...
ollama --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Ollama nao encontrado. Instale em ollama.ai
    pause
    exit /b 1
)
echo [OK] Ollama disponivel

echo.
echo [2/4] Iniciando servico Ollama...
start "Ollama Service" cmd /k "ollama serve"
timeout /t 3 /nobreak

echo.
echo [3/4] Aguardando Ollama ficar online...
:waitloop
timeout /t 1 /nobreak >nul
ollama list >nul 2>&1
if errorlevel 1 goto waitloop
echo [OK] Ollama online

echo.
echo [4/4] Verificando modelo...
ollama list | find "neural-chat" >nul 2>&1
if errorlevel 1 (
    echo [BAIXANDO] Modelo neural-chat (pode levar alguns minutos)...
    echo [INFO] Primeiro acesso: aguarde ~4GB download
    ollama pull neural-chat
    echo [OK] Modelo pronto!
) else (
    echo [OK] Modelo neural-chat ja disponivel
)

echo.
echo ================================================================
echo  OLLAMA PRONTO!
echo ================================================================
echo.
echo Ollama esta rodando em http://localhost:11434
echo Modelo: neural-chat
echo.
echo Proxima etapa: Iniciar JARVIS com start_jarvis.bat
echo.
pause
