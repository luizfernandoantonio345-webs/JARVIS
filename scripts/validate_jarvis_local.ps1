param(
    [string]$BackendUrl = "http://127.0.0.1:8000",
    [string]$OllamaUrl = "",
    [string]$FallbackOllamaUrl = "",
    [switch]$UseFallback,
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

if ([string]::IsNullOrWhiteSpace($FallbackOllamaUrl)) {
    $FallbackOllamaUrl = "http://192.168.0.106:11434"
}

function Get-OllamaModels {
    param([string]$BaseUrl)
    try {
        $tags = Invoke-RestMethod -Uri "$BaseUrl/api/tags" -TimeoutSec 8
        return @($tags.models | ForEach-Object { $_.name })
    } catch {
        return $null
    }
}

Write-Host "=== JARVIS Local Validation ===" -ForegroundColor Cyan
Write-Host "Backend: $BackendUrl"
Write-Host "Ollama : $OllamaUrl (primario)"
if ($UseFallback) {
    Write-Host "Fallback: $FallbackOllamaUrl"
}
Write-Host "Modelo alvo: $ExpectedModel"

$allOk = $true
$activeOllamaUrl = $OllamaUrl
$models = @()

# 1) Ollama
$models = Get-OllamaModels -BaseUrl $OllamaUrl
if ($models -ne $null) {
    Write-Host "[OK] Ollama primario alcancavel. Models: $($models -join ', ')" -ForegroundColor Green
} elseif ($UseFallback) {
    $fallbackModels = Get-OllamaModels -BaseUrl $FallbackOllamaUrl
    if ($fallbackModels -ne $null) {
        $activeOllamaUrl = $FallbackOllamaUrl
        $models = $fallbackModels
        Write-Host "[OK] Ollama fallback alcancavel. Models: $($models -join ', ')" -ForegroundColor Yellow
    } else {
        Write-Host "[FAIL] Ollama primario e fallback indisponiveis" -ForegroundColor Red
        $allOk = $false
    }
} else {
    Write-Host "[FAIL] Ollama primario indisponivel (use -UseFallback para testar PC2)" -ForegroundColor Red
    $allOk = $false
}

if ($models.Count -eq 0) {
    Write-Host "[FAIL] Nenhum modelo instalado no Ollama ativo ($activeOllamaUrl)." -ForegroundColor Red
    Write-Host "       Acao: ollama pull $ExpectedModel" -ForegroundColor Yellow
    $allOk = $false
}

# 2) Ollama model generation (direct)
if ($models.Count -gt 0) {
    $modelToTest = $ExpectedModel
    if ($models -notcontains $modelToTest) {
        $modelToTest = $models[0]
        Write-Host "[WARN] Modelo alvo ausente. Testando com: $modelToTest" -ForegroundColor Yellow
    }
    try {
        $genBody = @{ model = $modelToTest; prompt = "responda apenas: OK"; stream = $false } | ConvertTo-Json
        $gen = Invoke-RestMethod -Uri "$activeOllamaUrl/api/generate" -Method Post -ContentType "application/json" -Body $genBody -TimeoutSec 45
        Write-Host "[OK] Geracao Ollama: $($gen.response)" -ForegroundColor Green
    } catch {
        Write-Host "[FAIL] Geracao Ollama falhou: $($_.Exception.Message)" -ForegroundColor Red
        $allOk = $false
    }
}

# 3) Backend health
try {
    $health = Invoke-RestMethod -Uri "$BackendUrl/health" -TimeoutSec 8
    Write-Host "[OK] Backend health: $($health.status)" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Backend health check failed: $($_.Exception.Message)" -ForegroundColor Red
    $allOk = $false
}

# 4) Chat
try {
    $body = @{ message = "responda apenas: OK"; session_id = "local-validate" } | ConvertTo-Json
    $chat = Invoke-RestMethod -Uri "$BackendUrl/chat/process" -Method Post -ContentType "application/json" -Body $body -TimeoutSec 45
    Write-Host "[OK] Chat response: $($chat.response)" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Chat request failed: $($_.Exception.Message)" -ForegroundColor Red
    $allOk = $false
}

# 5) TTS endpoint
$ttsFile = Join-Path $PSScriptRoot "..\test_tts_local.mp3"
try {
    Invoke-WebRequest "$BackendUrl/tts?text=jarvis+online+local&lang=pt" -OutFile $ttsFile -TimeoutSec 45 | Out-Null
    if ((Test-Path $ttsFile) -and ((Get-Item $ttsFile).Length -gt 0)) {
        Write-Host "[OK] TTS generated file: $ttsFile" -ForegroundColor Green
    } else {
        throw "TTS file not generated or empty"
    }
} catch {
    Write-Host "[FAIL] TTS endpoint failed: $($_.Exception.Message)" -ForegroundColor Red
    $allOk = $false
}

Write-Host ""
if ($allOk) {
    Write-Host "RESULT: ALL CHECKS PASSED" -ForegroundColor Green
    exit 0
}

Write-Host "RESULT: SOME CHECKS FAILED" -ForegroundColor Yellow
exit 1
