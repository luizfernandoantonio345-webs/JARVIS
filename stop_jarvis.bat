@echo off
title J.A.R.V.I.S. — Parar Sistema
color 04
cd /d "%~dp0"

echo.
echo  =============================================
echo   J.A.R.V.I.S. — ENCERRANDO SISTEMA
echo  =============================================
echo.

:: ── Parar uvicorn na porta 8000 ──────────────────────────────────────────────
echo [..] Encerrando backend JARVIS (porta 8000)...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
    echo [OK] Backend encerrado (PID %%a)
)

:: ── Parar janelas abertas com nome JARVIS ────────────────────────────────────
echo [..] Fechando janelas do JARVIS...
taskkill /FI "WINDOWTITLE eq JARVIS*" /F >nul 2>&1

:: ── Parar Ollama (opcional — comentar se quiser manter Ollama rodando) ───────
:: Descomentar linha abaixo para parar o Ollama também:
:: taskkill /IM ollama.exe /F >nul 2>&1 && echo [OK] Ollama encerrado

:: ── Verificar ─────────────────────────────────────────────────────────────────
timeout /t 2 /nobreak >nul
curl -s --connect-timeout 2 http://localhost:8000/ping >nul 2>&1
if errorlevel 1 (
    echo [OK] JARVIS offline — sistema encerrado.
) else (
    echo [!] JARVIS ainda responde. Pode haver outro processo na porta 8000.
)

echo.
echo  =============================================
echo   Sistema encerrado.
echo   Para reiniciar: start_jarvis.bat
echo  =============================================
echo.
timeout /t 3 /nobreak >nul
