param(
    [int]$Port = 8000,
    [string]$BindHost = "0.0.0.0",
    [string]$OllamaUrl = "",
    [switch]$UseReload
)

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

if ([string]::IsNullOrWhiteSpace($OllamaUrl)) {
    if ($env:JARVIS_OLLAMA_URL) {
        $OllamaUrl = $env:JARVIS_OLLAMA_URL
    } else {
        $OllamaUrl = "http://localhost:11434"
    }
}

if (-not $env:JARVIS_MODEL) {
    $env:JARVIS_MODEL = "qwen2:0.5b"
}

$pythonCandidates = @(
    (Join-Path $repoRoot ".venv\Scripts\python.exe"),
    (Join-Path $repoRoot "venv311\Scripts\python.exe"),
    (Join-Path $repoRoot "venv\Scripts\python.exe")
)

$pythonExe = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $pythonExe) {
    throw "Python de venv nao encontrado. Esperado em .venv, venv311 ou venv."
}

$lines = netstat -ano | findstr ":$Port" | findstr "LISTENING" 2>$null
if ($lines) {
    foreach ($line in $lines) {
        $killPid = $line.Trim().Split()[-1]
        if ($killPid) {
            Write-Output "Killing PID $killPid on port $Port"
            taskkill /PID $killPid /F *> $null
        }
    }
} else {
    Write-Output "No process on port $Port"
}

$env:JARVIS_OLLAMA_URL = $OllamaUrl
Write-Output "Starting backend with JARVIS_OLLAMA_URL=$OllamaUrl"
$uvicornArgs = @('-m','uvicorn','backend.main:app','--host',$BindHost,'--port',$Port,'--log-level','info')
if ($UseReload) {
    $uvicornArgs += '--reload'
}
Start-Process -FilePath $pythonExe -ArgumentList $uvicornArgs -WindowStyle Hidden -WorkingDirectory $repoRoot

$healthUrl = "http://127.0.0.1:$Port/health"
$healthy = $false
for ($i = 1; $i -le 20; $i++) {
    Start-Sleep -Seconds 2
    try {
        $h = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 3 -ErrorAction Stop
        Write-Output "Backend health OK on attempt $i"
        $h | ConvertTo-Json -Depth 6
        $healthy = $true
        break
    } catch {
        Write-Output "Waiting backend... attempt $i/20"
    }
}

if (-not $healthy) {
    Write-Output "ERROR: backend did not become healthy at $healthUrl"
    exit 1
}
