@echo off
for /f "tokens=5" %%a in ('netstat -ano ^| find ":8000" ^| find "LISTENING"') do taskkill /F /PID %%a >nul 2>&1
cd /d C:\Users\cibernetico\JARVIS
start "JARVIS Backend" /B "C:\Users\cibernetico\JARVIS\venv311\Scripts\python.exe" -u -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload --log-level info
ping -n 11 127.0.0.1 >nul
C:\Users\cibernetico\JARVIS\venv311\Scripts\python.exe C:\Users\cibernetico\JARVIS\scripts\check_health.py
