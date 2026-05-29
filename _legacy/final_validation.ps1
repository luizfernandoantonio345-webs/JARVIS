param(
    [string]$BackendUrl = "http://127.0.0.1:8000",
    [string]$OllamaUrl = "",
    [switch]$UseFallback,
    [string]$FallbackOllamaUrl = "http://192.168.0.106:11434",
    [string]$ExpectedModel = ""
)

if ([string]::IsNullOrWhiteSpace($OllamaUrl)) {
    if ($env:JARVIS_OLLAMA_URL) {
        $OllamaUrl = $env:JARVIS_OLLAMA_URL
    } else {
        $OllamaUrl = "http://localhost:11434"
    }
}

if ([string]::IsNullOrWhiteSpace($ExpectedModel)) {
    if ($env:JARVIS_MODEL) {
        $ExpectedModel = $env:JARVIS_MODEL
    } else {
        $ExpectedModel = "qwen2:0.5b"
    }
}

function Test-OllamaReachable {
    param([string]$BaseUrl)
    try {
        $null = Invoke-RestMethod -Uri "$BaseUrl/api/tags" -TimeoutSec 4 -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

function Try-StartLocalOllama {
    param([string]$BaseUrl)
    if ($BaseUrl -notmatch "localhost|127\.0\.0\.1") {
        return
    }

    if (Test-OllamaReachable -BaseUrl $BaseUrl) {
        return
    }

    Write-Host "[INFO] Ollama local offline. Tentando iniciar servico local..." -ForegroundColor Yellow

    $ollamaExe = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if (Test-Path $ollamaExe) {
        Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Hidden
    } else {
        Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden -ErrorAction SilentlyContinue
    }

    for ($i = 1; $i -le 10; $i++) {
        Start-Sleep -Seconds 2
        if (Test-OllamaReachable -BaseUrl $BaseUrl) {
            Write-Host "[OK] Ollama local iniciado." -ForegroundColor Green
            return
        }
    }

    Write-Host "[WARN] Nao foi possivel iniciar Ollama local automaticamente." -ForegroundColor DarkYellow
}

Write-Host "=== FINAL VALIDATION (PC1-first) ===" -ForegroundColor Cyan
Write-Host "Backend : $BackendUrl"
Write-Host "Ollama  : $OllamaUrl"
Write-Host "Modelo  : $ExpectedModel"
if ($UseFallback) {
    Write-Host "Fallback: $FallbackOllamaUrl"
}

Try-StartLocalOllama -BaseUrl $OllamaUrl

$healthUrl = "$BackendUrl/health"
$needStartBackend = $false

try {
    $null = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 5 -ErrorAction Stop
} catch {
    $needStartBackend = $true
}

if ($needStartBackend) {
    Write-Host "[INFO] Backend offline. Tentando iniciar..." -ForegroundColor Yellow
    if (Test-Path ".\scripts\start_backend.ps1") {
        powershell -ExecutionPolicy Bypass -File .\scripts\start_backend.ps1 | Out-Null
    } else {
        Start-Process -FilePath ".\start_backend.bat" -WindowStyle Hidden
    }

    $backendReady = $false
    for ($i = 1; $i -le 15; $i++) {
        Start-Sleep -Seconds 2
        try {
            $null = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 3 -ErrorAction Stop
            $backendReady = $true
            break
        } catch {
            Write-Host "[INFO] Aguardando backend... tentativa $i/15" -ForegroundColor DarkYellow
        }
    }

    if (-not $backendReady) {
        Write-Host "[FAIL] Backend nao ficou pronto em tempo habil ($healthUrl)." -ForegroundColor Red
        exit 1
    }
}

if (-not (Test-Path ".\scripts\validate_jarvis_local.ps1")) {
    Write-Host "[FAIL] Script scripts\\validate_jarvis_local.ps1 nao encontrado." -ForegroundColor Red
    exit 1
}

$args = @(
    "-ExecutionPolicy", "Bypass",
    "-File", ".\scripts\validate_jarvis_local.ps1",
    "-BackendUrl", $BackendUrl,
    "-OllamaUrl", $OllamaUrl,
    "-ExpectedModel", $ExpectedModel
)

if ($UseFallback) {
    $args += @("-UseFallback", "-FallbackOllamaUrl", $FallbackOllamaUrl)
}

& powershell @args
exit $LASTEXITCODE
