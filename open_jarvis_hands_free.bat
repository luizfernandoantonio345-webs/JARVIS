@echo off
echo ====================================
echo   JARVIS v6.0 — HANDS-FREE ACTIVATION
echo ====================================
echo.
echo [+] Iniciando browser em http://localhost:8000
echo [*] Sistema aguarda escuta de "JARVIS"
echo [*] Após detectar seu nome, fale o comando
echo.
timeout /t 1 >nul
start chrome http://localhost:8000
echo.
echo [✓] Browser aberto!
echo [✓] Sistema pronto para escuta por voz
echo.
echo INSTRUÇÕES:
echo - Orbe azul = aguardando seu nome
echo - Diga "JARVIS" → orbe ativa
echo - Fale seu comando imediatamente após
echo.
pause
