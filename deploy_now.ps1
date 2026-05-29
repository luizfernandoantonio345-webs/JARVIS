#!/usr/bin/env pwsh
<#
.SYNOPSIS
JARVIS v6.0 — FULL DEPLOY AUTOMATION
Execute all phases and deploy in one command

.EXAMPLE
.\deploy_now.ps1

.NOTES
This script runs all 4 phases and starts JARVIS
Total time: 1.5-2 hours
#>

param(
    [switch]$SkipPhase1 = $false,
    [switch]$SkipPhase2 = $false,
    [switch]$SkipPhase3 = $false,
    [switch]$SkipValidation = $false,
    [switch]$DisableVoice = $false
)

$colors = @{
    Green  = "`e[92m"
    Red    = "`e[91m"
    Yellow = "`e[93m"
    Cyan   = "`e[96m"
    Blue   = "`e[94m"
    Bold   = "`e[1m"
    Reset  = "`e[0m"
}

function Write-Success { param([string]$Message)
    Write-Host "$($colors.Green)✓ $Message$($colors.Reset)" }

function Write-Error { param([string]$Message)
    Write-Host "$($colors.Red)✗ $Message$($colors.Reset)" }

function Write-Warning { param([string]$Message)
    Write-Host "$($colors.Yellow)⚠ $Message$($colors.Reset)" }

function Write-Info { param([string]$Message)
    Write-Host "$($colors.Cyan)→ $Message$($colors.Reset)" }

function Write-Header { param([string]$Message)
    $line = "="*70
    Write-Host "`n$($colors.Blue)$($colors.Bold)$line$($colors.Reset)"
    Write-Host "$($colors.Blue)$($colors.Bold)$($Message.PadLeft(($Message.Length + 70)/2))$($colors.Reset)"
    Write-Host "$($colors.Blue)$($colors.Bold)$line$($colors.Reset)`n" }

function Main {
    Write-Header "JARVIS v6.0 — COMPLETE DEPLOYMENT AUTOMATION"
    
    $root = Split-Path -Parent $MyInvocation.MyCommand.Path
    Set-Location $root
    
    $startTime = Get-Date
    
    # PHASE 1
    if (-not $SkipPhase1) {
        Write-Info "PHASE 1 — Environment Preparation (10-15 min)..."
        $phase1Start = Get-Date
        
        python phase1_deploy_prep.py
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Phase 1 failed"
            return 1
        }
        
        $phase1Time = ((Get-Date) - $phase1Start).TotalSeconds
        Write-Success "Phase 1 completed in $([math]::Round($phase1Time))s`n"
    }
    
    # PHASE 2
    if (-not $SkipPhase2) {
        Write-Info "PHASE 2 — Code Fixes (20-30 min)..."
        $phase2Start = Get-Date
        
        python phase2_deploy_fixes.py
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Phase 2 failed"
            return 1
        }
        
        $phase2Time = ((Get-Date) - $phase2Start).TotalSeconds
        Write-Success "Phase 2 completed in $([math]::Round($phase2Time))s`n"
    }
    
    # PHASE 3
    if (-not $SkipPhase3) {
        Write-Info "PHASE 3 — Validation Tests (10-15 min)..."
        $phase3Start = Get-Date
        
        python phase3_deploy_validation.py
        if ($LASTEXITCODE -ne 0) {
            if (-not $SkipValidation) {
                Write-Error "Phase 3 validation failed"
                Write-Warning "Some checks failed. Review above and retry"
                return 1
            } else {
                Write-Warning "Phase 3 skipped (--SkipValidation)"
            }
        }
        
        $phase3Time = ((Get-Date) - $phase3Start).TotalSeconds
        Write-Success "Phase 3 completed in $([math]::Round($phase3Time))s`n"
    }
    
    # PHASE 4 — Startup
    Write-Info "PHASE 4 — Starting JARVIS..."
    
    $args = @()
    if ($DisableVoice) {
        $args += "-DisableVoice"
    }
    
    & .\startup_final.ps1 @args
    
    return $LASTEXITCODE
}

$exitCode = Main
exit $exitCode
