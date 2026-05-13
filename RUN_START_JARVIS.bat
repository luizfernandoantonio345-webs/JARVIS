@echo off
REM ============================================================
REM  JARVIS Startup Script (Windows - using cmd.exe)
REM  This script starts the JARVIS AI Backend server
REM ============================================================

setlocal enabledelayedexpansion

:: Configuration
set "JARVIS_DIR=C:\Users\cibernetico\JARVIS"
set "PYTHON=%JARVIS_DIR%\.venv\Scripts\python.exe"
set "LAUNCHER=%JARVIS_DIR%\launch_jarvis.py"
set "LOGFILE=%JARVIS_DIR%\jarvis_startup.log"
set "PORT=8000"

cd /d "%JARVIS_DIR%"

:: Check if Python exists
if not exist "%PYTHON%" (
    echo [ERROR] Python not found at: %PYTHON%
    echo.
    echo Available venv directories:
    if exist ".venv" echo   - .venv
    if exist ".venv-1" echo   - .venv-1
    if exist "venv" echo   - venv
    if exist "venv311" echo   - venv311
    exit /b 1
)

echo [JARVIS] Starting JARVIS AI Backend
echo [JARVIS] Python: %PYTHON%
echo [JARVIS] Working Dir: %JARVIS_DIR%
echo [JARVIS] Log: %LOGFILE%
echo.

:: Disable voice to avoid audio device issues
set JARVIS_DISABLE_VOICE=1

:: Use the launcher script which handles everything
echo [JARVIS] Running launcher: %PYTHON% %LAUNCHER%
%PYTHON% %LAUNCHER%

endlocal
