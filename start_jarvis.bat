@echo off
cd /d C:\Users\cibernetico\JARVIS
echo [JARVIS] Ativando venv311...
call venv311\Scripts\activate.bat

echo [JARVIS] Iniciando backend...
start "JARVIS Backend" cmd /k "venv311\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload"

echo [JARVIS] Aguardando backend...
timeout /t 3 /nobreak

echo [JARVIS] Iniciando frontend...
start "JARVIS Frontend" cmd /k "cd frontend && npm run dev"

echo [JARVIS] Aguardando frontend...
timeout /t 4 /nobreak

echo [JARVIS] Abrindo interface...
start "" "http://localhost:3000"

echo [JARVIS] Sistema online. Fale JARVIS.
