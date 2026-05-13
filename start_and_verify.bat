@echo off
REM Start JARVIS backend and verify it works
setlocal enabledelayedexpansion

echo.
echo ===================================================================
echo   JARVIS Backend Server - Start and Verify
echo ===================================================================
echo.

cd /d C:\Users\cibernetico\JARVIS
set JARVIS_DISABLE_VOICE=1

REM Test if already running
echo [1] Checking if server is already running...
C:\Users\cibernetico\JARVIS\.venv\Scripts\python.exe -c "import urllib.request, json; h=urllib.request.urlopen('http://localhost:8000/health', timeout=2).read().decode(); print('OK:'+h)" 2>nul
if %ERRORLEVEL% EQU 0 (
    echo     ^[OK^] Server already running!
    goto :show_urls
)

echo     No server running, starting fresh...
echo.

REM Start the server
echo [2] Starting JARVIS backend...
echo     Using entry point: backend.main:app
echo.

start "JARVIS Backend" cmd /k "set JARVIS_DISABLE_VOICE=1 && C:\Users\cibernetico\JARVIS\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000"

REM Wait for startup
echo [3] Waiting for server to start...
set count=0
:wait_loop
timeout /t 1 /nobreak > nul
set /a count+=1
echo     ... %count%s elapsed

C:\Users\cibernetico\JARVIS\.venv\Scripts\python.exe -c "import urllib.request, json; urllib.request.urlopen('http://localhost:8000/health', timeout=1); print('OK')" 2>nul
if %ERRORLEVEL% EQU 0 (
    echo     ^[OK^] Server online after %count%s!
    echo.
    goto :test_endpoint
)

if %count% LSS 30 goto :wait_loop

echo     [ERROR] Server failed to start
goto :eof

:test_endpoint
echo [4] Testing /process endpoint...
C:\Users\cibernetico\JARVIS\.venv\Scripts\python.exe -c "import urllib.request, json; req=urllib.request.Request('http://localhost:8000/process', data=json.dumps({'command':'echo test'}).encode(), headers={'Content-Type':'application/json'}, method='POST'); r=urllib.request.urlopen(req); print(r.read().decode())" 2>nul

:show_urls
echo.
echo ===================================================================
echo   ^[SUCCESS^] JARVIS Backend is running!
echo ===================================================================
echo.
echo   API Base: http://localhost:8000
echo   API Docs: http://localhost:8000/docs
echo   Health:   http://localhost:8000/health
echo.
echo ===================================================================
