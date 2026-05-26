@echo off
setlocal enabledelayedexpansion

echo.
echo ════════════════════════════════════════════════════════════
echo  JARVIS — TESTE COMPLETO TIER 1 + TIER 2
echo ════════════════════════════════════════════════════════════
echo.

cd /d C:\Users\cibernetico\JARVIS

REM Iniciar sistema
echo [TESTE] Iniciando sistema...
call start_jarvis.bat

echo.
echo [TESTE] Aguardando inicialização (8 segundos)...
timeout /t 8 /nobreak

echo.
echo [TESTE] Testando health check...
curl -s http://localhost:8000/health > nul && echo ✅ Backend respondendo || echo ❌ Backend offline

echo.
echo ════════════════════════════════════════════════════════════
echo  TESTE MANUAL REQUERIDO
echo ════════════════════════════════════════════════════════════
echo.
echo 1. Navegador deve abrir automaticamente em localhost:3000
echo 2. VERIFICAR:
echo    ✓ Orbe azul pulsante no centro
echo    ✓ Label JARVIS
echo    ✓ Botão ❤️ (tema) no canto superior direito
echo.
echo 3. TESTAR FUNCIONALIDADES:
echo    A. Pressionar ESPAÇO para abrir input
echo    B. Digitar "oi ja" → deve mostrar sugestões
echo    C. Selecionar sugestão → orbe fica amarelo (thinking)
echo    D. Aguardar resposta → orbe fica verde (success)
echo    E. Verificar histórico (w4) com comando registrado
echo    F. Clicar em ❤️ → tema muda para vermelho/ouro
echo    G. Audio deve tocar com resposta (TTS)
echo.
echo 4. PAINÉIS (pressionar 1-4):
echo    1 = Código    2 = Anomalias   3 = Flow    4 = Histórico
echo.
echo ════════════════════════════════════════════════════════════
pause
