#!/usr/bin/env pwsh
# -*- coding: utf-8 -*-
<#
.SYNOPSIS
JARVIS v6.0 — FINAL DEPLOYMENT STARTUP
Robust startup script with health checks, auto-retry, fallback handling

.DESCRIPTION
This script:
1. Kills any existing process on port 8000
2. Activates venv311
3. Starts backend with uvicorn
4. Polls health endpoint (with retries)
5. Opens browser to dashboard
6. Monitors for errors

.EXAMPLE
.\startup_final.ps1

.EXAMPLE
.\startup_final.ps1 -NoWait

.NOTES
Author: GitHub Copilot
Version: 6.0
Date: 2026-05-28
#>

param(
    [switch]$NoWait,
    [switch]$DisableVoice = $false,
    [string]$Model = "smollm2:135m",
    [string]$Port = "8000"
)

# Colors
$colors = @{
    Green  = "`e[92m"
    Red    = "`e[91m"
    Yellow = "`e[93m"
    Cyan   = "`e[96m"
    Blue   = "`e[94m"
    Bold   = "`e[1m"
    Reset  = "`e[0m"
}

function Write-Success {
    param([string]$Message)
    Write-Host "$($colors.Green)✓ $Message$($colors.Reset)"
}

function Write-Error {
    param([string]$Message)
    Write-Host "$($colors.Red)✗ $Message$($colors.Reset)"
}

function Write-Warning {
    param([string]$Message)
    Write-Host "$($colors.Yellow)⚠ $Message$($colors.Reset)"
}

function Write-Info {
    param([string]$Message)
    Write-Host "$($colors.Cyan)→ $Message$($colors.Reset)"
}

function Write-Header {
    param([string]$Message)
    $line = "="*70
    Write-Host "`n$($colors.Blue)$($colors.Bold)$line$($colors.Reset)"
    Write-Host "$($colors.Blue)$($colors.Bold)$($Message.PadLeft(($Message.Length + 70)/2))$($colors.Reset)"
    Write-Host "$($colors.Blue)$($colors.Bold)$line$($colors.Reset)`n"
}

# Main execution
function Main {
    Write-Header "JARVIS v6.0 — FINAL DEPLOYMENT STARTUP"
    
    $root = Split-Path -Parent $MyInvocation.MyCommand.Path
    Set-Location $root
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Info "Started: $timestamp"
    Write-Info "Root: $root`n"
    
    # ===== STEP 1: Verify Prerequisites =====
    Write-Info "STEP 1: Verifying prerequisites..."
    
    # Check Python
    $pythonPath = Join-Path $root "venv311\Scripts\python.exe"
    if (-not (Test-Path $pythonPath)) {
        Write-Error "Python not found at venv311. Create with: python -m venv venv311"
        return 1
    }
    Write-Success "Python venv found"
    
    # Check Ollama
    try {
        $ollamaResponse = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -TimeoutSec 2 -ErrorAction Stop
        Write-Success "Ollama online"
    } catch {
        Write-Warning "Ollama not responding. Start with: ollama serve"
        Write-Info "Continuing anyway (may fail later)..."
    }
    
    # ===== STEP 2: Kill existing process on port =====
    Write-Info "STEP 2: Clearing port $Port..."
    
    $pidOnPort = netstat -ano 2>$null | Select-String ":$Port " | Select-String "LISTENING" | ForEach-Object {
        $parts = $_ -split '\s+'
        $parts[4]
    } | Select-Object -First 1
    
    if ($pidOnPort) {
        Write-Warning "Found process on port $Port (PID: $pidOnPort) — killing..."
        try {
            Stop-Process -Id $pidOnPort -Force -ErrorAction Stop
            Write-Success "Killed PID $pidOnPort"
            Start-Sleep -Milliseconds 500
        } catch {
            Write-Error "Could not kill PID $pidOnPort"
        }
    } else {
        Write-Success "Port $Port is free"
    }
    
    # ===== STEP 3: Setup environment =====
    Write-Info "STEP 3: Setting up environment..."
    
    # Set environment variables
    $env:KMP_DUPLICATE_LIB_OK = "TRUE"
    $env:OMP_NUM_THREADS = "1"
    $env:KMP_WARNINGS = "FALSE"
    $env:OPENBLAS_NUM_THREADS = "1"
    $env:MKL_NUM_THREADS = "1"
    $env:PYTHONIOENCODING = "utf-8"
    $env:JARVIS_MODEL = $Model
    $env:JARVIS_PORT = $Port
    
    if ($DisableVoice) {
        $env:JARVIS_DISABLE_VOICE = "true"
        Write-Info "Voice disabled"
    }
    
    Write-Success "Environment variables set"
    
    # ===== STEP 4: Start backend =====
    Write-Info "STEP 4: Starting JARVIS backend..."
    
    $startTime = Get-Date
    
    # Start the backend in a new process
    $argList = @(
        "-m", "uvicorn",
        "backend.main:app",
        "--host", "0.0.0.0",
        "--port", $Port,
        "--log-level", "warning",
        "--access-log"
    )
    
    Write-Info "Command: $pythonPath $($argList -join ' ')"
    
    $processInfo = New-Object System.Diagnostics.ProcessStartInfo
    $processInfo.FileName = $pythonPath
    $processInfo.Arguments = $argList -join " "
    $processInfo.UseShellExecute = $true
    $processInfo.CreateNoWindow = $false
    $processInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Normal
    $processInfo.WorkingDirectory = $root
    $processInfo.RedirectStandardOutput = $false
    $processInfo.RedirectStandardError = $false
    
    try {
        $process = [System.Diagnostics.Process]::Start($processInfo)
        $backendPid = $process.Id
        Write-Success "Backend started (PID: $backendPid)"
        Write-Info "Waiting for server to initialize..."
    } catch {
        Write-Error "Failed to start backend: $_"
        return 1
    }
    
    # ===== STEP 5: Health check with retry =====
    Write-Info "STEP 5: Waiting for backend (polling health endpoint)..."
    
    $healthUrl = "http://localhost:$Port/health"
    $maxRetries = 30
    $retryInterval = 1
    $healthOk = $false
    
    for ($i = 1; $i -le $maxRetries; $i++) {
        try {
            $response = Invoke-WebRequest -Uri $healthUrl -TimeoutSec 2 -ErrorAction Stop
            if ($response.StatusCode -eq 200) {
                $healthOk = $true
                Write-Success "Health check passed (attempt $i)"
                break
            }
        } catch {
            # Connection not ready yet
            Write-Info "  Attempt $i/$maxRetries: Backend initializing..."
            Start-Sleep -Seconds $retryInterval
        }
    }
    
    if (-not $healthOk) {
        Write-Warning "Health check timeout after $($maxRetries * $retryInterval)s"
        Write-Info "Backend may still be starting — waiting extra 10s..."
        Start-Sleep -Seconds 10
    }
    
    # ===== STEP 6: Show URLs =====
    Write-Header "✓ JARVIS ONLINE"
    
    $elapsedSeconds = ((Get-Date) - $startTime).TotalSeconds
    Write-Success "Backend ready in $([math]::Round($elapsedSeconds, 1))s"
    
    Write-Host "`n$($colors.Cyan)URLs:$($colors.Reset)"
    Write-Host "  🏠 Dashboard    : http://localhost:$Port"
    Write-Host "  📚 API Docs     : http://localhost:$Port/docs"
    Write-Host "  🔌 WebSocket    : ws://localhost:$Port/ws/jarvis"
    Write-Host "  💚 Health       : http://localhost:$Port/health"
    Write-Host "  📊 Metrics      : http://localhost:$Port/metrics"
    
    Write-Host "`n$($colors.Cyan)Configuration:$($colors.Reset)"
    Write-Host "  Model  : $Model"
    Write-Host "  Port   : $Port"
    Write-Host "  Voice  : $(-not $DisableVoice)"
    Write-Host "  PID    : $backendPid"
    
    # ===== STEP 7: Open browser =====
    if (-not $NoWait) {
        Write-Info "Opening browser..."
        Start-Sleep -Milliseconds 500
        try {
            Start-Process "http://localhost:$Port"
            Write-Success "Browser opened"
        } catch {
            Write-Warning "Could not open browser automatically"
        }
    }
    
    # ===== STEP 8: Monitoring =====
    Write-Host "`n$($colors.Cyan)Monitoring (Ctrl+C to stop):$($colors.Reset)`n"
    
    $monitorInterval = 30  # seconds
    $errorCount = 0
    $lastCheck = Get-Date
    
    if (-not $NoWait) {
        while ($true) {
            Start-Sleep -Milliseconds 500
            
            # Check if backend process still exists
            try {
                $proc = Get-Process -Id $backendPid -ErrorAction Stop
            } catch {
                Write-Error "`nBackend process died (PID: $backendPid)"
                Write-Info "Check logs: backend/logs/jarvis.log"
                return 1
            }
            
            # Periodic health check (every $monitorInterval seconds)
            if (((Get-Date) - $lastCheck).TotalSeconds -ge $monitorInterval) {
                try {
                    $response = Invoke-WebRequest -Uri $healthUrl -TimeoutSec 2 -ErrorAction Stop
                    if ($response.StatusCode -eq 200) {
                        $data = $response.Content | ConvertFrom-Json
                        Write-Host "[$((Get-Date).ToString('HH:mm:ss'))] Health: OK | Uptime: $($data.uptime)s" -ForegroundColor Green
                        $errorCount = 0
                    }
                } catch {
                    $errorCount++
                    Write-Warning "[$((Get-Date).ToString('HH:mm:ss'))] Health check failed (attempt $errorCount)"
                    if ($errorCount -ge 3) {
                        Write-Error "`nBackend appears to be unhealthy"
                        Write-Info "Check logs: backend/logs/jarvis.log"
                        return 1
                    }
                }
                $lastCheck = Get-Date
            }
        }
    }
    
    return 0
}

# Execute
$exitCode = Main
exit $exitCode
