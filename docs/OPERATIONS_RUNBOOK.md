# JARVIS v6.0 — Operations Runbook

Daily operations manual for JARVIS v6.0 production environment.

---

## 1. Normal Operations

### 1.1 Starting JARVIS

#### Windows

```powershell
# Method 1: Direct (dev/testing)
cd c:\Users\cibernetico\JARVIS
.\venv311\Scripts\Activate.ps1
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Method 2: Service (production)
nssm start JARVIS
nssm status JARVIS

# Method 3: Docker
docker-compose up -d
```

#### Linux/macOS

```bash
# Method 1: Direct
cd ~/JARVIS
source venv311/bin/activate
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Method 2: Systemd
sudo systemctl start jarvis
sudo systemctl status jarvis

# Method 3: Docker
docker-compose up -d
```

### 1.2 Stopping JARVIS

#### Windows

```powershell
# Service
nssm stop JARVIS

# Docker
docker-compose down
```

#### Linux/macOS

```bash
# Systemd
sudo systemctl stop jarvis

# Docker
docker-compose down
```

### 1.3 Restarting JARVIS

#### Windows

```powershell
# Service
nssm restart JARVIS

# Direct (must stop first)
# Use Ctrl+C in terminal running process
```

#### Linux/macOS

```bash
# Systemd
sudo systemctl restart jarvis

# Check status
sudo systemctl status jarvis
```

---

## 2. Daily Health Checks

### 2.1 Pre-Shift Checklist (Morning)

```bash
# 1. Check service status
systemctl status jarvis  # Linux
nssm status JARVIS       # Windows

# 2. Health endpoint
curl http://localhost:8000/health

# 3. Response expected:
# {
#   "status": "ok",
#   "version": "6.0",
#   "components": {
#     "backend": {"ok": true},
#     "llm": {"ok": true},
#     "memory": {"ok": true},
#     "voice": {"ok": true}
#   }
# }

# 4. Check system resources
top -b -n 1 | head -15  # Linux
tasklist /v             # Windows

# 5. Check disk space
df -h                   # Linux
Get-Volume             # Windows

# 6. Check database
ls -lh data/jarvis_memory.db  # Linux
ls data/jarvis_memory.db      # Windows
```

### 2.2 Resource Monitoring

Monitor during operation:

| Resource | Check | Threshold | Action |
|----------|-------|-----------|--------|
| CPU | `top` or Task Manager | >80% sustained | Scale up, optimize queries |
| RAM | `free -h` or Resource Monitor | >85% | Restart service, increase RAM |
| Disk | `df -h` | <5GB free | Archive/delete old logs, backups |
| Connections | `netstat -an` | >100 active | Check for connection leaks |

### 2.3 Log Review

Check for errors:

```bash
# Real-time (Linux)
journalctl -u jarvis -f

# From file (all platforms)
tail -f jarvis.log
grep ERROR jarvis.log
grep WARN jarvis.log
```

### 2.4 Performance Metrics

Access metrics endpoint:

```bash
curl http://localhost:8000/metrics
```

Key metrics:

- `jarvis_requests_total`: Total requests
- `jarvis_request_duration_seconds`: Response time
- `jarvis_active_connections`: Current WebSocket connections
- `jarvis_memory_queries`: Experience memory operations
- `jarvis_tts_duration_seconds`: Voice synthesis time

---

## 3. Common Issues & Fixes

### 3.1 Backend Won't Start

**Symptoms**: Service fails immediately, port bind error

**Diagnosis**:

```bash
# Check if port in use
netstat -ano | findstr :8000  # Windows
lsof -i :8000                 # Linux

# Check logs for errors
tail -20 jarvis.log
```

**Fix**:

```bash
# Option 1: Kill process using port
taskkill /PID <PID> /F  # Windows
kill -9 <PID>           # Linux

# Option 2: Use different port
export JARVIS_PORT=8001
python -m uvicorn backend.main:app --port 8001

# Option 3: Wait 60s and retry (port may be in TIME_WAIT state)
sleep 60
systemctl restart jarvis
```

### 3.2 Ollama Not Responding

**Symptoms**: LLM requests fail with "Connection refused"

**Diagnosis**:

```bash
# Check Ollama service
ollama serve  # Should start without error

# Verify connection
curl http://localhost:11434/api/tags
```

**Fix**:

```bash
# Windows: Restart Ollama
taskkill /IM ollama.exe /F
ollama serve

# Linux: Restart service
sudo systemctl restart ollama

# Manual restart: kill process and start again
kill -9 $(pgrep -f ollama)
ollama serve
```

### 3.3 High Memory Usage

**Symptoms**: RAM >85%, OOM errors

**Diagnosis**:

```bash
# Check processes
top -p $(pgrep -f "uvicorn|ollama|python")
```

**Fix**:

```bash
# 1. Reduce model context window (.env)
JARVIS_MODEL_CONTEXT=2048

# 2. Use smaller Whisper model
JARVIS_STT_MODEL=tiny

# 3. Enable GPU offloading
export OLLAMA_NUM_GPU=1

# 4. Restart service
systemctl restart jarvis
```

### 3.4 Slow Responses

**Symptoms**: Chat takes >5 seconds, voice lags

**Diagnosis**:

```bash
# Check response time
time curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"test"}'

# Monitor CPU/I/O
top -n 1 | head -20
iotop
```

**Fix**:

```bash
# 1. Warm up model (first request slower)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"hello"}'

# 2. Use GPU acceleration
OLLAMA_NUM_GPU=1

# 3. Reduce log level
JARVIS_LOG_LEVEL=WARN

# 4. Optimize database
sqlite3 data/jarvis_memory.db "VACUUM;"
```

### 3.5 WebSocket Disconnections

**Symptoms**: Chat sessions drop, frontend shows "Connection lost"

**Diagnosis**:

```bash
# Check active connections
netstat -an | grep ESTABLISHED | wc -l

# Monitor WebSocket traffic
tcpdump -i any -n 'tcp port 8000'
```

**Fix**:

```bash
# 1. Check for timeout issues
# Increase WebSocket timeout in nginx (120s → 300s)

# 2. Check firewall
sudo ufw status
sudo iptables -L

# 3. Verify DNS resolution
nslookup jarvis.example.com

# 4. Restart service
systemctl restart jarvis
```

### 3.6 Database Lock Errors

**Symptoms**: "database is locked", concurrent request failures

**Diagnosis**:

```bash
# Check open database connections
lsof | grep jarvis_memory.db

# Check journal file (indicates lock)
ls -la data/jarvis_memory.db*
```

**Fix**:

```bash
# 1. Remove stale lock file
rm -f data/jarvis_memory.db-journal
rm -f data/jarvis_memory.db-wal

# 2. Vacuum database
sqlite3 data/jarvis_memory.db "VACUUM;"

# 3. Check for hanging transactions
# Increase WAL (Write-Ahead Logging) timeout

# 4. Restart service
systemctl restart jarvis
```

---

## 4. Backup & Recovery

### 4.1 Daily Backup

```bash
#!/bin/bash
# scripts/backup_db.sh

BACKUP_DIR="/backups/jarvis"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Backup database
cp data/jarvis_memory.db $BACKUP_DIR/jarvis_$TIMESTAMP.db

# Compress
gzip $BACKUP_DIR/jarvis_$TIMESTAMP.db

# Verify
if [ -f "$BACKUP_DIR/jarvis_$TIMESTAMP.db.gz" ]; then
    echo "Backup successful: $BACKUP_DIR/jarvis_$TIMESTAMP.db.gz"
else
    echo "ERROR: Backup failed!"
    exit 1
fi

# Keep only last 30 days
find $BACKUP_DIR -type f -mtime +30 -delete

# Upload to cloud (optional)
# aws s3 cp $BACKUP_DIR/jarvis_$TIMESTAMP.db.gz s3://backups/jarvis/
```

Setup cron:

```bash
# Backup every 6 hours
0 */6 * * * /home/jarvis/JARVIS/scripts/backup_db.sh
```

### 4.2 Recovery Procedure

```bash
# 1. Stop service
sudo systemctl stop jarvis

# 2. List backups
ls -lh /backups/jarvis/

# 3. Restore from backup
gunzip /backups/jarvis/jarvis_YYYYMMDD_HHMMSS.db.gz
cp /backups/jarvis/jarvis_YYYYMMDD_HHMMSS.db data/jarvis_memory.db

# 4. Verify database
sqlite3 data/jarvis_memory.db ".schema"

# 5. Start service
sudo systemctl start jarvis

# 6. Check status
sudo systemctl status jarvis
```

---

## 5. Performance Optimization

### 5.1 Cache Management

```bash
# Clear Redis cache (if used)
redis-cli FLUSHALL

# Or in Python:
# from backend.core.cache import cache_manager
# cache_manager.clear()
```

### 5.2 Database Optimization

```bash
# Analyze query performance
sqlite3 data/jarvis_memory.db "EXPLAIN QUERY PLAN SELECT * FROM experiences;"

# Rebuild indexes
sqlite3 data/jarvis_memory.db "REINDEX;"

# Vacuum (defragment)
sqlite3 data/jarvis_memory.db "VACUUM;"
```

### 5.3 Log Rotation

Setup logrotate on Linux:

```
# /etc/logrotate.d/jarvis
/home/jarvis/JARVIS/jarvis.log {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    create 0644 jarvis jarvis
    sharedscripts
    postrotate
        systemctl reload jarvis > /dev/null 2>&1 || true
    endscript
}
```

Test:

```bash
logrotate -d /etc/logrotate.d/jarvis
```

---

## 6. Monitoring & Alerts

### 6.1 Health Check Script

Create `scripts/health_monitor.py`:

```python
#!/usr/bin/env python
import requests
import json
from datetime import datetime

endpoints = {
    "health": "http://localhost:8000/health",
    "metrics": "http://localhost:8000/metrics",
}

alerts = []

for name, url in endpoints.items():
    try:
        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            alerts.append(f"WARN: {name} returned {response.status_code}")
        print(f"✓ {name}: {response.status_code}")
    except Exception as e:
        alerts.append(f"ALERT: {name} failed: {e}")
        print(f"✗ {name}: {e}")

if alerts:
    print("\n⚠️ ALERTS:")
    for alert in alerts:
        print(f"  - {alert}")
```

Run periodically:

```bash
*/5 * * * * python /home/jarvis/JARVIS/scripts/health_monitor.py
```

### 6.2 Resource Monitoring

Use system tools:

- **Linux**: `htop`, `iotop`, `nethogs`
- **Windows**: Task Manager, Resource Monitor, Get-Process PowerShell
- **Docker**: `docker stats`

---

## 7. Emergency Procedures

### 7.1 Service Crash

```bash
# 1. Check status
sudo systemctl status jarvis

# 2. View recent logs
sudo journalctl -u jarvis -n 50

# 3. Restart service
sudo systemctl restart jarvis

# 4. Monitor
sudo journalctl -u jarvis -f
```

### 7.2 Database Corruption

```bash
# 1. Stop service
sudo systemctl stop jarvis

# 2. Check database integrity
sqlite3 data/jarvis_memory.db "PRAGMA integrity_check;"

# 3. If corrupted, restore from backup
cp /backups/jarvis/jarvis_LATEST.db data/jarvis_memory.db

# 4. Restart
sudo systemctl start jarvis
```

### 7.3 Full System Restart

```bash
# Graceful restart
sudo systemctl stop jarvis
sudo systemctl stop ollama
sleep 5
sudo systemctl start ollama
sleep 10  # Let Ollama initialize
sudo systemctl start jarvis

# Check status
sudo systemctl status jarvis
sudo systemctl status ollama
```

---

## 8. Escalation Path

| Issue | Severity | Timeout | Action |
|-------|----------|---------|--------|
| High latency | Low | 2 hours | Monitor, optimize queries |
| Component down | Medium | 15 mins | Restart, check logs |
| Multiple failures | High | 5 mins | Escalate, consider rollback |
| Data corruption | Critical | 1 min | Restore backup, notify |

---

## 9. Maintenance Window

Schedule weekly maintenance (Sunday 2AM UTC):

```bash
# 1. Full backup
./scripts/backup_db.sh

# 2. Database optimization
sqlite3 data/jarvis_memory.db "VACUUM; ANALYZE;"

# 3. Log cleanup
rm -f logs/jarvis.log.*

# 4. Cache clear
redis-cli FLUSHALL

# 5. Health check
python scripts/health_monitor.py

# 6. Update dependencies (if needed)
pip install --upgrade -r backend/requirements.txt
```

---

## Contacts & Resources

- **Documentation**: /docs/
- **Logs**: ~/JARVIS/jarvis.log
- **GitHub**: https://github.com/cibernetico/JARVIS
- **Issues**: https://github.com/cibernetico/JARVIS/issues

**Last Updated**: May 25, 2026  
**Version**: 6.0
