# 🚀 DEPLOYMENT GUIDE — JARVIS v5.2

**Versão:** 5.2  
**Status:** Production Ready  
**Última atualização:** 2026-05-13

---

## 📋 TABELA DE CONTEÚDOS

1. [Pré-requisitos](#pré-requisitos)
2. [Deployment Local](#deployment-local)
3. [Deployment Docker](#deployment-docker)
4. [Deployment Cloud](#deployment-cloud)
5. [Checklist Pré-Produção](#checklist-pré-produção)
6. [Monitoring & Logs](#monitoring--logs)
7. [Troubleshooting](#troubleshooting)

---

## ✅ Pré-requisitos

### Mínimo
- Python 3.11+
- 2GB RAM
- 1GB disco (sem models)
- Conexão de rede (Ollama, APIs externas)

### Recomendado
- Python 3.12
- 8GB+ RAM
- 10GB+ disco (com models)
- CPU com 4+ cores
- HTTPS/SSL certificate

### Dependências Externas
- **Ollama** (local LLM) — http://localhost:11434
- **FFmpeg** (áudio/vídeo) — `pip install ffmpeg-python`
- **PostgreSQL** (opcional, para scale) — não incluso

---

## 🖥️ DEPLOYMENT LOCAL

### Opção 1: Python Direto (Desenvolvimento)

```bash
# Clone
git clone <repo> && cd JARVIS

# Ambiente
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate      # Windows

# Instale
pip install -r backend/requirements.txt

# Configure
cp backend/.env.example backend/.env
# Edite backend/.env com suas configurações

# Inicie Ollama em outro terminal
ollama serve

# Inicie servidor
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

**Resultado esperado:**
```
INFO:JARVIS_CORE:Inicializando JARVIS...
INFO:JARVIS_CORE:✓ Health router carregado
INFO:JARVIS_CORE:[WAKE] Wake word 'JARVIS' ativa e escutando
INFO:     Uvicorn running on http://0.0.0.0:8000
```

---

### Opção 2: Script de Inicialização

**Windows (`start_jarvis.bat`):**
```batch
@echo off
cd %~dp0
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
pause
```

**Linux/Mac (`start_jarvis.sh`):**
```bash
#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

---

## 🐳 DEPLOYMENT DOCKER

### Pré-requisitos
- Docker 20.10+
- Docker Compose 2.0+

### Build & Run

```bash
# Build image
docker build -t jarvis:5.2 .

# Run single container
docker run -p 8000:8000 \
  -e JARVIS_OLLAMA_URL=http://host.docker.internal:11434 \
  jarvis:5.2

# Ou com docker-compose (incluindo Ollama)
docker-compose up -d

# Verificar status
docker ps
docker logs jarvis-backend
```

### Docker Compose (Recomendado)

```yaml
# docker-compose.yml já incluído
services:
  jarvis:
    ports: ["8000:8000"]
    environment:
      JARVIS_OLLAMA_URL: http://ollama:11434
    depends_on:
      - ollama

  ollama:
    ports: ["11434:11434"]
    volumes: ["ollama-data:/root/.ollama"]
```

**Comandos:**
```bash
# Iniciar
docker-compose up -d

# Parar
docker-compose down

# Ver logs
docker-compose logs -f jarvis

# Atualizar imagem
docker-compose pull && docker-compose up -d
```

---

## ☁️ DEPLOYMENT CLOUD

### AWS (EC2)

```bash
# Launch Ubuntu 22.04 LTS
# Security Group: Allow 8000, 22, 443

# SSH into instance
ssh -i key.pem ubuntu@<instance-ip>

# Update & Install
sudo apt update && sudo apt install -y python3.11 python3-pip git

# Clone & Setup
git clone <repo> && cd JARVIS
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

# Install Ollama
curl https://ollama.ai/install.sh | sh
ollama serve &  # Background

# Nginx reverse proxy
sudo apt install -y nginx
sudo nano /etc/nginx/sites-available/default

# Configuration:
upstream jarvis {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://jarvis;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

# Restart Nginx
sudo systemctl restart nginx

# Start JARVIS with systemd
sudo nano /etc/systemd/system/jarvis.service

[Unit]
Description=JARVIS AI System
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/JARVIS
ExecStart=/home/ubuntu/JARVIS/.venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target

# Enable & Start
sudo systemctl daemon-reload
sudo systemctl enable jarvis
sudo systemctl start jarvis
```

### Google Cloud Run

```bash
# Deploy containerized app
gcloud run deploy jarvis \
  --source . \
  --platform managed \
  --region us-central1 \
  --port 8000 \
  --allow-unauthenticated

# Set environment
gcloud run services update jarvis \
  --set-env-vars JARVIS_OLLAMA_URL=https://ollama-service.com
```

### Azure Container Instances

```bash
# Push to ACR
az acr build --registry <registry-name> --image jarvis:5.2 .

# Deploy
az container create \
  --resource-group myGroup \
  --name jarvis \
  --image <registry>.azurecr.io/jarvis:5.2 \
  --ports 8000 \
  --environment-variables JARVIS_OLLAMA_URL=http://ollama-host
```

---

## 📋 CHECKLIST PRÉ-PRODUÇÃO

### Código
- [ ] Todos testes passando: `pytest tests/ -v`
- [ ] Linting: `black backend/`, `flake8 backend/`
- [ ] Type checking: `mypy backend/`
- [ ] Security scan: `bandit -r backend/`
- [ ] Dependency check: `safety check`

### Configuração
- [ ] `.env` com todas variáveis necessárias
- [ ] `JARVIS_ENCRYPTION_KEY` configurada
- [ ] `JARVIS_OLLAMA_URL` apontando para Ollama correto
- [ ] Secrets não hardcoded no código

### Segurança
- [ ] CORS configurado (não `["*"]` em prod)
- [ ] HTTPS ativado (SSL certificate)
- [ ] Rate limiting testado
- [ ] Logs auditados (sem dados sensíveis)
- [ ] Firewall configurado

### Performance
- [ ] Database conexão pooling
- [ ] Redis cache (se configurado)
- [ ] CDN para static files
- [ ] Compression habilitado

### Observabilidade
- [ ] Logging estruturado
- [ ] Metrics exportadas (Prometheus)
- [ ] Health check respondendo
- [ ] Alertas configurados

### Backup & Continuidade
- [ ] Database backups agendados
- [ ] Memory snapshots salvos
- [ ] Disaster recovery plan
- [ ] Load balancer (opcional)

---

## 📊 MONITORING & LOGS

### Health Check

```bash
# Verificar status
curl http://localhost:8000/health

# Resposta esperada:
{
  "status": "ok",
  "service": "JARVIS API",
  "version": "5.2",
  "uptime": 3600,
  "components": {
    "ollama": "connected",
    "voice": "ready",
    "autonomy": "active"
  }
}
```

### Logs

```bash
# Real-time logs
docker-compose logs -f jarvis

# Log file (docker)
docker exec jarvis-backend cat /app/backend/logs/jarvis.log

# Log file (local)
tail -f backend/logs/jarvis.log
```

### Métricas (Prometheus)

```bash
# Acessar métricas
curl http://localhost:8000/metrics

# Exemplo Prometheus config:
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'jarvis'
    static_configs:
      - targets: ['localhost:8000']
```

### Alertas Recomendados

```yaml
# Prometheus alerting rules
groups:
  - name: jarvis
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
        for: 5m

      - alert: ServiceDown
        expr: up{job="jarvis"} == 0
        for: 1m

      - alert: HighLatency
        expr: histogram_quantile(0.95, http_request_duration_seconds) > 5
        for: 10m
```

---

## 🔧 TROUBLESHOOTING

### Servidor não inicia

```bash
# Verificar porta em uso
netstat -ano | findstr :8000  # Windows
lsof -i :8000                 # Linux/Mac

# Matar processo
taskkill /PID <PID> /F        # Windows
kill -9 <PID>                 # Linux/Mac

# Verificar imports
python -c "from backend.main import app; print('OK')"
```

### Ollama não conecta

```bash
# Verificar Ollama rodando
curl http://192.168.0.106:11434/api/tags

# Listar models
ollama list

# Puxar model
ollama pull qwen2:0.5b

# Reiniciar Ollama
ollama serve  # ou systemctl restart ollama
```

### Chat não responde

1. Health check: `curl http://localhost:8000/health`
2. Logs: `tail -f backend/logs/jarvis.log`
3. Ollama: `curl http://ollama:11434/api/tags`
4. Firewall: Verificar porta 8000 aberta

### Memory database crescendo

```bash
# Check size
ls -lh backend/memory.db

# Cleanup
python << 'EOF'
import sqlite3
conn = sqlite3.connect('backend/memory.db')
# Delete old entries
conn.execute("DELETE FROM memory WHERE timestamp < unixepoch() - 30*86400")
conn.commit()
EOF
```

---

## 📈 PERFORMANCE TUNING

### Nginx (Reverse Proxy)

```nginx
upstream jarvis {
    server 127.0.0.1:8000;
    keepalive 32;
}

server {
    # Compression
    gzip on;
    gzip_types text/plain text/css application/json;
    
    # Cache
    proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=jarvis_cache:10m;
    
    location / {
        proxy_pass http://jarvis;
        proxy_cache jarvis_cache;
        proxy_cache_valid 200 10m;
    }
}
```

### Python (Uvicorn)

```bash
# Multi-worker
gunicorn backend.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

### Database

```python
# Connection pooling
from sqlalchemy import create_engine
engine = create_engine(
    "sqlite:///memory.db",
    pool_pre_ping=True,
    pool_recycle=3600
)
```

---

## 🔐 PRODUÇÃO CHECKLIST

- [ ] HTTPS/TLS ativado
- [ ] Secrets em environment variables
- [ ] Encryption key gerada e segura
- [ ] Rate limiting testado
- [ ] Logs estruturados
- [ ] Monitoring ativo
- [ ] Backups automatizados
- [ ] Disaster recovery documentado
- [ ] Team treinado
- [ ] Runbook criado

---

**Status:** ✅ PRONTO PARA PRODUÇÃO

Consulte [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) para problemas comuns.
