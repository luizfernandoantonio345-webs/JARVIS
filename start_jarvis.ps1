# JARVIS Startup Script for PowerShell 5.x (Windows PowerShell)
# Usage: powershell.exe -ExecutionPolicy Bypass -File "C:\Users\cibernetico\JARVIS\start_jarvis.ps1"

param(
    [switch]$NoVerify
)

$ErrorActionPreference = "Continue"

# Configuration
$JARVIS_DIR = "C:\Users\cibernetico\JARVIS"
$PYTHON = Join-Path $JARVIS_DIR ".venv\Scripts\python.exe"
$LAUNCHER = Join-Path $JARVIS_DIR "launch_jarvis.py"
$LOGFILE = Join-Path $JARVIS_DIR "jarvis_startup.log"
$PORT = 8000
$HEALTH_URL = "http://localhost:$PORT/health"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  JARVIS AI Backend Launcher (PowerShell 5.x)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Check Python
if (-not (Test-Path $PYTHON)) {
    Write-Host "[ERROR] Python not found at: $PYTHON" -ForegroundColor Red
    exit 1
}

Write-Host "[+] Python: $PYTHON" -ForegroundColor Green
Write-Host "[+] JARVIS Dir: $JARVIS_DIR" -ForegroundColor Green
Write-Host "[+] Log: $LOGFILE" -ForegroundColor Green
Write-Host ""

# Check if already running
Write-Host "[+] Checking if JARVIS is already running..." -ForegroundColor Yellow
try {
    $healthResponse = Invoke-WebRequest -Uri $HEALTH_URL -TimeoutSec 3 -UseBasicParsing
    $health = $healthResponse.Content | ConvertFrom-Json
    Write-Host ""
    Write-Host "[✓] JARVIS is already running!" -ForegroundColor Green
    Write-Host ""
    Write-Host ($health | ConvertTo-Json -Depth 10)
    Write-Host ""
    Write-Host "  API:  http://localhost:$PORT" -ForegroundColor Cyan
    Write-Host "  Docs: http://localhost:$PORT/docs" -ForegroundColor Cyan
    Write-Host "  WS:   ws://localhost:$PORT/ws/jarvis" -ForegroundColor Cyan
    Write-Host ""
    exit 0
} catch {
    Write-Host "    (Not running or slow to respond)" -ForegroundColor Gray
}

# Start the launcher
Write-Host "[+] Starting launcher..." -ForegroundColor Yellow
Write-Host "    $PYTHON $LAUNCHER" -ForegroundColor Gray
Write-Host ""

try {
    # Start the launcher script in background
    # Using no window to suppress the console window
    $proc = Start-Process -FilePath $PYTHON `
                         -ArgumentList $LAUNCHER `
                         -WorkingDirectory $JARVIS_DIR `
                         -WindowStyle Hidden `
                         -PassThru `
                         -ErrorAction Stop
    
    Write-Host "[✓] Launcher started with PID: $($proc.Id)" -ForegroundColor Green
    Write-Host ""
    
    # Wait for startup
    Write-Host "[+] Waiting for JARVIS to come online..." -ForegroundColor Yellow
    $maxWait = 30
    $waited = 0
    
    while ($waited -lt $maxWait) {
        Start-Sleep -Seconds 1
        $waited += 1
        
        try {
            $healthResponse = Invoke-WebRequest -Uri $HEALTH_URL -TimeoutSec 2 -UseBasicParsing
            $health = $healthResponse.Content | ConvertFrom-Json
            
            Write-Host ""
            Write-Host "[✓] JARVIS is ONLINE after ${waited}s!" -ForegroundColor Green
            Write-Host ""
            Write-Host ($health | ConvertTo-Json -Depth 10)
            Write-Host ""
            Write-Host "  API:  http://localhost:$PORT" -ForegroundColor Cyan
            Write-Host "  Docs: http://localhost:$PORT/docs" -ForegroundColor Cyan
            Write-Host "  WS:   ws://localhost:$PORT/ws/jarvis" -ForegroundColor Cyan
            Write-Host "  Log:  $LOGFILE" -ForegroundColor Cyan
            Write-Host ""
            exit 0
        } catch {
            if (($waited % 5) -eq 0) {
                Write-Host "    ... ${waited}s elapsed" -ForegroundColor Gray
            }
        }
    }
    
    # If we get here, health check failed
    Write-Host ""
    Write-Host "[ERROR] Health check failed after ${maxWait}s" -ForegroundColor Red
    Write-Host ""
    Write-Host "Log file may contain error details:" -ForegroundColor Yellow
    Write-Host "  $LOGFILE" -ForegroundColor Cyan
    Write-Host ""
    
    if (Test-Path $LOGFILE) {
        Write-Host "--- Last 40 lines of log ---" -ForegroundColor Gray
        Get-Content $LOGFILE -Tail 40 | ForEach-Object {
            Write-Host "  $_" -ForegroundColor Gray
        }
    }
    
    exit 1
    
} catch {
    Write-Host "[ERROR] Failed to start launcher: $_" -ForegroundColor Red
    exit 1
}
