param(
    [string]$ShortcutName = "JARVIS - Inicio Rapido.lnk"
)

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$launcherPath = Join-Path $repoRoot "start_jarvis_one_click.bat"

if (-not (Test-Path $launcherPath)) {
    Write-Host "[FAIL] Launcher nao encontrado: $launcherPath" -ForegroundColor Red
    exit 1
}

$desktopPath = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktopPath $ShortcutName

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $launcherPath
$shortcut.WorkingDirectory = $repoRoot
$shortcut.Description = "Inicia e valida o JARVIS em 1 clique"
$shortcut.IconLocation = "%SystemRoot%\System32\shell32.dll,220"
$shortcut.Save()

Write-Host "[OK] Atalho criado com sucesso:" -ForegroundColor Green
Write-Host "     $shortcutPath"