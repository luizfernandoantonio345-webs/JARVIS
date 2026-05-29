# JARVIS v6.0 — Deploy em Nova Máquina

## Pré-requisitos
- **Windows 10+** ou **Linux**
- **Python 3.11+**
- **Ollama** instalado
- **Git** instalado
- ~2GB espaço em disco

---

## 1️⃣ Clonar Repositório

```bash
git clone https://github.com/luizfernandoantonio345-webs/JARVIS.git
cd JARVIS
```

---

## 2️⃣ Setup Python (Windows)

```bash
# Criar venv
python -m venv venv311

# Ativar
venv311\Scripts\activate

# Instalar dependências
pip install -r backend/requirements.txt
```

**Linux:**
```bash
python3 -m venv venv311
source venv311/bin/activate
pip install -r backend/requirements.txt
```

---

## 3️⃣ Configurar Ollama

### **Windows:**
```bash
# Instalar Ollama
winget install Ollama.Ollama

# Ou baixar manualmente: https://ollama.ai/download

# Iniciar Ollama
ollama serve

# Em outro terminal, puxar modelo:
ollama pull qwen2:0.5b
```

### **Linux:**
```bash
# Instalar
curl -fsSL https://ollama.ai/install.sh | sh

# Iniciar em background
ollama serve &

# Puxar modelo
ollama pull qwen2:0.5b
```

---

## 4️⃣ Configurar .env (Opcional)

Se usar Ollama em outro host/porta, edite `.env`:

```env
JARVIS_OLLAMA_URL=http://seu-host:11434
JARVIS_MODEL=qwen2:0.5b
```

**Default:** localhost:11434 (OK para deploy local)

---

## 5️⃣ Iniciar JARVIS

### **Windows:**
```bash
.\start_jarvis.bat
```

### **Linux/Mac:**
```bash
# Ativar venv primeiro
source venv311/bin/activate

# Iniciar backend
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Browser abrirá automaticamente em: **http://localhost:8000**

---

## 6️⃣ Testar

```bash
# Health check
curl http://localhost:8000/health

# Status
curl http://localhost:8000/status

# WebSocket test
wscat -c ws://localhost:8000/ws/jarvis
```

---

## 📊 Acessos

| Local | URL |
|-------|-----|
| **Mesmo PC** | http://localhost:8000 |
| **Rede Local** | http://seu-ip:8000 |
| **Tailscale** | http://100.110.105.46:8000* |

*Se usando Tailscale na mesma rede

---

## ⚙️ Troubleshooting

### **Porta 8000 já em uso:**
```bash
# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Linux
lsof -ti:8000 | xargs kill -9
```

### **Ollama não responde:**
```bash
# Verificar se está rodando
curl http://localhost:11434/api/tags

# Reiniciar
ollama serve
```

### **Logs:**
```bash
# Windows/Linux
tail -f backend/logs/jarvis.log
```

---

## 📦 Estrutura Deploável

```
JARVIS/
├── backend/          (FastAPI + módulos)
├── frontend/         (HTML estático)
├── .env              (configuração)
├── requirements.txt  (dependências)
├── start_jarvis.bat  (launcher Windows)
├── README.md         (este arquivo)
└── data/             (SQLite)
```

---

## 🚀 Próximos Passos

1. Deploy concluído quando ver: **"JARVIS online. Good day, Sir."**
2. Teste em http://localhost:8000
3. Digite um comando (ex: "Olá") para validar
4. Se precisar expor externamente, use ngrok ou Tailscale

---

## 📝 Notas

- **Primeira resposta:** ~20s (Ollama prewarm)
- **Respostas seguintes:** ~8-15s
- **TTS:** ~3s por mensagem
- **GPU:** Recomendado (usa CPU se não houver)

---

**Deploy v6.0 — Production Ready**  
Última atualização: 2026-05-29
