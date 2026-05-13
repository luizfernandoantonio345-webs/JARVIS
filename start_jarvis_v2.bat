@echo off
setlocal enabledelayedexpansion
cd /d C:\Users\cibernetico\JARVIS

echo ============================================================
echo  JARVIS AI Backend Launcher v2.0
echo ============================================================

set PYTHON=C:\Users\cibernetico\JARVIS\.venv\Scripts\python.exe
set LOGFILE=C:\Users\cibernetico\JARVIS\backend\logs\uvicorn.log
set PORT=8000

:: Ensure logs directory exists
if not exist "C:\Users\cibernetico\JARVIS\backend\logs" (
    mkdir "C:\Users\cibernetico\JARVIS\backend\logs"
    echo [JARVIS] Logs dir created.
)

:: Check Python venv exists
if not exist "%PYTHON%" (
    echo [ERROR] Python venv not found at: %PYTHON%
    echo         Create venv: python -m venv .venv
    pause
    exit /b 1
)

echo [JARVIS] Python: %PYTHON%

:: Check if port 8000 is already in use
netstat -ano | findstr ":%PORT% " | findstr "LISTEN" >nul 2>&1
if %errorlevel%==0 (
    echo [JARVIS] Port %PORT% already in use. Checking if JARVIS is healthy...
    %PYTHON% -c "import urllib.request; print(urllib.request.urlopen('http://localhost:%PORT%/health', timeout=3).read().decode())" 2>nul
    if %errorlevel%==0 (
        echo [JARVIS] Server already running and healthy!
        goto :verify
    ) else (
        echo [WARNING] Port in use but not responding. Kill the process manually if needed.
    )
)

:: Disable voice for startup (avoids audio device issues)
set JARVIS_DISABLE_VOICE=1

:: --- Test main.py imports ---
echo [JARVIS] Testing backend.main imports...
%PYTHON% -c "import sys; sys.path.insert(0,'backend'); import backend.main; print('OK')" 2>nul
if %errorlevel%==0 (
    set ENTRY=backend.main:app
    echo [JARVIS] main.py imports OK — using full backend
) else (
    echo [WARNING] backend.main import failed — falling back to main_simple.py
    %PYTHON% -c "import backend.main_simple; print('OK')" 2>nul
    if %errorlevel%==0 (
        set ENTRY=backend.main_simple:app
        echo [JARVIS] main_simple.py imports OK — using simple backend
    ) else (
        echo [ERROR] Both main.py and main_simple.py failed to import!
        echo         Check requirements: %PYTHON% -m pip install -r backend\requirements.txt
        pause
        exit /b 1
    )
)

echo [JARVIS] Starting: uvicorn !ENTRY! on 0.0.0.0:%PORT%
echo [JARVIS] Log: %LOGFILE%

:: Start uvicorn detached, redirect output to log
start "JARVIS Backend" /B cmd /c "%PYTHON% -m uvicorn !ENTRY! --host 0.0.0.0 --port %PORT% > %LOGFILE% 2>&1"

:: Wait for startup
echo [JARVIS] Waiting for startup...
timeout /t 6 /nobreak >nul

:verify
echo [JARVIS] Verifying health endpoint (polling up to 30s)...
set HEALTH_OK=0
for /l %%i in (1,1,15) do (
    if !HEALTH_OK!==0 (
        %PYTHON% -c "import urllib.request; urllib.request.urlopen('http://localhost:%PORT%/health',timeout=2).read()" 2>nul
        if !errorlevel!==0 (
            set HEALTH_OK=1
        ) else (
            timeout /t 2 /nobreak >nul
        )
    )
)
%PYTHON% -c "import urllib.request; print(urllib.request.urlopen('http://localhost:%PORT%/health',timeout=5).read().decode())" 2>nul
if !HEALTH_OK!==1 (
    echo.
    echo ============================================================
    echo  JARVIS IS ONLINE at http://localhost:%PORT%
    echo  Health:   http://localhost:%PORT%/health
    echo  Docs:     http://localhost:%PORT%/docs
    echo  WS:       ws://localhost:%PORT%/ws/jarvis
    echo  Log:      %LOGFILE%
    echo ============================================================
) else (
    echo [ERROR] Health check failed! Server may not have started.
    echo         Check log: %LOGFILE%
    if exist "%LOGFILE%" (
        echo.
        echo --- Last 30 lines of log ---
        powershell -Command "Get-Content '%LOGFILE%' | Select-Object -Last 30"
    )
)

endlocal
