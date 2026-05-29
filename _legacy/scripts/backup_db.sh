#!/bin/bash
# JARVIS v6.0 - Database Backup Script (Linux/macOS)
# 
# Backs up SQLite database to timestamped file
# Usage: ./backup_db.sh
#        ./backup_db.sh --destination /custom/path
#        ./backup_db.sh --compress
#        ./backup_db.sh --upload s3://bucket/path

set -e

# ════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ════════════════════════════════════════════════════════════════════════════

DB_SOURCE="data/jarvis_memory.db"
BACKUP_DIR="${BACKUP_DIR:-.backup}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
COMPRESS=false
UPLOAD_DEST=""

# ════════════════════════════════════════════════════════════════════════════
# PARSE ARGUMENTS
# ════════════════════════════════════════════════════════════════════════════

while [[ $# -gt 0 ]]; do
    case $1 in
        --destination)
            BACKUP_DIR="$2"
            shift 2
            ;;
        --compress)
            COMPRESS=true
            shift
            ;;
        --upload)
            UPLOAD_DEST="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# ════════════════════════════════════════════════════════════════════════════
# FUNCTIONS
# ════════════════════════════════════════════════════════════════════════════

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

error() {
    echo "❌ ERROR: $1" >&2
    exit 1
}

# ════════════════════════════════════════════════════════════════════════════
# VALIDATION
# ════════════════════════════════════════════════════════════════════════════

if [[ ! -f "$DB_SOURCE" ]]; then
    error "Database file not found: $DB_SOURCE"
fi

mkdir -p "$BACKUP_DIR" || error "Failed to create backup directory: $BACKUP_DIR"

# ════════════════════════════════════════════════════════════════════════════
# BACKUP PROCESS
# ════════════════════════════════════════════════════════════════════════════

log "Starting database backup..."

BACKUP_FILE="$BACKUP_DIR/jarvis_$TIMESTAMP.db"

# Copy database file
cp "$DB_SOURCE" "$BACKUP_FILE" || error "Failed to copy database"
log "✓ Database copied to $BACKUP_FILE"

# Get file size
SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
log "✓ Backup size: $SIZE"

# Compress if requested
if [[ "$COMPRESS" == "true" ]]; then
    log "Compressing backup..."
    gzip "$BACKUP_FILE" || error "Failed to compress backup"
    BACKUP_FILE="$BACKUP_FILE.gz"
    COMPRESSED_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    log "✓ Compressed size: $COMPRESSED_SIZE"
fi

# Verify backup
if [[ ! -f "$BACKUP_FILE" ]]; then
    error "Backup verification failed: file not found"
fi
log "✓ Backup verified"

# Upload to S3 (if configured)
if [[ -n "$UPLOAD_DEST" ]]; then
    log "Uploading to S3: $UPLOAD_DEST"
    aws s3 cp "$BACKUP_FILE" "$UPLOAD_DEST/" || error "S3 upload failed"
    log "✓ Upload complete"
fi

# ════════════════════════════════════════════════════════════════════════════
# CLEANUP (retention policy)
# ════════════════════════════════════════════════════════════════════════════

log "Applying retention policy (keeping last $RETENTION_DAYS days)..."
find "$BACKUP_DIR" -name "jarvis_*.db*" -type f -mtime +$RETENTION_DAYS -delete
log "✓ Cleanup complete"

# ════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ════════════════════════════════════════════════════════════════════════════

BACKUP_COUNT=$(find "$BACKUP_DIR" -name "jarvis_*.db*" -type f | wc -l)

log "════════════════════════════════════════════════"
log "✅ BACKUP SUCCESSFUL"
log "════════════════════════════════════════════════"
log "Location: $BACKUP_FILE"
log "Size: $SIZE"
log "Backups available: $BACKUP_COUNT"
log "════════════════════════════════════════════════"
