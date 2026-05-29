# JARVIS v6.0 - Database Backup Script (Windows PowerShell)
# 
# Backs up SQLite database to timestamped file
# Usage: .\backup_db.ps1
#        .\backup_db.ps1 -Destination "D:\backups"
#        .\backup_db.ps1 -Compress
#        .\backup_db.ps1 -Upload "s3://bucket/path"

param(
    [string]$Destination = ".\.backup",
    [switch]$Compress,
    [string]$Upload,
    [int]$RetentionDays = 30
)

# ════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ════════════════════════════════════════════════════════════════════════════

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$DBSource = "data\jarvis_memory.db"
$BackupDir = $Destination
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"

# ════════════════════════════════════════════════════════════════════════════
# FUNCTIONS
# ════════════════════════════════════════════════════════════════════════════

function Log {
    param([string]$Message)
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
}

function LogError {
    param([string]$Message)
    Write-Host "❌ ERROR: $Message" -ForegroundColor Red
    exit 1
}

function LogSuccess {
    param([string]$Message)
    Write-Host "✓ $Message" -ForegroundColor Green
}

# ════════════════════════════════════════════════════════════════════════════
# VALIDATION
# ════════════════════════════════════════════════════════════════════════════

Log "Starting JARVIS database backup..."

if (-not (Test-Path $DBSource)) {
    LogError "Database file not found: $DBSource"
}

if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
    Log "Created backup directory: $BackupDir"
}

# ════════════════════════════════════════════════════════════════════════════
# BACKUP PROCESS
# ════════════════════════════════════════════════════════════════════════════

$BackupFile = Join-Path $BackupDir "jarvis_$Timestamp.db"

Log "Copying database file..."
try {
    Copy-Item -Path $DBSource -Destination $BackupFile -Force
    LogSuccess "Database copied to $BackupFile"
} catch {
    LogError "Failed to copy database: $_"
}

# Get file size
$Size = (Get-Item $BackupFile).Length / 1MB
Log "Backup size: $($Size | Round 2) MB"

# ════════════════════════════════════════════════════════════════════════════
# COMPRESSION (Optional)
# ════════════════════════════════════════════════════════════════════════════

if ($Compress) {
    Log "Compressing backup..."
    
    # Use 7-Zip if available, otherwise fall back to System.IO.Compression
    if (Get-Command 7z -ErrorAction SilentlyContinue) {
        7z a -y "$BackupFile.7z" "$BackupFile" | Out-Null
        Remove-Item $BackupFile
        $BackupFile = "$BackupFile.7z"
        $CompressedSize = (Get-Item $BackupFile).Length / 1MB
        LogSuccess "Compressed to $($CompressedSize | Round 2) MB"
    } else {
        # Fallback using .NET
        [System.IO.Compression.ZipFile]::CreateFromDirectory(
            (Split-Path $BackupFile -Parent),
            "$BackupFile.zip",
            [System.IO.Compression.CompressionLevel]::Optimal,
            $false
        )
        Remove-Item $BackupFile
        $BackupFile = "$BackupFile.zip"
        $CompressedSize = (Get-Item $BackupFile).Length / 1MB
        LogSuccess "Compressed to $($CompressedSize | Round 2) MB"
    }
}

# ════════════════════════════════════════════════════════════════════════════
# VERIFICATION
# ════════════════════════════════════════════════════════════════════════════

if (-not (Test-Path $BackupFile)) {
    LogError "Backup verification failed: file not found"
}
LogSuccess "Backup verified"

# ════════════════════════════════════════════════════════════════════════════
# S3 UPLOAD (Optional)
# ════════════════════════════════════════════════════════════════════════════

if ($Upload) {
    Log "Uploading to S3: $Upload"
    try {
        # Requires AWS CLI to be installed
        & aws s3 cp $BackupFile "$Upload/" --no-progress
        LogSuccess "S3 upload complete"
    } catch {
        Log "⚠️ Warning: S3 upload failed (AWS CLI may not be installed)"
    }
}

# ════════════════════════════════════════════════════════════════════════════
# CLEANUP (Retention Policy)
# ════════════════════════════════════════════════════════════════════════════

Log "Applying retention policy (keeping last $RetentionDays days)..."

$CutoffDate = (Get-Date).AddDays(-$RetentionDays)
$OldBackups = Get-ChildItem -Path $BackupDir -Filter "jarvis_*.db*" -File | 
    Where-Object { $_.LastWriteTime -lt $CutoffDate }

if ($OldBackups) {
    $OldBackups | ForEach-Object {
        Log "Removing old backup: $($_.Name)"
        Remove-Item $_.FullName -Force
    }
    LogSuccess "Cleanup complete - removed $($OldBackups.Count) old backup(s)"
} else {
    LogSuccess "No old backups to remove"
}

# ════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ════════════════════════════════════════════════════════════════════════════

$BackupCount = (Get-ChildItem -Path $BackupDir -Filter "jarvis_*.db*" -File).Count

Write-Host "`n" + ("="*60)
Write-Host "✅ BACKUP SUCCESSFUL" -ForegroundColor Green
Write-Host ("="*60)
Write-Host "Location: $BackupFile"
Write-Host "Size: $($Size | Round 2) MB"
Write-Host "Backups available: $BackupCount"
Write-Host ("="*60) + "`n"

exit 0
