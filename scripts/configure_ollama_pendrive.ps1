param(
    [string]$ModelsPath = "D:\Ollama\models",
    [switch]$AlsoSetJarvisLocal
)

Write-Host "=== JARVIS / Ollama USB Setup ===" -ForegroundColor Cyan
Write-Host "Models path: $ModelsPath"

if (-not (Test-Path $ModelsPath)) {
    New-Item -Path $ModelsPath -ItemType Directory -Force | Out-Null
    Write-Host "Created models directory: $ModelsPath" -ForegroundColor Yellow
}

[Environment]::SetEnvironmentVariable("OLLAMA_MODELS", $ModelsPath, "User")
$env:OLLAMA_MODELS = $ModelsPath
Write-Host "Set OLLAMA_MODELS (User): $ModelsPath" -ForegroundColor Green

if ($AlsoSetJarvisLocal) {
    [Environment]::SetEnvironmentVariable("JARVIS_OLLAMA_URL", "http://localhost:11434", "User")
    $env:JARVIS_OLLAMA_URL = "http://localhost:11434"
    Write-Host "Set JARVIS_OLLAMA_URL (User): http://localhost:11434" -ForegroundColor Green
}

Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1) Close and reopen Ollama app/service"
Write-Host "2) Open a new terminal and run: ollama list"
Write-Host "3) Validate stack: powershell -ExecutionPolicy Bypass -File scripts\validate_jarvis_local.ps1"
Write-Host ""
Write-Host "Tip: keep the USB drive mounted with same drive letter before starting Ollama." -ForegroundColor Yellow
