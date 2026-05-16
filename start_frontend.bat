@echo off
title JARVIS Frontend
color 0A
echo ======================================================
echo   JARVIS v5.2 — Frontend Vite
echo   UI:     http://localhost:3000
echo   Proxy → http://localhost:8000
echo ======================================================
cd /d "%~dp0\frontend"

echo [JARVIS] Instalando dependencias...
call npm install --prefer-offline --silent 2>nul || npm install

echo [JARVIS] Iniciando frontend na porta 3000...
call npm run dev

pause
