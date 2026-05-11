@echo off
cd /d C:\Users\cibernetico\JARVIS
call .venv\Scripts\activate.bat
echo [JARVIS] Ambiente: .venv (Python 3.14)

echo [JARVIS] Iniciando backend...
start "" "http://localhost:8000/health"
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
