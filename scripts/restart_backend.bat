@echo off
for /f "tokens=5" %%a in ('netstat -ano ^| find ":8000" ^| find "LISTENING"') do (
  echo Killing PID %%a
  taskkill /PID %%a /F >nul 2>&1
)
cd /d C:\Users\cibernetico\JARVIS
start "JARVIS Backend" /B "C:\Users\cibernetico\JARVIS\venv311\Scripts\python.exe" -u -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload --log-level info
ping -n 6 127.0.0.1 >nul
python -c "import requests, json; r=requests.get('http://localhost:8000/health', timeout=20); print(r.status_code); print(json.dumps(r.json(), ensure_ascii=False))"
