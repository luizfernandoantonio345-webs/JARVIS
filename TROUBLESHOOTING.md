# 🔧 TROUBLESHOOTING GUIDE — JARVIS v5.2

**Common Issues & Solutions**

---

## ❓ FAQ

### 1. Servidor não inicia

**Erro:** `Address already in use` ou `Port 8000 in use`

**Solução:**
```bash
# Windows: Find process using port 8000
netstat -ano | findstr :8000

# Result: TCP 0.0.0.0:8000 LISTENING 12345
# Kill process
taskkill /PID 12345 /F

# Linux/Mac: Find and kill
lsof -i :8000
kill -9 <PID>

# Or use different port
python -m uvicorn backend.main:app --port 8001
```

---

### 2. Ollama não conecta

**Erro:** `Connection refused` ou `Cannot reach Ollama`

**Checklist:**
```bash
# 1. Verificar se Ollama está rodando
curl http://192.168.0.106:11434/api/tags

# Se falhar:
# - Windows: Restart Ollama from Start Menu
# - Linux: sudo systemctl restart ollama
# - Mac: brew services restart ollama

# 2. Verificar URL configurada
echo $JARVIS_OLLAMA_URL    # Should show correct URL

# 3. Se usar Docker, verificar network
docker network inspect jarvis_network

# 4. Test from inside container
docker exec jarvis-backend curl http://ollama:11434/api/tags
```

---

### 3. Chat retorna erro 500

**Erro:** `Internal Server Error`

**Diagnóstico:**
```bash
# 1. Check server logs
tail -f backend/logs/jarvis.log

# 2. Test health endpoint
curl http://localhost:8000/health

# 3. Test chat directly
curl -X POST http://localhost:8000/chat/process \
  -H "Content-Type: application/json" \
  -d '{"message":"hello","session_id":"test"}'

# 4. Check Ollama is responding
ollama list  # Should show models

# 5. If model missing, pull it
ollama pull qwen2:0.5b
```

---

### 4. WebSocket desconecta

**Erro:** Dashboard mostra `Offline` ou `Reconnecting`

**Solução:**
```bash
# 1. Check WebSocket endpoint
curl -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" \
  http://localhost:8000/ws/jarvis

# 2. Check firewall/network
netstat -ano | findstr :8000

# 3. Check server logs for connection issues
grep -i "websocket\|disconnect" backend/logs/jarvis.log

# 4. Test from different browser (cache issue?)
# Open in Incognito/Private mode

# 5. Check CORS headers
curl -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: Content-Type" \
  http://localhost:8000/health
```

---

### 5. Memory database crescendo muito

**Problema:** `memory.db` > 1GB

**Solução:**
```bash
# 1. Check size
ls -lh backend/memory.db

# 2. Backup
cp backend/memory.db backend/memory.db.backup

# 3. Cleanup old entries (>30 days)
python << 'EOF'
import sqlite3
import time

conn = sqlite3.connect('backend/memory.db')
threshold = time.time() - (30 * 86400)  # 30 days ago

cursor = conn.cursor()
cursor.execute("DELETE FROM memory WHERE timestamp < ?", (threshold,))
deleted = cursor.rowcount

conn.commit()
conn.close()

print(f"Deleted {deleted} old entries")
EOF

# 4. VACUUM to reclaim space
python << 'EOF'
import sqlite3
conn = sqlite3.connect('backend/memory.db')
conn.execute("VACUUM")
conn.close()
print("Database optimized")
EOF
```

---

### 6. Rate limiting rejeitando requisições

**Erro:** `HTTP 429 - Too Many Requests`

**Solução:**
```bash
# 1. Check current limits
grep -A 5 "LIMITS = " backend/middleware/rate_limiter.py

# 2. Adjust if needed (in config)
# Edit backend/middleware/rate_limiter.py
# Increase limits or change to sessionless

# 3. Wait for reset
# Default reset: 1 minute after last request

# 4. Use different session_id
# Change JARVIS_SESSION_ID env var or pass in query:
curl http://localhost:8000/chat/process?session_id=session2 \
  -X POST -d '{"message":"test"}'
```

---

### 7. Voz não funciona

**Erro:** `Voice disabled` ou `Microphone not working`

**Checklist:**
```bash
# 1. Verificar se voz está habilitada
echo $JARVIS_DISABLE_VOICE  # Should be empty

# 2. Check audio device
python -m sounddevice

# 3. Install FFmpeg
pip install ffmpeg-python

# Windows: Download from https://ffmpeg.org/download.html
# Linux: sudo apt install ffmpeg
# Mac: brew install ffmpeg

# 4. Test STT (Faster Whisper)
python << 'EOF'
from faster_whisper import WhisperModel
model = WhisperModel("tiny")
print("STT model loaded OK")
EOF

# 5. Test TTS (Edge-TTS)
python << 'EOF'
import asyncio
import edge_tts

async def test_tts():
    communicate = edge_tts.Communicate(
        "Hello world",
        "pt-BR-AntonioNeural"
    )
    await communicate.save("test.mp3")
    print("TTS OK")

asyncio.run(test_tts())
EOF

# 6. Check permissions
# Windows: Settings > Privacy > Microphone
# Linux: Check PulseAudio settings
# Mac: System Preferences > Security > Microphone
```

---

### 8. Docker: `CORS error`

**Erro:** Browser: `Cross-Origin Request Blocked`

**Solução:**
```bash
# 1. Check CORS config in main.py
grep -A 5 "CORSMiddleware" backend/main.py

# 2. For production, restrict origins:
# Change allow_origins=["*"] to:
allow_origins=[
    "https://yourdomain.com",
    "http://localhost:3000"
]

# 3. Rebuild image
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# 4. Clear browser cache
# Ctrl+Shift+Delete → Clear all time

# 5. Test CORS headers
curl -v http://localhost:8000/health | grep -i access-control
```

---

### 9. `Import error` ou `ModuleNotFoundError`

**Erro:** `ModuleNotFoundError: No module named 'voice'`

**Solução:**
```bash
# 1. Check Python path
python -c "import sys; print(sys.path)"

# 2. Verify file exists
ls -la backend/voice/

# 3. Add __init__.py if missing
touch backend/voice/__init__.py

# 4. Reinstall dependencies
pip install -r backend/requirements.txt

# 5. Check for circular imports
grep -r "from voice import\|from autonomy import" backend/

# 6. Test import directly
python -c "from backend.voice import *; print('OK')"
```

---

### 10. Logs não são criados

**Problema:** `backend/logs/jarvis.log` vazio ou não criado

**Solução:**
```bash
# 1. Check permissions
ls -la backend/logs/

# 2. Create directory if missing
mkdir -p backend/logs

# 3. Check write permissions
touch backend/logs/test.txt

# 4. Verify logging config
grep -A 5 "logging.basicConfig" backend/main.py

# 5. Check log level
grep "LOG_LEVEL\|log.setLevel" backend/*.py

# 6. Test logging
python << 'EOF'
import logging
logging.basicConfig(
    filename='backend/logs/test.log',
    level=logging.INFO
)
logging.info("Test log entry")
print("Check backend/logs/test.log")
EOF
```

---

## 🚨 CRITICAL ERRORS

### `Circuit breaker open`

**Causa:** Muitos erros em sequência  
**Solução:**
```bash
# 1. Wait 5-10 minutes for reset
# ou
# 2. Restart servidor
# ou
# 3. Reduce concurrency:
export JARVIS_AUTONOMY_MAX_ACTIONS_PER_MINUTE=1
```

### `Memory database locked`

**Causa:** Múltiplos acessos simultâneos  
**Solução:**
```bash
# 1. Check if another process has lock
lsof backend/memory.db

# 2. Restart server
systemctl restart jarvis

# 3. Or use WAL mode (better for concurrent)
python << 'EOF'
import sqlite3
conn = sqlite3.connect('backend/memory.db')
conn.execute("PRAGMA journal_mode=WAL")
conn.close()
EOF
```

### `Heap overflow / Out of memory`

**Causa:** Memory leak ou large dataset  
**Solução:**
```bash
# 1. Check memory usage
docker stats jarvis-backend
# or
ps aux | grep uvicorn

# 2. Check what's in memory
python << 'EOF'
import tracemalloc
tracemalloc.start()
# ... run code ...
top_stats = tracemalloc.take_snapshot().statistics('lineno')
for stat in top_stats[:10]:
    print(stat)
EOF

# 3. Increase memory limit (Docker)
# Edit docker-compose.yml:
services:
  jarvis:
    deploy:
      resources:
        limits:
          memory: 4G  # Increase from 1G

# 4. Restart
docker-compose down && docker-compose up -d
```

---

## 📊 MONITORING

### Health Dashboard

```bash
# Real-time metrics
watch -n 1 'curl -s http://localhost:8000/health | jq'

# Memory usage
ps aux | grep uvicorn | grep -v grep | awk '{print $6}'

# Network connections
netstat -an | grep 8000 | wc -l

# Error rate (from logs)
tail -f backend/logs/jarvis.log | grep ERROR
```

### Performance Profiling

```bash
# Profile CPU usage
python -m cProfile -s cumtime -m uvicorn backend.main:app

# Profile memory
python -m memory_profiler -m uvicorn backend.main:app

# Profile latency
python << 'EOF'
import time
import requests

start = time.time()
response = requests.post(
    'http://localhost:8000/chat/process',
    json={"message": "test", "session_id": "profile"}
)
elapsed = time.time() - start

print(f"Response time: {elapsed:.2f}s")
print(f"Status: {response.status_code}")
EOF
```

---

## 🆘 GET HELP

### Before reporting bug:

1. ✅ Update to latest version: `git pull`
2. ✅ Reinstall dependencies: `pip install -r requirements.txt`
3. ✅ Clear cache: `rm -rf __pycache__ .pytest_cache`
4. ✅ Check logs: `tail -f backend/logs/jarvis.log`
5. ✅ Search existing issues: GitHub Issues

### When reporting:

Include:
- [ ] Python version: `python --version`
- [ ] OS: Windows/Linux/Mac
- [ ] Last 50 lines of logs
- [ ] Steps to reproduce
- [ ] Expected vs actual behavior

---

**Last Updated:** 2026-05-13  
**Status:** ✅ MAINTAINED
