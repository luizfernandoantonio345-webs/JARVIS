
# JARVIS v6.0 — Deployment Guide

Complete step-by-step guide to deploy JARVIS v6.0 to production.

**Estimated time**: 30-45 minutes (including Ollama setup)

---

## Prerequisites

- **Python**: 3.10 or higher
- **Ollama**: Latest version (https://ollama.ai)
- **Node.js**: 18+ (optional, if building frontend separately)
- **Git**: For cloning repository
- **RAM**: Minimum 8GB (16GB recommended for Ollama + Whisper)
- **Disk**: Minimum 20GB free (Ollama models: ~5GB, Whisper: ~3GB)

### System Requirements

| Component | Min | Recommended |
|-----------|-----|-------------|
| CPU Cores | 2 | 4+ |
| RAM | 8GB | 16GB |
| Disk (SSD) | 20GB | 50GB |
| GPU | None | NVIDIA (optional) |

---

## Step 1: Clone Repository

```bash
cd c:\Users\YourUsername  # or /home/username
git clone https://github.com/cibernetico/JARVIS.git
cd JARVIS
```

---

## Step 2: Setup Python Virtual Environment

### Windows

```powershell
cd c:\Users\cibernetico\JARVIS

# Create venv
python -m venv venv311

# Activate
.\venv311\Scripts\Activate.ps1

# If execution policy error, run:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
.\venv311\Scripts\Activate.ps1
```

### Linux / macOS

```bash
cd ~/JARVIS

# Create venv
python3.10 -m venv venv311

# Activate
source venv311/bin/activate
```

---

## Step 3: Install Python Dependencies

```bash
# Upgrade pip
python -m pip install --upgrade pip

# Install main dependencies
pip install -r backend/requirements.txt

# Install dev dependencies (optional, for testing)
pip install -r requirements-dev.txt
```

**Expected time**: 5-10 minutes (first install may take longer)

---

## Step 4: Setup Ollama

### Windows

1. Download Ollama from https://ollama.ai/download/windows
2. Run installer and complete setup
3. Ollama will run as a service on `http://localhost:11434`
4. Verify installation:
   ```powershell
   curl http://localhost:11434/api/tags
   ```

### Linux

```bash
curl https://ollama.ai/install.sh | sh

# Start Ollama service
sudo systemctl start ollama
sudo systemctl enable ollama

# Verify
curl http://localhost:11434/api/tags
```

### macOS

```bash
brew install ollama
brew services start ollama

# Verify
curl http://localhost:11434/api/tags
```

---

## Step 5: Download LLM Model

```bash
ollama pull qwen2:0.5b

# Or use your preferred model
ollama pull phi:latest
ollama pull mistral:latest
```

**Expected time**: 3-5 minutes (depends on model size)

List available models:

```bash
ollama list
```

---

## Step 6: Configure Environment

Create `.env` file in project root:

```bash
# ── IA LOCAL (PC1) ────────────────────────────────────────────────────
JARVIS_OLLAMA_URL=http://127.0.0.1:11434
JARVIS_MODEL=qwen2:0.5b
JARVIS_LOCAL_MODEL=qwen2:0.5b
JARVIS_FALLBACK_MODEL=tinyllama:latest
JARVIS_EMBEDDING_MODEL=nomic-embed-text
JARVIS_TIMEOUT=15
JARVIS_MAX_RETRIES=3

# ── BACKEND ───────────────────────────────────────────────────────
JARVIS_HOST=0.0.0.0
JARVIS_PORT=8000
JARVIS_DEBUG=false
JARVIS_LOG_LEVEL=INFO
JARVIS_SAFE_MODE=true

# ── VOZ ───────────────────────────────────────────────────────────
JARVIS_VOICE_ENABLED=true
JARVIS_TTS_VOICE=pt-BR-AntonioNeural
JARVIS_TTS_RATE=-12%
JARVIS_TTS_PITCH=-15Hz
JARVIS_STT_MODEL=small
JARVIS_WAKE_WORD=jarvis
JARVIS_USER_TITLE=Senhor
JARVIS_LANG=pt-BR

# ── OPTIONAL: External APIs ─────────────────────────────────────────
# JARVIS_ANTHROPIC_API_KEY=your-key-here
# JARVIS_OPENAI_API_KEY=your-key-here
```

**Note**: For production, use strong secret management (AWS Secrets Manager, HashiCorp Vault, etc.)

---

## Step 7: Test Backend Startup

```bash
# Windows
.\venv311\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Linux/macOS
source venv311/bin/activate
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

**Expected output**:
```
INFO:     Application startup complete
INFO:     Uvicorn running on http://0.0.0.0:8000
```

Visit: http://localhost:8000/health

Expected response:
```json
{
  "status": "ok",
  "version": "5.2",
  "components": {
    "llm": {"ok": true},
    "memory": {"ok": true},
    "voice": {"ok": true},
    ...
  }
}
```

---

## Step 8: Setup Frontend (Optional)

```bash
cd frontend

# Install dependencies
npm install

# Build for production
npm run build

# Or run in dev mode
npm run dev  # http://localhost:3000
```

---

## Step 9: Run Smoke Tests

```bash
# Windows
.\venv311\Scripts\python.exe _legacy/smoke_final.py

# Linux/macOS
python _legacy/smoke_final.py
```

**Expected result**: 14+ PASS | 0 FAIL

---

## Step 10: Deploy to Production

### Option A: Systemd Service (Linux)

Create `/etc/systemd/system/jarvis.service`:

```ini
[Unit]
Description=JARVIS v6.0 Backend
After=network.target

[Service]
Type=notify
User=jarvis
WorkingDirectory=/home/jarvis/JARVIS
Environment="PATH=/home/jarvis/JARVIS/venv311/bin"
ExecStart=/home/jarvis/JARVIS/venv311/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable jarvis
sudo systemctl start jarvis
sudo systemctl status jarvis
```

View logs:

```bash
sudo journalctl -u jarvis -f
```

### Option B: Windows Service (using NSSM)

```powershell
# Install NSSM
choco install nssm

# Register service
nssm install JARVIS "C:\Users\cibernetico\JARVIS\venv311\Scripts\python.exe" "-m uvicorn backend.main:app --host 0.0.0.0 --port 8000"

# Start
nssm start JARVIS

# Check status
nssm status JARVIS
```

### Option C: Docker Compose

```bash
docker-compose up -d
```

---

## Step 11: Configure Reverse Proxy (Nginx)

**File**: `/etc/nginx/sites-available/jarvis`

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name jarvis.example.com;

    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name jarvis.example.com;

    # SSL Certificates
    ssl_certificate /etc/letsencrypt/live/jarvis.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/jarvis.example.com/privkey.pem;

    # Proxy to Backend
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket support
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }
}
```

Enable:

```bash
sudo ln -s /etc/nginx/sites-available/jarvis /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## Step 12: Database Backup Strategy

Create backup script: `scripts/backup_db.sh`

```bash
#!/bin/bash
BACKUP_DIR="/backups/jarvis"
mkdir -p $BACKUP_DIR

# Daily backup
sqlite3 data/jarvis_memory.db ".backup '/backups/jarvis/jarvis_$(date +%Y%m%d_%H%M%S).db'"

# Keep only last 30 days
find $BACKUP_DIR -type f -mtime +30 -delete
```

Setup cron job:

```bash
# Every 6 hours
0 */6 * * * /home/jarvis/JARVIS/scripts/backup_db.sh
```

---

## Step 13: Monitoring & Health Checks

Setup monitoring script: `scripts/health_monitor.py`

Run as periodic task:

```bash
# Linux: Every 5 minutes
*/5 * * * * python /home/jarvis/JARVIS/scripts/health_monitor.py

# Windows: Use Task Scheduler
```

Expected checks:

- Backend HTTP 200 on `/health`
- Ollama responding
- Database file accessible
- CPU/RAM within limits
- Disk space available

---

## Troubleshooting

### 1. Ollama not connecting

```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Restart Ollama
ollama serve  # or service restart on Windows/Linux
```

### 2. Port 8000 in use

```bash
# Find process using port
netstat -ano | findstr :8000  # Windows
lsof -i :8000  # Linux/macOS

# Kill process
taskkill /PID <PID> /F  # Windows
kill -9 <PID>  # Linux/macOS

# Or use different port
python -m uvicorn backend.main:app --port 8001
```

### 3. Out of memory

- Reduce Whisper model size: `JARVIS_STT_MODEL=tiny`
- Reduce Ollama context window
- Use GPU if available

### 4. Slow responses

- Warm up model: Run a test query
- Check CPU/RAM usage
- Monitor network latency
- Consider using smaller LLM

---

## Post-Deployment Verification

```bash
# 1. Check health
curl http://localhost:8000/health

# 2. Run smoke test
python _legacy/smoke_final.py

# 3. Check logs
tail -f jarvis.log

# 4. Test chat endpoint
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"hello","session_id":"test"}'

# 5. Visit frontend
# http://localhost:3000
```

---

## Performance Tuning

| Setting | Default | Recommended | Notes |
|---------|---------|-------------|-------|
| Uvicorn workers | 1 | CPU cores | Increase for load |
| Request timeout | 120s | 300s | For long operations |
| Cache backend | InMemory | Redis | For scalability |
| Log level | INFO | WARNING | For production |
| Model context | 2048 | 4096 | Increase for better responses |

---

## Security Checklist

- [ ] Use HTTPS in production (Let's Encrypt)
- [ ] Enable firewall (UFW, Windows Firewall)
- [ ] Restrict port access
- [ ] Set strong SECRET_KEY for sessions
- [ ] Enable rate limiting
- [ ] Setup log rotation
- [ ] Regular database backups
- [ ] Monitor for suspicious activity
- [ ] Keep dependencies updated

---

## Support & Troubleshooting

For issues:

1. Check logs: `tail -f jarvis.log`
2. Run diagnostics: `python scripts/health_monitor.py`
3. Review deployment guide above
4. Check GitHub issues: https://github.com/cibernetico/JARVIS/issues

---

**Date**: May 25, 2026  
**Version**: 6.0  
**Status**: Production Ready
