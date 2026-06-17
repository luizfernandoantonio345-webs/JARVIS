#!/usr/bin/env pwsh
<#
.SYNOPSIS
JARVIS v8.0 — Registra auto-start no Windows (Task Scheduler)

.DESCRIPTION
Cria uma Tarefa Agendada que inicia o JARVIS automaticamente:
  - No logon do usuario
  - Com reinicio automatico em caso de falha
  - Silencioso (sem janela visible — roda em background)

.PARAMETER Uninstall
Remove a tarefa agendada (ao inves de criar)

.PARAMETER Port
Porta do backend (default: 8000)

.PARAMETER Model
Modelo LLM padrao (default: qwen2:0.5b)

.EXAMPLE
# Instalar auto-start:
.\install_autostart.ps1

# Remover auto-start:
.\install_autostart.ps1 -Uninstall
#>

param(
    [switch]$Uninstall,
    [string]$Port  = "8000",
    [string]$Model = "qwen2:0.5b"
)

$TASK_NAME    = "JARVIS-AutoStart"
$TASK_DESC    = "Inicia o servidor JARVIS v8.0 automaticamente no logon"
$ROOT         = $PSScriptRoot
$VENV_PYTHON  = Join-Path $ROOT "venv311\Scripts\python.exe"
$LOG_DIR      = Join-Path $ROOT "backend\logs"
$LAUNCHER     = Join-Path $ROOT "start_background.ps1"

# ── Cores ──────────────────────────────────────────────────────────────────────
function ok($m)   { Write-Host "[OK]   $m" -ForegroundColor Green }
function err($m)  { Write-Host "[ERR]  $m" -ForegroundColor Red }
function info($m) { Write-Host "[INFO] $m" -ForegroundColor Cyan }

# ── Remover tarefa ─────────────────────────────────────────────────────────────
if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $TASK_NAME -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TASK_NAME -Confirm:$false
        ok "Tarefa '$TASK_NAME' removida."
    } else {
        info "Tarefa '$TASK_NAME' nao existe."
    }
    exit 0
}

# ── Verificacoes pre-install ───────────────────────────────────────────────────
info "Verificando pre-requisitos..."

if (-not (Test-Path $VENV_PYTHON)) {
    err "venv311 nao encontrado em: $VENV_PYTHON"
    err "Execute: python -m venv venv311 && venv311\Scripts\pip install -r requirements.txt"
    exit 1
}
ok "Python venv311 encontrado"

if (-not (Test-Path $LOG_DIR)) {
    New-Item -ItemType Directory -Force $LOG_DIR | Out-Null
}
ok "Diretorio de logs: $LOG_DIR"

# ── Criar script launcher silencioso ─────────────────────────────────────────
$launcherContent = @"
# JARVIS Background Launcher — gerado por install_autostart.ps1
# Nao edite manualmente
`$ErrorActionPreference = 'SilentlyContinue'

`$ROOT    = '$ROOT'
`$PYTHON  = '$VENV_PYTHON'
`$LOG     = '$LOG_DIR\autostart.log'
`$PORT    = '$Port'
`$MODEL   = '$Model'

Set-Location `$ROOT

# Matar processo anterior na porta
`$pidOnPort = netstat -ano 2>`$null | Select-String ":`$PORT " | Select-String "LISTENING" |
    ForEach-Object { (`$_ -split '\s+')[4] } | Select-Object -First 1
if (`$pidOnPort) { Stop-Process -Id `$pidOnPort -Force -ErrorAction SilentlyContinue }

# Variaveis de ambiente
`$env:KMP_DUPLICATE_LIB_OK = 'TRUE'
`$env:OMP_NUM_THREADS       = '1'
`$env:OPENBLAS_NUM_THREADS  = '1'
`$env:MKL_NUM_THREADS       = '1'
`$env:PYTHONIOENCODING      = 'utf-8'
`$env:JARVIS_MODEL          = `$MODEL
`$env:JARVIS_PORT           = `$PORT
`$env:JARVIS_WAKE_WORD_ENABLED = 'false'

# Iniciar backend (esconde janela)
`$startInfo = New-Object System.Diagnostics.ProcessStartInfo
`$startInfo.FileName  = `$PYTHON
`$startInfo.Arguments = "-m uvicorn main:app --host 0.0.0.0 --port `$PORT --log-level warning"
`$startInfo.WorkingDirectory     = "`$ROOT\backend"
`$startInfo.UseShellExecute      = `$false
`$startInfo.CreateNoWindow       = `$true
`$startInfo.RedirectStandardOutput = `$true
`$startInfo.RedirectStandardError  = `$true

`$proc = [System.Diagnostics.Process]::Start(`$startInfo)
`$timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
Add-Content -Path `$LOG -Value "`$timestamp [AUTOSTART] JARVIS iniciado PID=`$(`$proc.Id) porta=`$PORT"

# Esperar backend subir (max 60s)
`$deadline = (Get-Date).AddSeconds(60)
while ((Get-Date) -lt `$deadline) {
    Start-Sleep -Seconds 2
    try {
        `$r = Invoke-WebRequest -Uri "http://localhost:`$PORT/health" -TimeoutSec 1 -EA Stop
        if (`$r.StatusCode -eq 200) {
            Add-Content -Path `$LOG -Value "`$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [AUTOSTART] Health OK"
            break
        }
    } catch { }
}
"@

Set-Content -Path $LAUNCHER -Value $launcherContent -Encoding UTF8
ok "Launcher criado: $LAUNCHER"

# ── Criar Tarefa Agendada ─────────────────────────────────────────────────────
info "Registrando tarefa agendada '$TASK_NAME'..."

# Remover tarefa anterior se existir
if (Get-ScheduledTask -TaskName $TASK_NAME -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TASK_NAME -Confirm:$false
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$LAUNCHER`""

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 2) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0)

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName    $TASK_NAME `
    -Description $TASK_DESC `
    -Action      $action `
    -Trigger     $trigger `
    -Settings    $settings `
    -Principal   $principal `
    -Force | Out-Null

if (Get-ScheduledTask -TaskName $TASK_NAME -ErrorAction SilentlyContinue) {
    ok "Tarefa '$TASK_NAME' registrada com sucesso!"
} else {
    err "Falha ao registrar tarefa. Tente executar como Administrador."
    exit 1
}

# ── Iniciar agora (opcional) ──────────────────────────────────────────────────
$start = Read-Host "`nDeseja iniciar o JARVIS agora? (S/n)"
if ($start -ne 'n' -and $start -ne 'N') {
    info "Iniciando JARVIS..."
    Start-ScheduledTask -TaskName $TASK_NAME
    Start-Sleep -Seconds 5
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:$Port/health" -TimeoutSec 5 -EA Stop
        if ($r.StatusCode -eq 200) {
            ok "JARVIS online em http://localhost:$Port"
            Start-Process "http://localhost:$Port"
        }
    } catch {
        info "JARVIS iniciando... acesse http://localhost:$Port em alguns segundos."
    }
}

Write-Host ""
ok "INSTALACAO CONCLUIDA!"
Write-Host "  Auto-start : no logon do Windows"
Write-Host "  Porta      : $Port"
Write-Host "  Modelo     : $Model"
Write-Host "  Log        : $LOG_DIR\autostart.log"
Write-Host "  Remover    : .\install_autostart.ps1 -Uninstall"
Write-Host ""
